from __future__ import annotations

from pathlib import Path

import sqlcipher3.dbapi2 as sqlcipher
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL


class SQLCipherPOCError(RuntimeError):
    """A safe, non-secret-bearing error from the temporary SQLCipher POC."""


class SQLCipherFTSDatabase:
    """Temporary encrypted SQLite/FTS5 POC; never used by product repositories."""

    def __init__(self, *, path: Path, key: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._key = self._validate_key(key)
        self._connection = self._open_connection(path, self._key)
        try:
            self._connection.executescript(
                """
                CREATE TABLE poc_memories (
                    memory_id INTEGER PRIMARY KEY,
                    content TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE poc_memories_fts
                    USING fts5(memory_id UNINDEXED, content);
                """
            )
            self._connection.commit()
        except sqlcipher.DatabaseError as exc:
            self._connection.close()
            raise SQLCipherPOCError("unable to initialize encrypted FTS5 database") from exc

    @classmethod
    def open_existing(cls, *, path: Path, key: str) -> SQLCipherFTSDatabase:
        if not path.is_file():
            raise SQLCipherPOCError("encrypted database does not exist")
        instance = cls.__new__(cls)
        instance._path = path
        instance._key = cls._validate_key(key)
        instance._connection = cls._open_connection(path, instance._key)
        return instance

    @property
    def cipher_version(self) -> str:
        row = self._connection.execute("PRAGMA cipher_version").fetchone()
        return str(row[0]) if row and row[0] else ""

    def add(self, content: str) -> int:
        if not content.strip():
            raise ValueError("memory content must not be empty")
        with self._connection:
            cursor = self._connection.execute(
                "INSERT INTO poc_memories(content) VALUES (?)", (content,)
            )
            memory_id = int(cursor.lastrowid)
            self._connection.execute(
                "INSERT INTO poc_memories_fts(memory_id, content) VALUES (?, ?)",
                (memory_id, content),
            )
        return memory_id

    def search(self, query: str) -> list[str]:
        if not query.strip():
            return []
        rows = self._connection.execute(
            """
            SELECT m.content FROM poc_memories_fts f
            JOIN poc_memories m ON m.memory_id = f.memory_id
            WHERE poc_memories_fts MATCH ? ORDER BY m.memory_id
            """,
            (query,),
        ).fetchall()
        return [str(row[0]) for row in rows]

    def integrity_check(self) -> str:
        row = self._connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else ""

    @property
    def page_count(self) -> int:
        row = self._connection.execute("PRAGMA page_count").fetchone()
        return int(row[0]) if row else 0

    def enable_wal_for_poc(self) -> str:
        try:
            row = self._connection.execute("PRAGMA journal_mode = WAL").fetchone()
        except sqlcipher.DatabaseError as exc:
            raise SQLCipherPOCError("unable to enable WAL for SQLCipher POC") from exc
        mode = str(row[0]).lower() if row and row[0] else ""
        if mode != "wal":
            raise SQLCipherPOCError("SQLCipher POC did not enter WAL mode")
        return mode

    def checkpoint_wal_for_poc(self, mode: str = "PASSIVE") -> tuple[int, int, int]:
        normalized_mode = mode.upper()
        if normalized_mode not in {"PASSIVE", "FULL", "RESTART", "TRUNCATE"}:
            raise ValueError("unsupported WAL checkpoint mode")
        try:
            row = self._connection.execute(
                f"PRAGMA wal_checkpoint({normalized_mode})"
            ).fetchone()
        except sqlcipher.DatabaseError as exc:
            raise SQLCipherPOCError("SQLCipher POC WAL checkpoint failed") from exc
        if row is None or len(row) != 3:
            raise SQLCipherPOCError("SQLCipher POC WAL checkpoint returned invalid status")
        return int(row[0]), int(row[1]), int(row[2])

    def set_max_page_count_for_poc(self, pages: int) -> int:
        if pages <= 0:
            raise ValueError("page limit must be positive")
        row = self._connection.execute(f"PRAGMA max_page_count = {pages}").fetchone()
        return int(row[0]) if row else 0

    def backup_to(self, target: Path, *, backup_key: str) -> None:
        if target.resolve() == self._path.resolve():
            raise ValueError("backup target must differ from source database")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise SQLCipherPOCError("encrypted backup destination is unavailable") from exc
        destination = self._open_connection(target, self._validate_key(backup_key))
        try:
            self._connection.backup(destination)
        except sqlcipher.DatabaseError as exc:
            raise SQLCipherPOCError("encrypted backup operation failed") from exc
        finally:
            destination.close()

    def close(self) -> None:
        self._connection.close()

    @staticmethod
    def _validate_key(key: str) -> str:
        if not key:
            raise ValueError("POC key must not be empty")
        return key

    @classmethod
    def _open_connection(cls, path: Path, key: str):
        connection = None
        try:
            connection = sqlcipher.connect(str(path))
            escaped_key = key.replace("'", "''")
            connection.execute(f"PRAGMA key = '{escaped_key}'")
            version_row = connection.execute("PRAGMA cipher_version").fetchone()
            if not version_row or not version_row[0]:
                connection.close()
                raise SQLCipherPOCError("SQLCipher codec is unavailable")
            connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
            return connection
        except SQLCipherPOCError:
            if connection is not None:
                connection.close()
            raise
        except sqlcipher.DatabaseError as exc:
            if connection is not None:
                connection.close()
            raise SQLCipherPOCError("invalid key or database file") from exc


def create_sqlalchemy_compat_engine(*, path: Path, key: str) -> Engine:
    """POC SQLAlchemy engine; the URL object is memory-only and echo is disabled."""
    validated_key = SQLCipherFTSDatabase._validate_key(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    url = URL.create(
        "sqlite+pysqlcipher",
        password=validated_key,
        database=str(path),
    )
    return create_engine(
        url,
        module=sqlcipher,
        echo=False,
    )
