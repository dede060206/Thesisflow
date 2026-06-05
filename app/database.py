from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.config import CATEGORIES, DATABASE_URL, MIN_ARTICLE_DATE, TOP_READS_MAX_AGE_DAYS


MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
ELIGIBLE_ARTICLE_SQL = (
    "(source = 'Sequoia' OR COALESCE(word_count, 0) > 1000) "
    "AND DATE(COALESCE(published_at, fetched_at)) >= %(min_article_date)s"
)


def get_connection() -> psycopg.Connection:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required for Postgres storage.")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def run_migrations() -> list[str]:
    applied: list[str] = []
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        existing = {
            row["version"]
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in existing:
                continue
            with conn.transaction():
                conn.execute(path.read_text())
                conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)",
                    (path.name,),
                )
            applied.append(path.name)
    return applied


def init_db() -> None:
    run_migrations()


def query_params(**extra: Any) -> dict[str, Any]:
    return {"min_article_date": MIN_ARTICLE_DATE, **extra}


def upsert_article(article: dict[str, Any]) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO articles (
                source, title, url, author, published_at, fetched_at, content,
                category, word_count, is_long_form
            )
            VALUES (
                %(source)s, %(title)s, %(url)s, %(author)s, %(published_at)s,
                %(fetched_at)s, %(content)s, %(category)s, %(word_count)s,
                %(is_long_form)s
            )
            ON CONFLICT (url) DO NOTHING
            RETURNING id
            """,
            article,
        )
        return cursor.fetchone() is not None


def list_articles(limit: int = 100) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT *
            FROM articles
            WHERE """
            + ELIGIBLE_ARTICLE_SQL
            + """
            ORDER BY is_long_form DESC, COALESCE(published_at, fetched_at) DESC
            LIMIT %(limit)s
            """,
            query_params(limit=limit),
        ).fetchall()


def list_daily_articles() -> list[dict[str, Any]]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT *
            FROM articles
            WHERE DATE(fetched_at) = CURRENT_DATE
              AND """
            + ELIGIBLE_ARTICLE_SQL
            + """
            ORDER BY is_long_form DESC, COALESCE(published_at, fetched_at) DESC
            LIMIT 20
            """,
            query_params(),
        ).fetchall()


def list_articles_by_category(
    category: str, limit: int = 100
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT *
            FROM articles
            WHERE category = %(category)s
              AND """
            + ELIGIBLE_ARTICLE_SQL
            + """
            ORDER BY is_long_form DESC, word_count DESC, COALESCE(published_at, fetched_at) DESC
            LIMIT %(limit)s
            """,
            query_params(category=category, limit=limit),
        ).fetchall()


