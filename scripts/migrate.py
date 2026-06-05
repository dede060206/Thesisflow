from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import run_migrations


def main() -> None:
    applied = run_migrations()
    if applied:
        print("Applied migrations:", ", ".join(applied))
    else:
        print("Database already up to date.")


if __name__ == "__main__":
    main()
