from __future__ import annotations

import sys
import time
from pathlib import Path

from pac_poc import sqlcipher_poc
from pac_poc.sqlcipher_poc import SQLCipherFTSDatabase


def main() -> int:
    if len(sys.argv) != 4 or sys.argv[3] not in {"before", "after"}:
        return 2
    source_path = Path(sys.argv[1])
    target_path = Path(sys.argv[2])
    boundary = sys.argv[3]
    source_key = sys.stdin.readline().rstrip("\r\n")
    backup_key = sys.stdin.readline().rstrip("\r\n")
    if not source_key or not backup_key:
        return 2

    database = SQLCipherFTSDatabase.open_existing(path=source_path, key=source_key)
    real_replace = sqlcipher_poc.os.replace

    def pause_at_replace(source: str | Path, target: str | Path) -> None:
        if boundary == "before":
            print("REPLACE_BEFORE", flush=True)
            while True:
                time.sleep(60)
        real_replace(source, target)
        print("REPLACE_AFTER", flush=True)
        while True:
            time.sleep(60)

    sqlcipher_poc.os.replace = pause_at_replace
    database.backup_to(target_path, backup_key=backup_key)
    database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
