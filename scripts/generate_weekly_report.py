from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import run_migrations
from app.weekly_report import generate_weekly_market_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a Thesisflow comprehensive weekly market report."
    )
    parser.add_argument("--week-start", help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--week-end", help="End date in YYYY-MM-DD format.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if bool(args.week_start) != bool(args.week_end):
        raise SystemExit("--week-start and --week-end must be provided together.")
    migrations = run_migrations()
    result = generate_weekly_market_report(
        force=True,
        week_start=args.week_start,
        week_end=args.week_end,
    )
    print("Migrations:", migrations or "none")
    print("Weekly market report:", result)


if __name__ == "__main__":
    main()
