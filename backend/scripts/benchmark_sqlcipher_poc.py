from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from pac_poc.sqlcipher_benchmark import benchmark_pair


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure synthetic SQLite/FTS5 and SQLCipher/FTS5 workloads"
    )
    parser.add_argument("--records", type=int, default=2_000)
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path(".poc-data/sqlcipher-bench"),
        help="Explicit temporary workspace; each run is removed afterward",
    )
    args = parser.parse_args()
    if args.records <= 0 or args.queries <= 0 or args.repeats <= 0:
        parser.error("records, queries, and repeats must be positive")

    args.work_dir.mkdir(parents=True, exist_ok=True)
    runs = []
    for _ in range(args.repeats):
        with tempfile.TemporaryDirectory(prefix="run-", dir=args.work_dir) as temporary:
            runs.append(
                benchmark_pair(
                    Path(temporary),
                    records=args.records,
                    queries=args.queries,
                )
            )

    print(
        json.dumps(
            {
                "status": "completed",
                "synthetic_data": True,
                "transcript_or_record_content_logged": False,
                "records": args.records,
                "queries": args.queries,
                "repeats": args.repeats,
                "runs": runs,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
