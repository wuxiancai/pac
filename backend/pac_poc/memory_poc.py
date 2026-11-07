from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from uuid import uuid4

from .embedding_poc import EmbeddingProvider, cosine_similarity


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


@dataclass(frozen=True)
class SemanticMemoryMatch:
    memory_id: str
    content: str
    claim_type: str
    source_ids: tuple[str, ...]
    score: float


class MemoryStore:
    """Disposable in-memory SQLite/FTS5 contract POC; not the product database."""

    def __init__(self, *, embedding_provider: EmbeddingProvider | None = None) -> None:
        self._embedding_provider = embedding_provider
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
        vector = self._embed(content)
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
            if vector is not None:
                self._insert_embedding(memory_id, vector)
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
        if not content.strip() or not source_id.strip() or not observed_at.strip():
            raise ValueError("content, source_id, and observed_at are required")
        old = self._db.execute(
            "SELECT 1 FROM memories WHERE memory_id = ? AND status = 'active'",
            (old_memory_id,),
        ).fetchone()
        if old is None:
            raise LookupError(f"no active memory: {old_memory_id}")
        vector = self._embed(content)
        new_id = f"mem_{uuid4().hex}"
        with self._db:
            self._db.execute(
                "UPDATE memories SET status = 'superseded' WHERE memory_id = ?",
                (old_memory_id,),
            )
            self._db.execute("DELETE FROM memory_fts WHERE memory_id = ?", (old_memory_id,))
            self._db.execute(
                "DELETE FROM memory_embeddings WHERE memory_id = ?", (old_memory_id,)
            )
            self._db.execute(
                "INSERT INTO memories VALUES (?, ?, ?, ?, 'active', ?)",
                (new_id, content, claim_type, observed_at, old_memory_id),
            )
            self._db.execute("INSERT INTO memory_sources VALUES (?, ?)", (new_id, source_id))
            self._db.execute(
                "INSERT INTO memory_fts VALUES (?, ?)", (new_id, _fts_text(content))
            )
            if vector is not None:
                self._insert_embedding(new_id, vector)
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

    def search_semantic(self, query: str, *, limit: int = 5) -> list[SemanticMemoryMatch]:
        if self._embedding_provider is None:
            raise RuntimeError("embedding provider is not configured")
        if not query.strip():
            return []
        if limit <= 0:
            raise ValueError("limit must be positive")
        query_vector = self._embed(query)
        assert query_vector is not None
        rows = self._db.execute(
            """
            SELECT m.memory_id, m.content, m.claim_type, e.vector,
                   GROUP_CONCAT(s.source_id, char(31)) AS source_ids
            FROM memories m
            JOIN memory_embeddings e ON e.memory_id = m.memory_id
            JOIN memory_sources s ON s.memory_id = m.memory_id
            WHERE m.status = 'active' AND e.model_id = ?
            GROUP BY m.memory_id
            """,
            (self._embedding_provider.model_id,),
        ).fetchall()
        matches = [
            SemanticMemoryMatch(
                memory_id=row["memory_id"],
                content=row["content"],
                claim_type=row["claim_type"],
                source_ids=tuple(row["source_ids"].split(chr(31))),
                score=cosine_similarity(query_vector, _decode_vector(row["vector"])),
            )
            for row in rows
        ]
        matches.sort(key=lambda item: (-item.score, item.memory_id))
        return matches[:limit]

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
        payload = _encode_vector(vector)
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
    def restore_bytes(
        cls,
        backup: bytes,
        *,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> MemoryStore:
        store = cls(embedding_provider=embedding_provider)
        try:
            store._db.deserialize(backup)
        except sqlite3.DatabaseError:
            store.close()
            raise
        store._db.row_factory = sqlite3.Row
        return store

    def close(self) -> None:
        self._db.close()

    def _embed(self, content: str) -> tuple[float, ...] | None:
        if self._embedding_provider is None:
            return None
        vectors = self._embedding_provider.embed([content])
        if len(vectors) != 1 or not vectors[0]:
            raise ValueError("embedding provider returned an invalid vector result")
        vector = tuple(float(value) for value in vectors[0])
        if any(not math.isfinite(value) for value in vector):
            raise ValueError("embedding provider returned a non-finite vector value")
        existing = self._db.execute(
            "SELECT vector FROM memory_embeddings WHERE model_id = ? LIMIT 1",
            (self._embedding_provider.model_id,),
        ).fetchone()
        if existing is not None and len(_decode_vector(existing["vector"])) != len(vector):
            raise ValueError("embedding provider returned inconsistent vector dimensions")
        return vector

    def _insert_embedding(self, memory_id: str, vector: tuple[float, ...]) -> None:
        assert self._embedding_provider is not None
        self._db.execute(
            "INSERT OR REPLACE INTO memory_embeddings VALUES (?, ?, ?)",
            (memory_id, self._embedding_provider.model_id, _encode_vector(vector)),
        )


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


def _encode_vector(vector: tuple[float, ...]) -> bytes:
    if not vector or any(not math.isfinite(float(value)) for value in vector):
        raise ValueError("embedding vector must contain finite values")
    return ",".join(str(float(value)) for value in vector).encode("ascii")


def _decode_vector(payload: bytes) -> tuple[float, ...]:
    try:
        vector = tuple(float(value) for value in payload.decode("ascii").split(","))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("stored embedding vector is invalid") from exc
    if not vector or any(not math.isfinite(value) for value in vector):
        raise ValueError("stored embedding vector is invalid")
    return vector
