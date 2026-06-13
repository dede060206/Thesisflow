from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> None:
    report_path = Path(sys.argv[1])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    lines = [
        "## Thesisflow daily ingestion",
        f"- Candidates discovered: {report['candidates_discovered']}",
        f"- Pages fetched: {report['pages_fetched']}",
        f"- Articles summarized: {report['articles_summarized']}",
        f"- Database rows written: {report['database_rows_written']}",
        f"- Operational errors: {report.get('operational_errors', 0)}",
        f"- Per-source counts: {report['per_source_counts']}",
        f"- Estimated API usage: {report['estimated_api_usage']}",
    ]
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as output:
            output.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


if __name__ == "__main__":
    main()
