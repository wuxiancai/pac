from __future__ import annotations

import argparse
import json
import resource
import sys
import time
import wave
from array import array
from pathlib import Path

from pac_poc.asr import AudioFrame, LocalStreamingASR, SherpaOnnxRecognizer, resolve_model_files
from pac_poc.asr_benchmark import summarize_measurements


def peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux and the other supported Unix test hosts report KiB.
    return int(value if sys.platform == "darwin" else value * 1024)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure local streaming ASR without printing or saving recognized text"
    )
    parser.add_argument("wav", type=Path, help="Explicit local mono PCM16 WAV at 16 kHz")
    parser.add_argument("model_dir", type=Path, help="Directory containing streaming model files")
    parser.add_argument("--frame-ms", type=int, default=200)
    parser.add_argument("--tail-silence-ms", type=int, default=1600)
    args = parser.parse_args()
    if args.frame_ms <= 0 or args.tail_silence_ms < 0:
        parser.error("frame duration must be positive and tail silence cannot be negative")

    with wave.open(str(args.wav), "rb") as source:
        if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (
            16_000,
            1,
            2,
        ):
            parser.error("WAV must be mono, 16 kHz, signed PCM16")
        audio_seconds = source.getnframes() / source.getframerate()
        pcm = array("h", source.readframes(source.getnframes()))
    if not pcm or pcm.itemsize != 2:
        parser.error("WAV must contain 16-bit PCM audio")

    model_files = resolve_model_files(args.model_dir)
    load_start = time.perf_counter()
    recognizer = SherpaOnnxRecognizer(**model_files.__dict__)
    model_load_seconds = time.perf_counter() - load_start
    asr = LocalStreamingASR(recognizer, sample_rate_hz=16_000)
    pcm.extend([0] * (16_000 * args.tail_silence_ms // 1_000))
    processed_audio_seconds = len(pcm) / 16_000
    frame_size = 16_000 * args.frame_ms // 1_000
    latencies: list[float] = []
    partial_count = 0
    final_count = 0
    inference_start = time.perf_counter()
    cpu_start = time.process_time()

    for sequence, offset in enumerate(range(0, len(pcm), frame_size)):
        samples = tuple(sample / 32768.0 for sample in pcm[offset : offset + frame_size])
        frame_start = time.perf_counter()
        event = asr.accept(AudioFrame(sequence, 16_000, samples))
        latencies.append(time.perf_counter() - frame_start)
        if event is not None:
            if event.kind == "partial":
                partial_count += 1
            elif event.kind == "final":
                final_count += 1

    inference_seconds = time.perf_counter() - inference_start
    cpu_seconds = time.process_time() - cpu_start
    result = summarize_measurements(
        frame_latencies_seconds=latencies,
        audio_seconds=processed_audio_seconds,
        inference_seconds=inference_seconds,
        model_load_seconds=model_load_seconds,
        process_cpu_seconds=cpu_seconds,
        peak_rss_bytes=peak_rss_bytes(),
        partial_count=partial_count,
        final_count=final_count,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