def list_top_reads_today(limit: int = 5) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT *
            FROM articles
            WHERE DATE(fetched_at) = CURRENT_DATE
              AND """
            + ELIGIBLE_ARTICLE_SQL
            + """
              AND published_at IS NOT NULL
              AND DATE(published_at) >= CURRENT_DATE - (%(top_reads_max_age_days)s * INTERVAL '1 day')
            ORDER BY
                is_long_form DESC,
                CASE WHEN summary IS NULL OR summary = '' THEN 1 ELSE 0 END,
                word_count DESC,
                COALESCE(published_at, fetched_at) DESC
            LIMIT %(limit)s
            """,
            query_params(
                top_reads_max_age_days=TOP_READS_MAX_AGE_DAYS,
                limit=limit,
            ),
        ).fetchall()


SOURCE_ALIASES = {
    "a16z": "andreessen horowitz",
    "andreessen": "andreessen horowitz",
    "yc": "y combinator",
    "ycombinator": "y combinator",
    "bvp": "bessemer",
    "bessemer venture partners": "bessemer",
    "lsvp": "lightspeed",
    "firstround": "first round",
}


def normalize_search_query(query: str) -> tuple[str, bool]:
    normalized = " ".join(query.lower().split())
    if normalized in SOURCE_ALIASES:
        return SOURCE_ALIASES[normalized], True
    return normalized, False


def word_match(needle: str, haystack: str) -> bool:
    return bool(re.search(rf"\b{re.escape(needle)}\b", haystack))


def article_search_score(
    article: dict[str, Any], query: str, source_only: bool = False
) -> int:
    title = (article["title"] or "").lower()
    source = (article["source"] or "").lower()
    category = (article["category"] or "").lower()
    summary = (article["summary"] or "").lower()
    content = (article["content"] or "").lower()
    short_query = len(query) <= 3
    score = 0

    if query == source or query in source:
        score += 100
    elif source_only:
        return 0
    if source_only:
        return score
    if query == category or query in category:
        score += 80
    if query in title:
        score += 60
    if word_match(query, title):
        score += 30
    if not short_query and query in summary:
        score += 20
    if not short_query and query in content:
        score += 5
    if article["is_long_form"]:
        score += 3
    score += min(int(article["word_count"] or 0) // 1000, 5)
    return score


def search_articles(query: str, limit: int = 100) -> list[dict[str, Any]]:
    normalized_query, source_only = normalize_search_query(query)
    with get_connection() as conn:
        articles = conn.execute(
            """
            SELECT *
            FROM articles
            WHERE """
            + ELIGIBLE_ARTICLE_SQL
            + """
            ORDER BY is_long_form DESC, word_count DESC, COALESCE(published_at, fetched_at) DESC
            """,
            query_params(),
        ).fetchall()

    scored = [
        (article_search_score(article, normalized_query, source_only), article)
        for article in articles
    ]
    matches = [item for item in scored if item[0] > 0]
    matches.sort(
        key=lambda item: (
            -item[0],
            -int(item[1]["is_long_form"] or 0),
            -int(item[1]["word_count"] or 0),
            item[1]["title"] or "",
        )
    )
    return [article for _, article in matches[:limit]]


def get_article(article_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM articles WHERE id = %s",
            (article_id,),
        ).fetchone()


def list_unsummarized_articles(limit: int = 20) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT *
            FROM articles
            WHERE summary IS NULL OR summary = ''
            ORDER BY is_long_form DESC, word_count DESC, COALESCE(published_at, fetched_at) DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()


def list_articles_for_resummary(limit: int = 100) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT *
            FROM articles
            ORDER BY is_long_form DESC, word_count DESC, COALESCE(published_at, fetched_at) DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()


def save_summary(
    article_id: int, summary: str, model: str, summarized_at: str
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE articles
            SET summary = %s, summary_model = %s, summarized_at = %s
            WHERE id = %s
            """,
            (summary, model, summarized_at, article_id),
        )


def list_articles_for_weekly_insight(
    category: str, week_start: str, week_end: str, limit: int = 20
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT *
            FROM articles
            WHERE category = %s
              AND DATE(fetched_at) >= %s
              AND DATE(fetched_at) <= %s
            ORDER BY is_long_form DESC, word_count DESC, COALESCE(published_at, fetched_at) DESC
            LIMIT %s
            """,
            (category, week_start, week_end, limit),
        ).fetchall()


def get_weekly_insight(
    category: str, week_start: str
) -> dict[str, Any] | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT *
            FROM weekly_category_insights
            WHERE category = %s AND week_start = %s
            """,
            (category, week_start),
        ).fetchone()


def get_weekly_insight_by_id(insight_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT *
            FROM weekly_category_insights
            WHERE id = %s
            """,
            (insight_id,),
        ).fetchone()


def list_latest_weekly_insights() -> list[dict[str, Any]]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT *
            FROM weekly_category_insights
            WHERE week_start = (
                SELECT MAX(week_start) FROM weekly_category_insights
            )
            ORDER BY category
            """
        ).fetchall()


def save_weekly_insight(
    category: str,
    week_start: str,
    week_end: str,
    insight: str,
    model: str,
    generated_at: str,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO weekly_category_insights (
                category, week_start, week_end, insight, summary_model, generated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (category, week_start) DO UPDATE SET
                week_end = EXCLUDED.week_end,
                insight = EXCLUDED.insight,
                summary_model = EXCLUDED.summary_model,
                generated_at = EXCLUDED.generated_at
            """,
            (category, week_start, week_end, insight, model, generated_at),
        )


def missing_weekly_insight_categories(week_start: str) -> list[str]:
    with get_connection() as conn:
        existing = {
            row["category"]
            for row in conn.execute(
                """
                SELECT category
                FROM weekly_category_insights
                WHERE week_start = %s
                """,
                (week_start,),
            ).fetchall()
        }
    return [category for category in CATEGORIES if category not in existing]
