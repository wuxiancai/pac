from __future__ import annotations

import sys
import time
from pathlib import Path

from pac_poc.sqlcipher_poc import SQLCipherFTSDatabase


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    source_path = Path(sys.argv[1])
    target_path = Path(sys.argv[2])
    source_key = sys.stdin.readline().rstrip("\r\n")
    backup_key = sys.stdin.readline().rstrip("\r\n")
    if not source_key or not backup_key:
        return 2

    database = SQLCipherFTSDatabase.open_existing(path=source_path, key=source_key)

    def pause_during_copy(destination) -> None:
        first_partial_page = True

        def on_progress(_status: int, remaining: int, total: int) -> None:
            nonlocal first_partial_page
            if first_partial_page and 0 < remaining < total:
                first_partial_page = False
                print(f"BACKUP_COPY_PROGRESS {remaining} {total}", flush=True)
                while True:
                    time.sleep(60)

        database._connection.backup(destination, pages=1, progress=on_progress)

    database._copy_backup_to = pause_during_copy
    database.backup_to(target_path, backup_key=backup_key)
    database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
