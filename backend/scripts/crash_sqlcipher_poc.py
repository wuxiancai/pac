from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import sqlcipher3.dbapi2 as sqlcipher


def main() -> int:
    if len(sys.argv) not in (2, 3, 4):
        return 2
    wait_for_kill = "--wait-for-kill" in sys.argv[2:]
    journal_mode = "wal" if "--wal" in sys.argv[2:] else "delete"
    allowed_options = {"--wait-for-kill", "--wal", "--delete-journal"}
    if any(option not in allowed_options for option in sys.argv[2:]):
        return 2
    if len(sys.argv) >= 3 and not wait_for_kill:
        return 2
    if journal_mode == "wal" and "--delete-journal" in sys.argv[2:]:
        return 2
    key = sys.stdin.readline().rstrip("\r\n")
    if not key:
        return 2

    connection = sqlcipher.connect(str(Path(sys.argv[1])))
    escaped_key = key.replace("'", "''")
    connection.execute(f"PRAGMA key = '{escaped_key}'")
    connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
    if journal_mode == "wal":
        actual_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()
        if not actual_mode or str(actual_mode[0]).lower() != "wal":
            connection.close()
            return 3
    connection.execute("BEGIN IMMEDIATE")
    cursor = connection.execute(
        "INSERT INTO poc_memories(content) VALUES (?)", ("uncommitted crash marker",)
    )
    connection.execute(
        "INSERT INTO poc_memories_fts(memory_id, content) VALUES (?, ?)",
        (int(cursor.lastrowid), "uncommitted crash marker"),
    )
    if wait_for_kill:
        print("READY", flush=True)
        while True:
            time.sleep(60)
    os._exit(73)


if __name__ == "__main__":
    raise SystemExit(main())
