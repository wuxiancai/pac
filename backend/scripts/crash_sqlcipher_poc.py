from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import sqlcipher3.dbapi2 as sqlcipher


def main() -> int:
    if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != "--wait-for-kill"):
        return 2
    key = sys.stdin.readline().rstrip("\r\n")
    if not key:
        return 2

    connection = sqlcipher.connect(str(Path(sys.argv[1])))
    escaped_key = key.replace("'", "''")
    connection.execute(f"PRAGMA key = '{escaped_key}'")
    connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
    connection.execute("BEGIN IMMEDIATE")
    cursor = connection.execute(
        "INSERT INTO poc_memories(content) VALUES (?)", ("uncommitted crash marker",)
    )
    connection.execute(
        "INSERT INTO poc_memories_fts(memory_id, content) VALUES (?, ?)",
        (int(cursor.lastrowid), "uncommitted crash marker"),
    )
    if len(sys.argv) == 3:
        print("READY", flush=True)
        while True:
            time.sleep(60)
    os._exit(73)


if __name__ == "__main__":
    raise SystemExit(main())
