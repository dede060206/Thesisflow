from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

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


def normalize_article_for_write(article: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(article)
    normalized["is_long_form"] = bool(normalized.get("is_long_form"))
    return normalized


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(value) for value in values) + "]"


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
            normalize_article_for_write(article),
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


def list_articles_for_indexing(limit: int = 100) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT a.*
            FROM articles a
            LEFT JOIN article_chunks c ON c.article_id = a.id
            WHERE COALESCE(a.content, '') <> ''
              AND """
            + ELIGIBLE_ARTICLE_SQL.replace("source", "a.source").replace(
                "word_count", "a.word_count"
            ).replace("published_at", "a.published_at").replace(
                "fetched_at", "a.fetched_at"
            )
            + """
            GROUP BY a.id
            HAVING COUNT(c.id) = 0 OR COUNT(c.embedding) = 0
            ORDER BY a.is_long_form DESC, a.word_count DESC,
                     COALESCE(a.published_at, a.fetched_at) DESC
            LIMIT %(limit)s
            """,
            query_params(limit=limit),
        ).fetchall()


def replace_article_chunks(
    article_id: int,
    chunks: list[dict[str, Any]],
    embedding_model: str | None,
) -> None:
    with get_connection() as conn:
        with conn.transaction():
            conn.execute(
                "DELETE FROM article_chunks WHERE article_id = %s",
                (article_id,),
            )
            for chunk in chunks:
                embedding = chunk.get("embedding")
                conn.execute(
                    """
                    INSERT INTO article_chunks (
                        article_id, chunk_index, content, word_count,
                        content_hash, embedding, embedding_model
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::vector, %s)
                    """,
                    (
                        article_id,
                        chunk["chunk_index"],
                        chunk["content"],
                        chunk["word_count"],
                        chunk["content_hash"],
                        vector_literal(embedding) if embedding else None,
                        embedding_model if embedding else None,
                    ),
                )


def search_article_chunks_vector(
    embedding: list[float], limit: int = 6, source: str | None = None
) -> list[dict[str, Any]]:
    query_vector = vector_literal(embedding)
    source_clause = " AND a.source = %(source)s" if source else ""
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                c.id AS chunk_id,
                c.content AS chunk_content,
                c.chunk_index,
                a.id AS article_id,
                a.title,
                a.source,
                a.url,
                a.published_at,
                a.fetched_at,
                1 - (c.embedding <=> %(embedding)s::vector) AS score
            FROM article_chunks c
            JOIN articles a ON a.id = c.article_id
            WHERE c.embedding IS NOT NULL
              AND """
            + ELIGIBLE_ARTICLE_SQL.replace("source", "a.source").replace(
                "word_count", "a.word_count"
            ).replace("published_at", "a.published_at").replace(
                "fetched_at", "a.fetched_at"
            )
            + source_clause
            + """
            ORDER BY c.embedding <=> %(embedding)s::vector
            LIMIT %(limit)s
            """,
            query_params(embedding=query_vector, limit=limit, source=source),
        ).fetchall()


def search_article_chunks_text(
    query: str, limit: int = 6, source: str | None = None
) -> list[dict[str, Any]]:
    source_clause = " AND a.source = %(source)s" if source else ""
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                c.id AS chunk_id,
                c.content AS chunk_content,
                c.chunk_index,
                a.id AS article_id,
                a.title,
                a.source,
                a.url,
                a.published_at,
                a.fetched_at,
                ts_rank_cd(
                    to_tsvector('english', c.content),
                    websearch_to_tsquery('english', %(query)s)
                ) AS score
            FROM article_chunks c
            JOIN articles a ON a.id = c.article_id
            WHERE to_tsvector('english', c.content)
                  @@ websearch_to_tsquery('english', %(query)s)
              AND """
            + ELIGIBLE_ARTICLE_SQL.replace("source", "a.source").replace(
                "word_count", "a.word_count"
            ).replace("published_at", "a.published_at").replace(
                "fetched_at", "a.fetched_at"
            )
            + source_clause
            + """
            ORDER BY score DESC
            LIMIT %(limit)s
            """,
            query_params(query=query, limit=limit, source=source),
        ).fetchall()


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


def list_articles_for_weekly_report(
    week_start: str, week_end: str, limit: int = 200
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT *
            FROM articles
            WHERE DATE(COALESCE(published_at, fetched_at)) >= %(week_start)s
              AND DATE(COALESCE(published_at, fetched_at)) <= %(week_end)s
              AND """
            + ELIGIBLE_ARTICLE_SQL
            + """
            ORDER BY COALESCE(published_at, fetched_at) DESC,
                     is_long_form DESC, word_count DESC
            LIMIT %(limit)s
            """,
            query_params(
                week_start=week_start,
                week_end=week_end,
                limit=limit,
            ),
        ).fetchall()


