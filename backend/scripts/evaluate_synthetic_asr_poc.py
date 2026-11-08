from __future__ import annotations

import argparse
import json
import wave
from array import array
from pathlib import Path
from typing import Any

from pac_poc.asr import AudioFrame, LocalStreamingASR, SherpaOnnxRecognizer, resolve_model_files
from pac_poc.asr_evaluation import character_error_rate, score_asr_samples


def load_manifest(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("samples"), list):
        raise ValueError("manifest must contain a samples array")
    records: list[dict[str, str]] = []
    for sample in payload["samples"]:
        if (
            not isinstance(sample, dict)
            or not isinstance(sample.get("audio"), str)
            or not isinstance(sample.get("reference"), str)
        ):
            raise ValueError("each sample must contain audio and reference strings")
        records.append({"audio": sample["audio"], "reference": sample["reference"]})
    if not records:
        raise ValueError("manifest must contain at least one sample")
    return records


def resolve_sample_audio(manifest_path: Path, audio_name: str) -> Path:
    root = manifest_path.resolve().parent
    candidate = (root / audio_name).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("manifest audio paths must stay beside the explicit manifest") from exc
    if not candidate.is_file():
        raise FileNotFoundError("manifest audio file is missing")
    return candidate


def recognize_sample(
    wav_path: Path, recognizer: SherpaOnnxRecognizer, *, tail_ms: int
) -> tuple[str, int, int]:
    with wave.open(str(wav_path), "rb") as source:
        if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (
            16_000,
            1,
            2,
        ):
            raise ValueError("WAV must be mono, 16 kHz, signed PCM16")
        pcm = array("h", source.readframes(source.getnframes()))
    if not pcm:
        raise ValueError("WAV must contain audio")
    pcm.extend([0] * (16_000 * tail_ms // 1_000))
    asr = LocalStreamingASR(recognizer, sample_rate_hz=16_000)
    frame_size = 16_000 * 200 // 1_000
    partial_count = 0
    final_texts: list[str] = []
    final_count = 0
    for sequence, offset in enumerate(range(0, len(pcm), frame_size)):
        samples = tuple(sample / 32768.0 for sample in pcm[offset : offset + frame_size])
        event = asr.accept(AudioFrame(sequence, 16_000, samples))
        if event is not None and event.kind == "partial":
            partial_count += 1
        elif event is not None and event.kind == "final":
            final_count += 1
            final_texts.append(event.text)
    if final_count == 0:
        recognizer.reset()
    return "".join(final_texts), partial_count, final_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate explicitly listed synthetic local ASR audio without printing transcripts"
    )
    parser.add_argument("manifest", type=Path, help="Explicit JSON manifest; no directory scanning")
    parser.add_argument("model_dir", type=Path, help="Explicit local sherpa-onnx model directory")
    parser.add_argument("--tail-silence-ms", type=int, default=3_000)
    args = parser.parse_args()
    if args.tail_silence_ms < 0:
        parser.error("tail silence cannot be negative")

    try:
        records = load_manifest(args.manifest)
        model_files = resolve_model_files(args.model_dir)
        results: list[dict[str, Any]] = []
        score_pairs: list[tuple[str, str]] = []
        for index, record in enumerate(records, 1):
            audio_path = resolve_sample_audio(args.manifest, record["audio"])
            recognizer = SherpaOnnxRecognizer(**model_files.__dict__)
            hypothesis, partial_count, final_count = recognize_sample(
                audio_path,
                recognizer,
                tail_ms=args.tail_silence_ms,
            )
            reference = record["reference"]
            score_pairs.append((reference, hypothesis))
            results.append(
                {
                    "sample": index,
                    "final_count": final_count,
                    "partial_count": partial_count,
                    "cer": character_error_rate(reference, hypothesis),
                }
            )
        score = score_asr_samples(score_pairs)
    except (OSError, ValueError, wave.Error, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    print(
        json.dumps(
            {
                "synthetic_samples": score.sample_count,
                "reference_chars": score.reference_chars,
                "character_errors": score.character_errors,
                "weighted_cer": score.weighted_cer,
                "samples_with_final": sum(result["final_count"] > 0 for result in results),
                "total_partials": sum(result["partial_count"] for result in results),
                "tail_silence_ms": args.tail_silence_ms,
                "transcripts_written": False,
                "samples": results,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if score.sample_count > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
