from __future__ import annotations

import sys
from pathlib import Path

from pac_poc.sqlcipher_poc import SQLCipherFTSDatabase


def main() -> int:
    if len(sys.argv) != 2:
        return 2
    key = sys.stdin.readline().rstrip("\r\n")
    if not key:
        return 2

    database = SQLCipherFTSDatabase.open_existing(path=Path(sys.argv[1]), key=key)
    try:
        database._connection.execute("PRAGMA busy_timeout = 30000")
        print("CHECKPOINT_BEGIN", flush=True)
        database.checkpoint_wal_for_poc("TRUNCATE")
        print("CHECKPOINT_RETURNED", flush=True)
    finally:
        database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
