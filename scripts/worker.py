from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import DAILY_ARTICLE_LIMIT
from app.database import run_migrations
from app.fetcher import fetch_all_feeds
from app.summarizer import generate_weekly_category_insights, summarize_pending


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Thesisflow ingestion worker.")
    parser.add_argument(
        "--summary-limit",
        type=int,
        default=DAILY_ARTICLE_LIMIT,
        help="Maximum number of articles to summarize.",
    )
    parser.add_argument(
        "--force-resummarize",
        action="store_true",
        help="Regenerate summaries for existing articles.",
    )
    parser.add_argument(
        "--force-weekly-insights",
        action="store_true",
        help="Regenerate weekly category insights for the current week.",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip article fetching and only run summarization/insights.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    migrations = run_migrations()
    fetch_result = {"skipped": True}
    if not args.skip_fetch:
        fetch_result = fetch_all_feeds()
    summary_limit = (
        args.summary_limit
        if args.force_resummarize
        else min(args.summary_limit, DAILY_ARTICLE_LIMIT)
    )
    summary_result = summarize_pending(
        limit=summary_limit,
        force=args.force_resummarize,
    )
    weekly_result = generate_weekly_category_insights(
        force=args.force_weekly_insights
    )

    print("Migrations:", migrations or "none")
    print("Fetch:", fetch_result)
    print("Summaries:", summary_result)
    print("Weekly insights:", weekly_result)


if __name__ == "__main__":
    main()
