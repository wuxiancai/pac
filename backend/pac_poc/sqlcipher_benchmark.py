from __future__ import annotations

import os
import secrets
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any

from pac_poc.sqlcipher_poc import SQLCipherFTSDatabase


def benchmark_pair(directory: Path, *, records: int, queries: int) -> dict[str, Any]:
    """Measure identical synthetic SQLite/FTS5 and SQLCipher/FTS5 workloads."""
    if records <= 0 or queries <= 0:
        raise ValueError("records and queries must be positive")
    directory.mkdir(parents=True, exist_ok=True)
    sqlite_metrics = _benchmark_backend(
        directory / "sqlite.db", directory / "sqlite-backup.db", "sqlite", records, queries
    )
    cipher_metrics = _benchmark_backend(
        directory / "sqlcipher.db",
        directory / "sqlcipher-backup.db",
        "sqlcipher",
        records,
        queries,
    )
    return {
        "records": records,
        "queries": queries,
        "engines": {"sqlite": sqlite_metrics, "sqlcipher": cipher_metrics},
    }


def _benchmark_backend(
    path: Path,
    backup_path: Path,
    engine_name: str,
    records: int,
    queries: int,
) -> dict[str, Any]:
    cipher_database = None
    plain_connection = None
    cipher_version = ""
    if engine_name == "sqlcipher":
        cipher_database = SQLCipherFTSDatabase(
            path=path,
            key=secrets.token_urlsafe(48),
        )
        connection = cipher_database._connection
        cipher_version = cipher_database.cipher_version
    else:
        plain_connection = sqlite3.connect(str(path))
        connection = plain_connection
        connection.executescript(
            """
            CREATE TABLE poc_memories (
                memory_id INTEGER PRIMARY KEY,
                content TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE poc_memories_fts
                USING fts5(memory_id UNINDEXED, content);
            """
        )

    try:
        write_started = time.perf_counter()
        with connection:
            for index in range(records):
                content = _synthetic_content(index)
                cursor = connection.execute(
                    "INSERT INTO poc_memories(content) VALUES (?)", (content,)
                )
                connection.execute(
                    "INSERT INTO poc_memories_fts(memory_id, content) VALUES (?, ?)",
                    (int(cursor.lastrowid), content),
                )
        write_seconds = time.perf_counter() - write_started

        search_started = time.perf_counter()
        successful_queries = 0
        for index in range(queries):
            topic = f"topic{index % 20:02d}"
            row = connection.execute(
                "SELECT count(*) FROM poc_memories_fts WHERE poc_memories_fts MATCH ?",
                (topic,),
            ).fetchone()
            if row is not None and int(row[0]) > 0:
                successful_queries += 1
        search_seconds = time.perf_counter() - search_started

        backup_started = time.perf_counter()
        if cipher_database is not None:
            cipher_database.backup_to(
                backup_path,
                backup_key=secrets.token_urlsafe(48),
            )
        else:
            descriptor, staging_name = tempfile.mkstemp(
                prefix=f".{backup_path.name}.", suffix=".partial", dir=backup_path.parent
            )
            os.close(descriptor)
            staging_path = Path(staging_name)
            try:
                destination = sqlite3.connect(str(staging_path))
                try:
                    connection.backup(destination)
                finally:
                    destination.close()

                validation = sqlite3.connect(str(staging_path))
                try:
                    row = validation.execute("PRAGMA integrity_check").fetchone()
                    if row is None or row[0] != "ok":
                        raise RuntimeError("SQLite backup validation failed")
                finally:
                    validation.close()
                os.replace(staging_path, backup_path)
            finally:
                staging_path.unlink(missing_ok=True)
        backup_seconds = time.perf_counter() - backup_started
    finally:
        if cipher_database is not None:
            cipher_database.close()
        if plain_connection is not None:
            plain_connection.close()

    return {
        "write_seconds": write_seconds,
        "search_seconds": search_seconds,
        "backup_seconds": backup_seconds,
        "database_bytes": path.stat().st_size,
        "backup_bytes": backup_path.stat().st_size,
        "successful_queries": successful_queries,
        "sqlite_version": sqlite3.sqlite_version,
        "cipher_version": cipher_version,
    }


def _synthetic_content(index: int) -> str:
    return f"memory{index:05d} topic{index % 20:02d} " + (
        "synthetic private payload token " * 24
    )
