from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from evaluate_synthetic_asr_poc import (
    load_manifest,
    recognize_sample,
    resolve_sample_audio,
)
from pac_poc.asr import SherpaOnnxRecognizer, resolve_model_files


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TTS_PACKAGE = PROJECT_ROOT / "poc" / "macos-audio"
PLAY_CONFIRMATION = "PLAY FINAL LOCALLY"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run one explicitly listed WAV through local streaming ASR, "
            "then optionally speak its final text with AVSpeechSynthesizer"
        )
    )
    parser.add_argument("manifest", type=Path, help="Explicit synthetic audio manifest")
    parser.add_argument("model_dir", type=Path, help="Local sherpa-onnx streaming model")
    parser.add_argument("--sample", type=int, default=1, help="One-based manifest sample index")
    parser.add_argument("--tail-silence-ms", type=int, default=3_000)
    args = parser.parse_args()

    if args.sample < 1 or args.tail_silence_ms < 0:
        parser.error("sample must be positive and tail silence cannot be negative")
    if not sys.stdin.isatty():
        print("需要交互式终端确认本机朗读；未启动麦克风或 TTS。", file=sys.stderr)
        return 2

    try:
        records = load_manifest(args.manifest)
        if args.sample > len(records):
            raise ValueError("sample index exceeds manifest size")
        wav_path = resolve_sample_audio(args.manifest, records[args.sample - 1]["audio"])
        model_files = resolve_model_files(args.model_dir)
        recognizer = SherpaOnnxRecognizer(**model_files.__dict__)
        final_text, partial_count, final_count = recognize_sample(
            wav_path,
            recognizer,
            tail_ms=args.tail_silence_ms,
        )
    except (OSError, ValueError) as exc:
        print(f"ASR/TTS POC failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"本机 ASR 完成：sample={args.sample} partials={partial_count} "
        f"finals={final_count} final_chars={len(final_text)}。"
    )
    if final_count == 0 or not final_text.strip():
        print("没有可朗读的 final；未启动 TTS。", file=sys.stderr)
        return 1

    print("下一步会通过 macOS AVSpeechSynthesizer 本机朗读所选音频的 ASR final；不会上传或保存文本。")
    try:
        confirmation = input(f"确认仅在本机朗读此 final，请输入 `{PLAY_CONFIRMATION}`：")
    except EOFError:
        print("未获确认；未启动 TTS。", file=sys.stderr)
        return 2
    if confirmation != PLAY_CONFIRMATION:
        print("未获确认；未启动 TTS。")
        return 2

    result = subprocess.run(
        ["swift", "run", "tts-interrupt-poc", "--wait-for-completion", final_text],
        cwd=TTS_PACKAGE,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0 or "playback_completed=true speaking=false" not in result.stdout:
        print("本机 TTS 未确认正常完成；文本未写入文件。", file=sys.stderr)
        return 1
    print("ASR→TTS 链路完成：playback_completed=true speaking=false；transcript_saved=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
