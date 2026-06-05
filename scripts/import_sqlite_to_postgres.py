from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import BASE_DIR
from app.database import get_connection, run_migrations


DEFAULT_SQLITE_PATH = BASE_DIR / "data" / "vc_blogs.sqlite3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import local SQLite Thesisflow data into Postgres."
    )
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=DEFAULT_SQLITE_PATH,
        help="Path to the local SQLite database.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read SQLite and report counts without writing to Postgres.",
    )
    return parser.parse_args()


def sqlite_connection(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"SQLite database not found: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def load_sqlite_rows(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with sqlite_connection(path) as conn:
        articles = [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT
                    source, title, url, author, published_at, fetched_at, content,
                    category, word_count, is_long_form, summary, summary_model,
                    summarized_at
                FROM articles
                ORDER BY id
                """
            ).fetchall()
        ]
        insights = [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT
                    category, week_start, week_end, insight, summary_model,
                    generated_at
                FROM weekly_category_insights
                ORDER BY id
                """
            ).fetchall()
        ]
    return articles, insights


def normalize_article(article: dict[str, Any]) -> dict[str, Any]:
    article["is_long_form"] = bool(article.get("is_long_form"))
    return article


def import_articles(articles: list[dict[str, Any]]) -> int:
    inserted = 0
    with get_connection() as conn:
        for article in articles:
            cursor = conn.execute(
                """
                INSERT INTO articles (
                    source, title, url, author, published_at, fetched_at, content,
                    category, word_count, is_long_form, summary, summary_model,
                    summarized_at
                )
                VALUES (
                    %(source)s, %(title)s, %(url)s, %(author)s, %(published_at)s,
                    %(fetched_at)s, %(content)s, %(category)s, %(word_count)s,
                    %(is_long_form)s, %(summary)s, %(summary_model)s,
                    %(summarized_at)s
                )
                ON CONFLICT (url) DO NOTHING
                RETURNING id
                """,
                normalize_article(article),
            )
            if cursor.fetchone() is not None:
                inserted += 1
    return inserted


def import_insights(insights: list[dict[str, Any]]) -> int:
    inserted = 0
    with get_connection() as conn:
        for insight in insights:
            cursor = conn.execute(
                """
                INSERT INTO weekly_category_insights (
                    category, week_start, week_end, insight, summary_model,
                    generated_at
                )
                VALUES (
                    %(category)s, %(week_start)s, %(week_end)s, %(insight)s,
                    %(summary_model)s, %(generated_at)s
                )
                ON CONFLICT (category, week_start) DO NOTHING
                RETURNING id
                """,
                insight,
            )
            if cursor.fetchone() is not None:
                inserted += 1
    return inserted


def main() -> None:
    args = parse_args()
    articles, insights = load_sqlite_rows(args.sqlite_path)

    print(f"SQLite source: {args.sqlite_path}")
    print(f"Found articles: {len(articles)}")
    print(f"Found weekly insights: {len(insights)}")

    if args.dry_run:
        print("Dry run complete. No Postgres writes performed.")
        return

    migrations = run_migrations()
    inserted_articles = import_articles(articles)
    inserted_insights = import_insights(insights)

    print("Migrations:", migrations or "none")
    print(f"Inserted articles: {inserted_articles}")
    print(f"Skipped existing articles: {len(articles) - inserted_articles}")
    print(f"Inserted weekly insights: {inserted_insights}")
    print(f"Skipped existing weekly insights: {len(insights) - inserted_insights}")


if __name__ == "__main__":
    main()
