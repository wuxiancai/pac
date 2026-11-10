from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast


SUPPORTED_CANDIDATE_MODELS = frozenset(
    {"sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"}
)


class EmbeddingProvider(Protocol):
    model_id: str

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]: ...


class _EmbeddingEngine(Protocol):
    def embed(self, texts: list[str]) -> Iterable[Sequence[float]]: ...


class FastEmbedCandidate:
    """Opt-in local FastEmbed model candidate with an explicit project cache path."""

    def __init__(
        self,
        *,
        model_id: str,
        cache_dir: Path,
        allow_download: bool = False,
        engine_factory: Callable[..., object] | None = None,
    ) -> None:
        if model_id not in SUPPORTED_CANDIDATE_MODELS:
            raise ValueError(f"embedding candidate is not registered: {model_id}")
        self.model_id = model_id
        self.cache_dir = self._project_cache_path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        if engine_factory is None:
            from fastembed import TextEmbedding

            engine_factory = TextEmbedding
        self._engine = cast(
            _EmbeddingEngine,
            engine_factory(
                model_name=model_id,
                cache_dir=str(self.cache_dir),
                local_files_only=not allow_download,
                threads=2,
            ),
        )

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("embedding input must contain non-empty text")
        raw_vectors = list(self._engine.embed(texts))
        if len(raw_vectors) != len(texts):
            raise ValueError("embedding provider returned an unexpected vector count")
        vectors = [tuple(float(value) for value in vector) for vector in raw_vectors]
        if not vectors or not vectors[0]:
            raise ValueError("embedding provider returned an empty vector")
        dimension = len(vectors[0])
        if any(len(vector) != dimension for vector in vectors):
            raise ValueError("embedding provider returned inconsistent vector dimensions")
        if any(not math.isfinite(value) for vector in vectors for value in vector):
            raise ValueError("embedding provider returned a non-finite vector value")
        return vectors

    @staticmethod
    def _project_cache_path(cache_dir: Path) -> Path:
        backend_root = Path(__file__).resolve().parents[1]
        candidate = cache_dir if cache_dir.is_absolute() else backend_root / cache_dir
        resolved = candidate.resolve()
        allowed_root = (backend_root / ".poc-data").resolve()
        try:
            resolved.relative_to(allowed_root)
        except ValueError as exc:
            raise ValueError("embedding model cache must stay under backend/.poc-data") from exc
        return resolved


@dataclass(frozen=True)
class EmbeddingMatch:
    source_id: str
    content: str
    score: float


@dataclass(frozen=True)
class _IndexedEmbedding:
    source_id: str
    content: str
    vector: tuple[float, ...]


class LocalEmbeddingSearch:
    """In-memory synthetic-corpus retrieval probe; no persistence or network fallback."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider
        self._entries: list[_IndexedEmbedding] = []

    def add(self, content: str, *, source_id: str) -> None:
        if not content.strip() or not source_id.strip():
            raise ValueError("content and source_id are required")
        vector = self._provider.embed([content])[0]
        self._entries.append(_IndexedEmbedding(source_id, content, vector))

    def search(self, query: str, *, limit: int = 5) -> list[EmbeddingMatch]:
        if not query.strip():
            return []
        if limit <= 0:
            raise ValueError("limit must be positive")
        query_vector = self._provider.embed([query])[0]
        scored = [
            EmbeddingMatch(
                source_id=entry.source_id,
                content=entry.content,
                score=cosine_similarity(query_vector, entry.vector),
            )
            for entry in self._entries
        ]
        return sorted(scored, key=lambda match: match.score, reverse=True)[:limit]

    def delete_source(self, source_id: str) -> int:
        previous_count = len(self._entries)
        self._entries = [entry for entry in self._entries if entry.source_id != source_id]
        return previous_count - len(self._entries)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or len(left) != len(right):
        raise ValueError("embedding vector dimensions must match and be non-empty")
    left_norm = math.sqrt(math.fsum(value * value for value in left))
    right_norm = math.sqrt(math.fsum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("cosine similarity does not accept a zero vector")
    return math.fsum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )
