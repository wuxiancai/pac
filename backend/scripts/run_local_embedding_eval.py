from __future__ import annotations

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from pac_poc.embedding_poc import FastEmbedCandidate, LocalEmbeddingSearch
from pac_poc.persistence import EncryptedApplicationStore


MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

MEMORIES = (
    ("Prefer concise, direct answers in Simplified Chinese.", "fixture:language-preference"),
    ("常用 Swift 开发 macOS 应用。", "fixture:programming-language"),
    ("On weekends, I enjoy hiking on mountain trails.", "fixture:weekend-hobby"),
    ("用户的工作地点在上海。", "fixture:work-city"),
    ("提醒事项最好提前一天通知。", "fixture:reminder-lead-time"),
    ("I prefer meeting notes with decisions and action items first.", "fixture:meeting-notes"),
    ("只在本机保存私人笔记，不上传到云服务。", "fixture:privacy-boundary"),
    ("The user avoids peanuts because of an allergy.", "fixture:food-allergy"),
    ("工作日通常上午九点开始工作。", "fixture:work-hours"),
    ("For backups, use a separate passphrase for each archive.", "fixture:backup-passphrase"),
    ("用户喜欢听爵士乐，尤其是钢琴三重奏。", "fixture:music-preference"),
    ("On trips, I prefer public transit over renting a car.", "fixture:travel-transport"),
)

# Each pair tests an independently phrased query in Chinese and English.
# This is a small synthetic probe, not a user-data or product acceptance set.
QUERIES = (
    ("回答时用简体中文，尽量简短直接。", "fixture:language-preference", "zh"),
    ("How should replies be phrased and in which language?", "fixture:language-preference", "en"),
    ("Which language is commonly used for the macOS apps?", "fixture:programming-language", "en"),
    ("开发 Mac 软件时常用哪种编程语言？", "fixture:programming-language", "zh"),
    ("周末喜欢去山里走步道。", "fixture:weekend-hobby", "zh"),
    ("What outdoor activity does the user enjoy on days off?", "fixture:weekend-hobby", "en"),
    ("In which city is the workplace located?", "fixture:work-city", "en"),
    ("用户平时在哪个城市上班？", "fixture:work-city", "zh"),
    ("任务到期之前多久提醒比较合适？", "fixture:reminder-lead-time", "zh"),
    ("When should a reminder arrive before its due date?", "fixture:reminder-lead-time", "en"),
    ("What should appear at the top of meeting summaries?", "fixture:meeting-notes", "en"),
    ("会议记录需要优先突出哪些内容？", "fixture:meeting-notes", "zh"),
    ("私人笔记是否可以同步到在线服务？", "fixture:privacy-boundary", "zh"),
    ("Where should private notes be stored?", "fixture:privacy-boundary", "en"),
    ("Which ingredient must be excluded from meals?", "fixture:food-allergy", "en"),
    ("用户对什么食物过敏，饮食上要避开什么？", "fixture:food-allergy", "zh"),
    ("What time does the workday usually begin?", "fixture:work-hours", "en"),
    ("通常几点开始上班？", "fixture:work-hours", "zh"),
    ("每个备份文件是否应该共用同一个密码？", "fixture:backup-passphrase", "zh"),
    ("How should archive passwords be handled?", "fixture:backup-passphrase", "en"),
    ("What style of music does the user like?", "fixture:music-preference", "en"),
    ("空闲时喜欢听哪种音乐？", "fixture:music-preference", "zh"),
    ("How does the user prefer to get around while traveling?", "fixture:travel-transport", "en"),
    ("旅行时更愿意选择什么交通方式？", "fixture:travel-transport", "zh"),
)

# Exact-text controls estimate lexical lookup behavior; they do not simulate
# natural-language search quality and are reported separately.
LEXICAL_CONTROL_QUERIES = tuple(
    (content, source_id) for content, source_id in MEMORIES
)