def get_weekly_market_report(week_start: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT *
            FROM weekly_market_reports
            WHERE week_start = %s
            """,
            (week_start,),
        ).fetchone()


def get_latest_weekly_market_report() -> dict[str, Any] | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT *
            FROM weekly_market_reports
            ORDER BY week_start DESC
            LIMIT 1
            """
        ).fetchone()


def save_weekly_market_report(
    *,
    week_start: str,
    week_end: str,
    report: dict[str, Any],
    citations: list[dict[str, Any]],
    source_article_ids: list[int],
    article_count: int,
    investor_count: int,
    model: str,
    generated_at: str,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO weekly_market_reports (
                week_start, week_end, report, citations, source_article_ids,
                article_count, investor_count, model, generated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (week_start) DO UPDATE SET
                week_end = EXCLUDED.week_end,
                report = EXCLUDED.report,
                citations = EXCLUDED.citations,
                source_article_ids = EXCLUDED.source_article_ids,
                article_count = EXCLUDED.article_count,
                investor_count = EXCLUDED.investor_count,
                model = EXCLUDED.model,
                report_version = weekly_market_reports.report_version + 1,
                generated_at = EXCLUDED.generated_at
            """,
            (
                week_start,
                week_end,
                Jsonb(report),
                Jsonb(citations),
                source_article_ids,
                article_count,
                investor_count,
                model,
                generated_at,
            ),
        )


def list_theses(workspace_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT t.*, COUNT(e.id) AS evidence_count
            FROM investment_theses t
            LEFT JOIN thesis_evidence e ON e.thesis_id = t.id
            WHERE t.workspace_id = %s
            GROUP BY t.id
            ORDER BY t.updated_at DESC
            """,
            (workspace_id,),
        ).fetchall()


def count_theses(workspace_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM investment_theses WHERE workspace_id = %s",
            (workspace_id,),
        ).fetchone()
        return int(row["count"])


def create_thesis(
    workspace_id: str, title: str, core_claim: str
) -> dict[str, Any]:
    with get_connection() as conn:
        return conn.execute(
            """
            INSERT INTO investment_theses (workspace_id, title, core_claim)
            VALUES (%s, %s, %s)
            RETURNING *
            """,
            (workspace_id, title, core_claim),
        ).fetchone()


def get_thesis(thesis_id: int, workspace_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT *
            FROM investment_theses
            WHERE id = %s AND workspace_id = %s
            """,
            (thesis_id, workspace_id),
        ).fetchone()


def update_thesis(
    thesis_id: int,
    workspace_id: str,
    *,
    title: str,
    core_claim: str,
) -> dict[str, Any] | None:
    with get_connection() as conn:
        return conn.execute(
            """
            UPDATE investment_theses
            SET title = %s, core_claim = %s, updated_at = NOW()
            WHERE id = %s AND workspace_id = %s
            RETURNING *
            """,
            (title, core_claim, thesis_id, workspace_id),
        ).fetchone()


def list_thesis_evidence(
    thesis_id: int, workspace_id: str
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT e.*
            FROM thesis_evidence e
            JOIN investment_theses t ON t.id = e.thesis_id
            WHERE e.thesis_id = %s AND t.workspace_id = %s
            ORDER BY e.created_at
            """,
            (thesis_id, workspace_id),
        ).fetchall()


def count_thesis_evidence(thesis_id: int, workspace_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM thesis_evidence e
            JOIN investment_theses t ON t.id = e.thesis_id
            WHERE e.thesis_id = %s AND t.workspace_id = %s
            """,
            (thesis_id, workspace_id),
        ).fetchone()
        return int(row["count"])


def search_articles_for_evidence(
    query: str, limit: int = 12
) -> list[dict[str, Any]]:
    pattern = f"%{query}%"
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, title, source, url, published_at, fetched_at,
                   category, summary, word_count
            FROM articles
            WHERE (
                title ILIKE %(pattern)s
                OR source ILIKE %(pattern)s
                OR category ILIKE %(pattern)s
                OR summary ILIKE %(pattern)s
                OR content ILIKE %(pattern)s
            )
              AND """
            + ELIGIBLE_ARTICLE_SQL
            + """
            ORDER BY is_long_form DESC, word_count DESC,
                     COALESCE(published_at, fetched_at) DESC
            LIMIT %(limit)s
            """,
            query_params(pattern=pattern, limit=limit),
        ).fetchall()


def add_article_evidence(
    thesis_id: int,
    workspace_id: str,
    article_id: int,
) -> dict[str, Any] | None:
    with get_connection() as conn:
        thesis = conn.execute(
            "SELECT id FROM investment_theses WHERE id = %s AND workspace_id = %s",
            (thesis_id, workspace_id),
        ).fetchone()
        if not thesis:
            return None
        article = conn.execute(
            "SELECT * FROM articles WHERE id = %s",
            (article_id,),
        ).fetchone()
        if not article:
            return None
        excerpt = article["summary"] or (article["content"] or "")[:3000]
        return conn.execute(
            """
            INSERT INTO thesis_evidence (
                thesis_id, evidence_type, article_id, title, source, url,
                published_at, excerpt, metadata
            )
            VALUES (%s, 'article', %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (thesis_id, article_id) WHERE article_id IS NOT NULL
            DO UPDATE SET excerpt = EXCLUDED.excerpt
            RETURNING *
            """,
            (
                thesis_id,
                article_id,
                article["title"],
                article["source"],
                article["url"],
                article["published_at"] or article["fetched_at"],
                excerpt,
                Jsonb({"category": article["category"]}),
            ),
        ).fetchone()


def add_snapshot_evidence(
    thesis_id: int,
    workspace_id: str,
    *,
    evidence_type: str,
    title: str,
    excerpt: str,
    source: str | None = None,
    url: str | None = None,
    note: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    with get_connection() as conn:
        thesis = conn.execute(
            "SELECT id FROM investment_theses WHERE id = %s AND workspace_id = %s",
            (thesis_id, workspace_id),
        ).fetchone()
        if not thesis:
            return None
        return conn.execute(
            """
            INSERT INTO thesis_evidence (
                thesis_id, evidence_type, title, source, url, excerpt, note, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                thesis_id,
                evidence_type,
                title,
                source,
                url,
                excerpt,
                note,
                Jsonb(metadata or {}),
            ),
        ).fetchone()


def delete_thesis_evidence(
    thesis_id: int, workspace_id: str, evidence_id: int
) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            """
            DELETE FROM thesis_evidence e
            USING investment_theses t
            WHERE e.id = %s AND e.thesis_id = %s
              AND t.id = e.thesis_id AND t.workspace_id = %s
            RETURNING e.id
            """,
            (evidence_id, thesis_id, workspace_id),
        ).fetchone()
        return row is not None


def save_thesis_sections(
    thesis_id: int,
    workspace_id: str,
    sections: dict[str, Any],
    model: str,
) -> dict[str, Any] | None:
    with get_connection() as conn:
        return conn.execute(
            """
            UPDATE investment_theses
            SET generated_sections = %s,
                analysis_model = %s,
                status = 'developed',
                updated_at = NOW()
            WHERE id = %s AND workspace_id = %s
            RETURNING *
            """,
            (Jsonb(sections), model, thesis_id, workspace_id),
        ).fetchone()


def save_thesis_memo(
    thesis_id: int,
    workspace_id: str,
    memo: str,
    model: str,
) -> dict[str, Any] | None:
    with get_connection() as conn:
        return conn.execute(
            """
            UPDATE investment_theses
            SET investment_memo = %s,
                memo_model = %s,
                status = 'memo_ready',
                updated_at = NOW()
            WHERE id = %s AND workspace_id = %s
            RETURNING *
            """,
            (memo, model, thesis_id, workspace_id),
        ).fetchone()


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
