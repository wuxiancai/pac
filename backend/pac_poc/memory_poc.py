from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True)
class MemoryMatch:
    memory_id: str
    content: str
    claim_type: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class MemoryVersion:
    memory_id: str
    content: str
    claim_type: str
    observed_at: str
    status: str


class MemoryStore:
    """Disposable in-memory SQLite/FTS5 contract POC; not the product database."""

    def __init__(self) -> None:
        self._db = sqlite3.connect(":memory:")
        self._db.row_factory = sqlite3.Row
        try:
            self._db.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE memories (
                    memory_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    claim_type TEXT NOT NULL CHECK (claim_type IN (
                        'user_confirmed_fact', 'inference', 'event'
                    )),
                    observed_at TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN (
                        'active', 'superseded', 'deleted'
                    )),
                    supersedes_memory_id TEXT REFERENCES memories(memory_id)
                );
                CREATE TABLE memory_sources (
                    memory_id TEXT NOT NULL REFERENCES memories(memory_id),
                    source_id TEXT NOT NULL,
                    PRIMARY KEY (memory_id, source_id)
                );
                CREATE VIRTUAL TABLE memory_fts USING fts5(memory_id UNINDEXED, content);
                CREATE TABLE memory_embeddings (
                    memory_id TEXT NOT NULL REFERENCES memories(memory_id),
                    model_id TEXT NOT NULL,
                    vector BLOB NOT NULL,
                    PRIMARY KEY (memory_id, model_id)
                );
                """
            )
        except sqlite3.OperationalError as exc:
            self._db.close()
            raise RuntimeError("SQLite FTS5 is required for this POC") from exc

    def remember(
        self,
        *,
        content: str,
        source_id: str,
        claim_type: str,
        observed_at: str,
    ) -> str:
        if not content.strip() or not source_id.strip() or not observed_at.strip():
            raise ValueError("content, source_id, and observed_at are required")
        memory_id = f"mem_{uuid4().hex}"
        with self._db:
            self._db.execute(
                "INSERT INTO memories VALUES (?, ?, ?, ?, 'active', NULL)",
                (memory_id, content, claim_type, observed_at),
            )
            self._db.execute(
                "INSERT INTO memory_sources VALUES (?, ?)", (memory_id, source_id)
            )
            self._db.execute(
                "INSERT INTO memory_fts VALUES (?, ?)",
                (memory_id, _fts_text(content)),
            )
        return memory_id

    def correct(
        self,
        *,
        old_memory_id: str,
        content: str,
        source_id: str,
        claim_type: str,
        observed_at: str,
    ) -> str:
        with self._db:
            old = self._db.execute(
                "SELECT 1 FROM memories WHERE memory_id = ? AND status = 'active'",
                (old_memory_id,),
            ).fetchone()
            if old is None:
                raise LookupError(f"no active memory: {old_memory_id}")
            self._db.execute(
                "UPDATE memories SET status = 'superseded' WHERE memory_id = ?",
                (old_memory_id,),
            )
            self._db.execute("DELETE FROM memory_fts WHERE memory_id = ?", (old_memory_id,))
            self._db.execute(
                "DELETE FROM memory_embeddings WHERE memory_id = ?", (old_memory_id,)
            )
            new_id = f"mem_{uuid4().hex}"
            self._db.execute(
                "INSERT INTO memories VALUES (?, ?, ?, ?, 'active', ?)",
                (new_id, content, claim_type, observed_at, old_memory_id),
            )
            self._db.execute("INSERT INTO memory_sources VALUES (?, ?)", (new_id, source_id))
            self._db.execute(
                "INSERT INTO memory_fts VALUES (?, ?)", (new_id, _fts_text(content))
            )
        return new_id

    def search(self, query: str) -> list[MemoryMatch]:
        terms = [term.replace('"', '""') for term in _fts_terms(query)]
        if not terms:
            return []
        match_query = " AND ".join(f'"{term}"' for term in terms)
        rows = self._db.execute(
            """
            SELECT m.memory_id, m.content, m.claim_type,
                   GROUP_CONCAT(s.source_id, char(31)) AS source_ids
            FROM memory_fts f
            JOIN memories m ON m.memory_id = f.memory_id
            JOIN memory_sources s ON s.memory_id = m.memory_id
            WHERE memory_fts MATCH ? AND m.status = 'active'
            GROUP BY m.memory_id ORDER BY m.observed_at DESC
            """,
            (match_query,),
        ).fetchall()
        return [
            MemoryMatch(
                memory_id=row["memory_id"],
                content=row["content"],
                claim_type=row["claim_type"],
                source_ids=tuple(row["source_ids"].split(chr(31))),
            )
            for row in rows
        ]

    def history(self, memory_id: str) -> list[MemoryVersion]:
        rows = self._db.execute(
            """
            WITH RECURSIVE chain(memory_id) AS (
                SELECT memory_id FROM memories WHERE memory_id = ?
                UNION ALL
                SELECT m.memory_id FROM memories m JOIN chain c
                    ON m.supersedes_memory_id = c.memory_id
            )
            SELECT memory_id, content, claim_type, observed_at, status
            FROM memories WHERE memory_id IN (SELECT memory_id FROM chain)
            ORDER BY observed_at
            """,
            (memory_id,),
        ).fetchall()
        return [MemoryVersion(**dict(row)) for row in rows]

    def delete(self, memory_id: str) -> None:
        with self._db:
            cursor = self._db.execute(
                "UPDATE memories SET status = 'deleted' WHERE memory_id = ?",
                (memory_id,),
            )
            if cursor.rowcount == 0:
                raise LookupError(f"unknown memory: {memory_id}")
            self._db.execute("DELETE FROM memory_fts WHERE memory_id = ?", (memory_id,))
            self._db.execute("DELETE FROM memory_embeddings WHERE memory_id = ?", (memory_id,))

    def add_embedding(self, memory_id: str, *, model_id: str, vector: tuple[float, ...]) -> None:
        if not vector:
            raise ValueError("embedding vector must not be empty")
        payload = ",".join(str(value) for value in vector).encode("ascii")
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO memory_embeddings VALUES (?, ?, ?)",
                (memory_id, model_id, payload),
            )

    def embedding_count(self, memory_id: str) -> int:
        row = self._db.execute(
            "SELECT COUNT(*) AS count FROM memory_embeddings WHERE memory_id = ?",
            (memory_id,),
        ).fetchone()
        return int(row["count"])

    def backup_bytes(self) -> bytes:
        return self._db.serialize()

    @classmethod
    def restore_bytes(cls, backup: bytes) -> MemoryStore:
        store = cls()
        try:
            store._db.deserialize(backup)
        except sqlite3.DatabaseError:
            store.close()
            raise
        store._db.row_factory = sqlite3.Row
        return store

    def close(self) -> None:
        self._db.close()


def _fts_text(text: str) -> str:
    return " ".join(_fts_terms(text))


def _fts_terms(text: str) -> list[str]:
    terms: list[str] = []
    cjk_run = ""
    latin_run = ""

    def flush_cjk() -> None:
        nonlocal cjk_run
        if cjk_run:
            terms.extend(
                cjk_run[index : index + 2]
                for index in range(max(1, len(cjk_run) - 1))
            )
            cjk_run = ""

    def flush_latin() -> None:
        nonlocal latin_run
        if latin_run:
            terms.append(latin_run)
            latin_run = ""

    for char in text:
        if _is_cjk(char):
            flush_latin()
            cjk_run += char
        elif char.isalnum() or char == "_":
            flush_cjk()
            latin_run += char
        else:
            flush_cjk()
            flush_latin()
    flush_cjk()
    flush_latin()
    return terms


def _is_cjk(char: str) -> bool:
    codepoint = ord(char)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
    )
