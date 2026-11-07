from __future__ import annotations

import argparse
import json
import wave
from array import array
from pathlib import Path

from pac_poc.asr import (
    AudioFrame,
    LocalStreamingASR,
    SherpaOnnxRecognizer,
    resolve_model_files,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline sherpa-onnx streaming ASR POC")
    parser.add_argument("wav", type=Path, help="Local mono PCM16 WAV at 16 kHz")
    parser.add_argument("model_dir", type=Path, help="Directory containing the streaming model files")
    parser.add_argument("--frame-ms", type=int, default=200)
    parser.add_argument("--tail-silence-ms", type=int, default=1600)
    args = parser.parse_args()

    if args.frame_ms <= 0 or args.tail_silence_ms < 0:
        parser.error("frame duration must be positive and tail silence cannot be negative")

    with wave.open(str(args.wav), "rb") as source:
        if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (16_000, 1, 2):
            parser.error("WAV must be mono, 16 kHz, signed PCM16")
        samples = array("h", source.readframes(source.getnframes()))

    if not samples:
        parser.error("WAV contains no audio")
    if samples.itemsize != 2:
        parser.error("this host's signed-short representation is not 16-bit")

    model_files = resolve_model_files(args.model_dir)
    recognizer = SherpaOnnxRecognizer(**model_files.__dict__)
    asr = LocalStreamingASR(recognizer, sample_rate_hz=16_000)
    samples.extend([0] * (16_000 * args.tail_silence_ms // 1_000))
    frame_size = 16_000 * args.frame_ms // 1_000

    for sequence, offset in enumerate(range(0, len(samples), frame_size)):
        pcm = samples[offset : offset + frame_size]
        normalized = tuple(sample / 32768.0 for sample in pcm)
        event = asr.accept(
            AudioFrame(sequence=sequence, sample_rate_hz=16_000, samples=normalized)
        )
        if event is not None:
            print(json.dumps(event.__dict__, ensure_ascii=False))


if __name__ == "__main__":
    main()
