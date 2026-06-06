from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import run_migrations
from app.indexer import index_pending_articles


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create chunks and embeddings for existing Thesisflow articles."
    )
    parser.add_argument("--limit", type=int, default=500)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    migrations = run_migrations()
    result = index_pending_articles(limit=args.limit)
    print("Migrations:", migrations or "none")
    print("Article indexing:", result)


if __name__ == "__main__":
    main()