# These synthetic queries deliberately have no relevant item in MEMORIES.
NEGATIVE_QUERIES = (
    ("如何清洁咖啡机的水垢？", "zh"),
    ("Which planet has the largest ring system?", "en"),
    ("如何给阳台上的番茄施肥？", "zh"),
    ("What is the boiling point of mercury?", "en"),
    ("怎么修理漏水的浴室水龙头？", "zh"),
    ("Who painted The Starry Night?", "en"),
    ("如何挑选适合观星的望远镜？", "zh"),
    ("What is the deepest ocean trench?", "en"),
    ("怎样制作发酵酸面包？", "zh"),
    ("How many bones are in an adult human hand?", "en"),
    ("如何给自行车后拨变速器调试？", "zh"),
    ("Which mineral gives amethyst its purple color?", "en"),
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
    top1 = top3 = fts_top1 = fts_top3 = 0
    lexical_embedding_top1 = lexical_fts_top1 = 0
    negative_embedding_any = negative_fts_any = 0
    positive_best_scores: list[float] = []
    negative_best_scores: list[float] = []
    language_counts = {"zh": [0, 0], "en": [0, 0]}
    with TemporaryDirectory(prefix="embedding-eval-", dir=backend / ".poc-data") as temp_dir:
        fts_store = EncryptedApplicationStore(
            path=Path(temp_dir) / "synthetic-eval.db", key=b"E" * 32
        )
        fts_store.open()
        try:
            source_by_memory_id: dict[str, str] = {}
            for content, source_id in MEMORIES:
                search.add(content, source_id=source_id)
                row = fts_store.create_confirmed_memory(
                    subject=source_id,
                    content=content,
                    category="fact",
                )
                source_by_memory_id[str(row["id"])] = source_id

            for query, expected_source, language in QUERIES:
                matches = search.search(query, limit=3)
                actual_source = matches[0].source_id if matches else "none"
                if matches:
                    positive_best_scores.append(matches[0].score)
                lexical_matches = fts_store.search_memories(query, limit=3)
                lexical_sources = {
                    source_by_memory_id[str(match["id"])] for match in lexical_matches
                }
                is_top1 = actual_source == expected_source
                is_top3 = any(match.source_id == expected_source for match in matches)
                is_fts_top1 = bool(lexical_matches) and (
                    source_by_memory_id[str(lexical_matches[0]["id"])] == expected_source
                )
                is_fts_top3 = expected_source in lexical_sources
                top1 += int(is_top1)
                top3 += int(is_top3)
                fts_top1 += int(is_fts_top1)
                fts_top3 += int(is_fts_top3)
                language_counts[language][0] += int(is_top1)
                language_counts[language][1] += int(is_top3)
                print(
                    f"lang={language} expected={expected_source} actual={actual_source} "
                    f"embedding_top1={str(is_top1).lower()} embedding_top3={str(is_top3).lower()} "
                    f"fts_top1={str(is_fts_top1).lower()} fts_top3={str(is_fts_top3).lower()}"
                )

            for query, expected_source in LEXICAL_CONTROL_QUERIES:
                matches = search.search(query, limit=1)
                lexical_matches = fts_store.search_memories(query, limit=1)
                lexical_embedding_top1 += int(
                    bool(matches) and matches[0].source_id == expected_source
                )
                if matches:
                    positive_best_scores.append(matches[0].score)
                lexical_fts_top1 += int(
                    bool(lexical_matches)
                    and source_by_memory_id[str(lexical_matches[0]["id"])] == expected_source
                )

            for query, _language in NEGATIVE_QUERIES:
                matches = search.search(query, limit=3)
                lexical_matches = fts_store.search_memories(query, limit=3)
                negative_embedding_any += int(bool(matches))
                negative_fts_any += int(bool(lexical_matches))
                negative_best_scores.append(matches[0].score if matches else 0.0)
        finally:
            fts_store.close()
    print(
        f"model={MODEL_ID} synthetic_memories={len(MEMORIES)} "
        f"synthetic_queries={len(QUERIES)} embedding_top1={top1}/{len(QUERIES)} "
        f"embedding_top3={top3}/{len(QUERIES)} fts_top1={fts_top1}/{len(QUERIES)} "
        f"fts_top3={fts_top3}/{len(QUERIES)} zh_embedding_top1={language_counts['zh'][0]}/12 "
        f"en_embedding_top1={language_counts['en'][0]}/12 "
        f"lexical_controls={len(LEXICAL_CONTROL_QUERIES)} "
        f"lexical_embedding_top1={lexical_embedding_top1}/{len(LEXICAL_CONTROL_QUERIES)} "
        f"lexical_fts_top1={lexical_fts_top1}/{len(LEXICAL_CONTROL_QUERIES)} "
        f"negative_queries={len(NEGATIVE_QUERIES)} "
        f"embedding_any={negative_embedding_any}/{len(NEGATIVE_QUERIES)} "
        f"fts_any={negative_fts_any}/{len(NEGATIVE_QUERIES)} "
        f"embedding_positive_best_score_min={min(positive_best_scores, default=0.0):.4f} "
        f"embedding_negative_best_score_min={min(negative_best_scores, default=0.0):.4f} "
        f"embedding_negative_best_score_max={max(negative_best_scores, default=0.0):.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
