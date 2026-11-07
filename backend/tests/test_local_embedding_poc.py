from __future__ import annotations

from pathlib import Path

import pytest

from pac_poc.embedding_poc import (
    FastEmbedCandidate,
    LocalEmbeddingSearch,
    cosine_similarity,
)


class FixtureEmbeddingProvider:
    model_id = "fixture-vector-model"

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        vectors = {
            "hiking": (1.0, 0.0),
            "mountain walk": (0.9, 0.1),
            "swift code": (0.0, 1.0),
        }
        return [vectors[text] for text in texts]


def test_semantic_retrieval_returns_source_and_ranks_by_cosine_similarity() -> None:
    search = LocalEmbeddingSearch(FixtureEmbeddingProvider())
    search.add("hiking", source_id="fixture-hobby")
    search.add("swift code", source_id="fixture-language")

    matches = search.search("mountain walk")

    assert matches[0].source_id == "fixture-hobby"
    assert matches[0].content == "hiking"
    assert matches[0].score > matches[1].score


def test_deleting_source_removes_its_derived_embedding_from_search() -> None:
    search = LocalEmbeddingSearch(FixtureEmbeddingProvider())
    search.add("hiking", source_id="fixture-hobby")
    search.add("swift code", source_id="fixture-language")

    assert search.delete_source("fixture-hobby") == 1
    assert [item.source_id for item in search.search("mountain walk")] == [
        "fixture-language"
    ]


def test_cosine_similarity_rejects_zero_or_different_dimension_vectors() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        cosine_similarity((1.0, 0.0), (1.0,))
    with pytest.raises(ValueError, match="zero vector"):
        cosine_similarity((0.0, 0.0), (1.0, 0.0))


def test_fastembed_candidate_uses_explicit_repo_cache_and_no_download_by_default() -> None:
    class FakeEngine:
        def embed(self, texts: list[str]):
            return [(0.25, 0.75) for _ in texts]

    captured: dict[str, object] = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return FakeEngine()

    candidate = FastEmbedCandidate(
        model_id="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        cache_dir=Path(".poc-data/embedding-cache"),
        engine_factory=factory,
    )

    assert candidate.embed(["测试文本"]) == [(0.25, 0.75)]
    assert captured["cache_dir"].endswith(".poc-data/embedding-cache")
    assert captured["local_files_only"] is True


def test_embedding_candidate_rejects_unapproved_model_identifier() -> None:
    with pytest.raises(ValueError, match="candidate is not registered"):
        FastEmbedCandidate(
            model_id="https://example.com/model",
            cache_dir=Path(".poc-data/embedding-cache"),
        )


def test_embedding_candidate_rejects_cache_locations_outside_poc_data() -> None:
    with pytest.raises(ValueError, match="must stay under backend/.poc-data"):
        FastEmbedCandidate(
            model_id="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            cache_dir=Path("../not-a-project-cache"),
            engine_factory=lambda **kwargs: object(),
        )


def test_embedding_candidate_rejects_wrong_vector_count() -> None:
    class BrokenEngine:
        def embed(self, texts: list[str]):
            return []

    candidate = FastEmbedCandidate(
        model_id="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        cache_dir=Path(".poc-data/embedding-cache"),
        engine_factory=lambda **kwargs: BrokenEngine(),
    )

    with pytest.raises(ValueError, match="vector count"):
        candidate.embed(["测试文本"])
