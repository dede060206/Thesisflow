from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

import httpx


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import INGESTION_ALERT_WEBHOOK_URL
from app.daily_ingestion import DailyIngestionConfig, run_daily_ingestion
from app.database import finish_ingestion_run, run_migrations, start_ingestion_run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the controlled Thesisflow daily ingestion policy manually."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run discovery and triage only. Do not fetch articles, call AI, or write rows.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help=(
            "Run the full pipeline and generate summaries, but do not write article "
            "or summary rows to the database."
        ),
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional path for the JSON report.",
    )
    return parser.parse_args()


def workflow_run_url() -> str | None:
    server = os.getenv("GITHUB_SERVER_URL")
    repository = os.getenv("GITHUB_REPOSITORY")
    run_id = os.getenv("GITHUB_RUN_ID")
    if server and repository and run_id:
        return f"{server}/{repository}/actions/runs/{run_id}"
    return None


def notify_failure(message: str) -> None:
    if not INGESTION_ALERT_WEBHOOK_URL:
        return
    try:
        httpx.post(
            INGESTION_ALERT_WEBHOOK_URL,
            json={"text": message, "content": message},
            timeout=10,
        ).raise_for_status()
    except Exception as exc:
        print(f"[ALERT ERROR] Failed to send ingestion alert: {exc}")


def main() -> None:
    args = parse_args()
    if args.dry_run and args.preview:
        raise SystemExit("Choose either --dry-run or --preview, not both.")
    config = DailyIngestionConfig()
    run_id: int | None = None
    if not args.dry_run and not args.preview:
        run_migrations()
        run_id = start_ingestion_run(
            dry_run=False,
            preview=False,
            limits={
                "max_candidate_links": config.max_candidate_links,
                "max_pages_fetched": config.max_pages_fetched,
                "max_articles_summarized": config.max_articles_summarized,
                "min_quality_score": config.min_quality_score,
                "max_per_source": config.max_per_source,
                "max_recursion_depth": config.max_recursion_depth,
            },
            workflow_run_url=workflow_run_url(),
        )
    try:
        report = run_daily_ingestion(
            config=config,
            dry_run=args.dry_run,
            preview=args.preview,
        )
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(rendered + "\n", encoding="utf-8")
        if run_id is not None:
            finish_ingestion_run(run_id, status="succeeded", report=report)
        print(rendered)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
        if run_id is not None:
            finish_ingestion_run(run_id, status="failed", error_message=error)
        url = workflow_run_url()
        notify_failure(
            "Thesisflow daily ingestion failed. "
            f"Error: {error}. Run: {url or 'local execution'}"
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
