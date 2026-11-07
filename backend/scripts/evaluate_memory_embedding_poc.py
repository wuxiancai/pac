from __future__ import annotations

import json
from pathlib import Path

from pac_poc.embedding_poc import EmbeddingProvider, FastEmbedCandidate
from pac_poc.memory_poc import MemoryStore


MEMORIES = (
    ("用户偏好简洁直接的中文回答", "fixture:language-preference", "user_confirmed_fact"),
    ("周末喜欢爬山和户外徒步", "fixture:weekend-hobby", "user_confirmed_fact"),
    ("用户的工作地点在上海", "fixture:work-city", "user_confirmed_fact"),
)

QUERIES = (
    ("更希望以中文简短回复", "fixture:language-preference"),
    ("周末会做什么户外运动", "fixture:weekend-hobby"),
    ("现在工作的城市", "fixture:work-city"),
)


def evaluate_memory_embedding(provider: EmbeddingProvider) -> dict[str, object]:
    store = MemoryStore(embedding_provider=provider)
    try:
        memory_ids: dict[str, str] = {}
        for content, source_id, claim_type in MEMORIES:
            memory_ids[source_id] = store.remember(
                content=content,
                source_id=source_id,
                claim_type=claim_type,
                observed_at="2026-11-07T08:00:00Z",
            )

        top1_matches = 0
        source_evidence_returned = True
        for query, expected_source in QUERIES:
            matches = store.search_semantic(query, limit=1)
            top1_matches += int(bool(matches) and matches[0].source_ids == (expected_source,))
            source_evidence_returned &= bool(matches and matches[0].memory_id == memory_ids[expected_source])

        return {
            "model_id": provider.model_id,
            "memory_count": len(MEMORIES),
            "query_count": len(QUERIES),
            "top1_matches": top1_matches,
            "source_evidence_returned": source_evidence_returned,
            "query_or_memory_text_logged": False,
        }
    finally:
        store.close()


def main() -> int:
    backend = Path(__file__).resolve().parents[1]
    provider = FastEmbedCandidate(
        model_id="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        cache_dir=backend / ".poc-data" / "embedding-cache",
        allow_download=False,
    )
    result = evaluate_memory_embedding(provider)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["top1_matches"] == result["query_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
