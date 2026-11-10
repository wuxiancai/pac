from __future__ import annotations

import argparse
from pathlib import Path

from pac_poc.embedding_poc import FastEmbedCandidate, LocalEmbeddingSearch


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

    top1 = top3 = 0
    language_counts = {"zh": [0, 0], "en": [0, 0]}
    for query, expected_source, language in QUERIES:
        matches = search.search(query, limit=3)
        actual_source = matches[0].source_id if matches else "none"
        is_top1 = actual_source == expected_source
        is_top3 = any(match.source_id == expected_source for match in matches)
        top1 += int(is_top1)
        top3 += int(is_top3)
        language_counts[language][0] += int(is_top1)
        language_counts[language][1] += int(is_top3)
        print(
            f"lang={language} expected={expected_source} actual={actual_source} "
            f"top1={str(is_top1).lower()} top3={str(is_top3).lower()}"
        )

    print(
        f"model={MODEL_ID} synthetic_memories={len(MEMORIES)} "
        f"synthetic_queries={len(QUERIES)} top1={top1}/{len(QUERIES)} "
        f"top3={top3}/{len(QUERIES)} zh_top1={language_counts['zh'][0]}/12 "
        f"en_top1={language_counts['en'][0]}/12"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
