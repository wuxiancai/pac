from __future__ import annotations

import argparse
import json
import resource
import sys
import time
import unicodedata
import wave
from array import array
from pathlib import Path

import numpy as np
import sherpa_onnx


DEFAULT_MODEL_DIR = Path(
    ".poc-data/models/sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25"
)
DEFAULT_FILES = (
    "raokouling.wav",
    "f1_noise.wav",
    "codeswitch.wav",
    "qiqiu1.wav",
    "noise1-en.wav",
)


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return "".join(
        char
        for char in normalized
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    )


def _edit_distance(reference: str, hypothesis: str) -> int:
    previous = list(range(len(hypothesis) + 1))
    for ref_index, ref_char in enumerate(reference, start=1):
        current = [ref_index]
        for hyp_index, hyp_char in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[hyp_index] + 1,
                    previous[hyp_index - 1] + (ref_char != hyp_char),
                )
            )
        previous = current
    return previous[-1]


def _read_references(path: Path) -> dict[str, str]:
    references: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        filename, text = line.split(" ", maxsplit=1)
        references[filename] = text
    return references


def _read_audio(path: Path) -> tuple[int, np.ndarray, float]:
    with wave.open(str(path), "rb") as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise ValueError(f"expected mono PCM16 audio: {path.name}")
        sample_rate = source.getframerate()
        frame_count = source.getnframes()
        pcm = array("h", source.readframes(frame_count))
    if not pcm or pcm.itemsize != 2:
        raise ValueError(f"expected non-empty PCM16 audio: {path.name}")
    samples = np.asarray(pcm, dtype=np.float32) / 32768.0
    return sample_rate, samples, frame_count / sample_rate


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline Qwen3-ASR evaluation using the model's bundled WAV/reference set"
    )
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--files", nargs="+", default=list(DEFAULT_FILES))
    parser.add_argument("--num-threads", type=int, default=4)
    parser.add_argument("--max-total-len", type=int, default=4096)
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    args = parser.parse_args()

    model_dir = args.model_dir.resolve()
    test_dir = model_dir / "test_wavs"
    references = _read_references(test_dir / "transcript.txt")
    for filename in args.files:
        if Path(filename).name != filename or filename not in references:
            parser.error(f"unknown bundled test WAV: {filename}")
        if not (test_dir / filename).is_file():
            parser.error(f"bundled test WAV is missing: {filename}")

    load_start = time.perf_counter()
    recognizer = sherpa_onnx.OfflineRecognizer.from_qwen3_asr(
        conv_frontend=str(model_dir / "conv_frontend.onnx"),
        encoder=str(model_dir / "encoder.int8.onnx"),
        decoder=str(model_dir / "decoder.int8.onnx"),
        tokenizer=str(model_dir / "tokenizer"),
        num_threads=args.num_threads,
        sample_rate=16_000,
        feature_dim=128,
        provider="cpu",
        max_total_len=args.max_total_len,
        max_new_tokens=args.max_new_tokens,
    )
    model_load_seconds = time.perf_counter() - load_start

    rows: list[dict[str, object]] = []
    reference_char_count = 0
    total_edits = 0
    for filename in args.files:
        sample_rate, samples, audio_seconds = _read_audio(test_dir / filename)
        stream = recognizer.create_stream()
        stream.accept_waveform(sample_rate, samples)
        decode_start = time.perf_counter()
        recognizer.decode_stream(stream)
        decode_seconds = time.perf_counter() - decode_start

        reference = _normalize(references[filename])
        hypothesis = _normalize(stream.result.text)
        edits = _edit_distance(reference, hypothesis)
        reference_char_count += len(reference)
        total_edits += edits
        rows.append(
            {
                "file": filename,
                "sample_rate_hz": sample_rate,
                "audio_seconds": round(audio_seconds, 2),
                "decode_seconds": round(decode_seconds, 3),
                "rtf": round(decode_seconds / audio_seconds, 4),
                "reference_chars": len(reference),
                "hypothesis_chars": len(hypothesis),
                "cer": round(edits / max(1, len(reference)), 4),
            }
        )

    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform != "darwin":
        peak_rss *= 1024
    print(
        json.dumps(
            {
                "model": model_dir.name,
                "sherpa_onnx_version": getattr(sherpa_onnx, "__version__", "unknown"),
                "inference_mode": "offline_file_decode",
                "language_mode": "automatic",
                "provider": "cpu",
                "num_threads": args.num_threads,
                "model_load_seconds": round(model_load_seconds, 3),
                "peak_rss_bytes": int(peak_rss),
                "weighted_cer": round(
                    total_edits / max(1, reference_char_count), 4
                ),
                "results": rows,
                "transcript_text_logged": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
