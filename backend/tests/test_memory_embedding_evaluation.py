from __future__ import annotations

from scripts.evaluate_memory_embedding_poc import evaluate_memory_embedding


class FixtureEmbeddingProvider:
    model_id = "fixture-memory-embedding"

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        vectors = {
            "用户偏好简洁直接的中文回答": (1.0, 0.0),
            "用户常用的编程语言是 Swift": (0.0, 1.0),
            "周末喜欢爬山和户外徒步": (0.9, 0.1),
            "用户的工作地点在上海": (-1.0, 0.0),
            "更希望以中文简短回复": (0.99, 0.01),
            "macOS 应用通常用什么语言开发": (0.01, 0.99),
            "周末会做什么户外运动": (0.8, 0.2),
            "现在工作的城市": (-0.99, 0.01),
        }
        return [vectors[text] for text in texts]


def test_memory_embedding_evaluation_reports_only_aggregate_synthetic_results() -> None:
    result = evaluate_memory_embedding(FixtureEmbeddingProvider())

    assert result == {
        "model_id": "fixture-memory-embedding",
        "memory_count": 4,
        "query_count": 4,
        "top1_matches": 4,
        "source_evidence_returned": True,
        "query_or_memory_text_logged": False,
    }
