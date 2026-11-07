from __future__ import annotations

import argparse
from pathlib import Path

from pac_poc.embedding_poc import FastEmbedCandidate, LocalEmbeddingSearch


MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

MEMORIES = (
    ("用户偏好简洁直接的中文回答", "fixture:language-preference"),
    ("用户常用的编程语言是 Swift", "fixture:programming-language"),
    ("周末喜欢爬山和户外徒步", "fixture:weekend-hobby"),
    ("用户的工作地点在上海", "fixture:work-city"),
)

QUERIES = (
    ("更希望以中文简短回复", "fixture:language-preference"),
    ("macOS 应用一般用什么语言开发", "fixture:programming-language"),
    ("周末会做什么户外运动", "fixture:weekend-hobby"),
    ("现在工作的城市", "fixture:work-city"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a synthetic local embedding retrieval POC")
    parser.add_argument(
        "--download-model",
        action="store_true",
        help="explicitly download the public candidate model into backend/.poc-data",
    )
    args = parser.parse_args()

    backend = Path(__file__).resolve().parents[1]
    provider = FastEmbedCandidate(
        model_id=MODEL_ID,
        cache_dir=backend / ".poc-data" / "embedding-cache",
        allow_download=args.download_model,
    )
    search = LocalEmbeddingSearch(provider)
    for content, source_id in MEMORIES:
        search.add(content, source_id=source_id)

    passed = 0
    for query, expected_source in QUERIES:
        matches = search.search(query, limit=1)
        actual_source = matches[0].source_id if matches else "none"
        is_match = actual_source == expected_source
        passed += int(is_match)
        print(f"expected={expected_source} actual={actual_source} match={str(is_match).lower()}")

    print(f"model={MODEL_ID} synthetic_queries={len(QUERIES)} top1_matches={passed}")
    return 0 if passed == len(QUERIES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
