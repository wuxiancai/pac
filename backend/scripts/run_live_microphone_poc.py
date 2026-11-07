from __future__ import annotations

import argparse
import math
import sys
import time
from array import array
from pathlib import Path
from queue import Empty
from threading import Event

from pac_poc.asr import AudioFrame, LocalStreamingASR, SherpaOnnxRecognizer
from pac_poc.microphone import AudioBackpressure, MicrophoneFrameBuffer


def pcm16le_to_float_samples(data: bytes) -> tuple[float, ...]:
    pcm = array("h")
    pcm.frombytes(data)
    if pcm.itemsize != 2:
        raise RuntimeError("the local platform does not expose 16-bit signed samples")
    if sys.byteorder != "little":
        pcm.byteswap()
    return tuple(sample / 32768.0 for sample in pcm)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explicitly started, local-only microphone streaming ASR POC"
    )
    parser.add_argument("model_dir", type=Path)
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument("--sample-rate", type=int, default=16_000)
    parser.add_argument("--frame-ms", type=int, default=200)
    args = parser.parse_args()

    if not 1 <= args.seconds <= 120:
        parser.error("--seconds must be between 1 and 120")
    if args.sample_rate != 16_000:
        parser.error("the selected POC model requires 16 kHz input")
    if args.frame_ms <= 0 or args.sample_rate * args.frame_ms % 1000:
        parser.error("--frame-ms must produce a whole number of samples")
    if not sys.stdin.isatty():
        parser.error("run from an interactive local terminal to explicitly start capture")

    try:
        import sounddevice as sd
    except ImportError as exc:
        raise SystemExit("Install the locked local dependencies before microphone capture") from exc

    print(
        f"本机默认麦克风将采集最多 {args.seconds} 秒；音频只保留在内存，不写入文件、不发送云端。"
    )
    input("准备好后按回车开始；中途按 Ctrl-C 停止：")

    frame_samples = args.sample_rate * args.frame_ms // 1000
    frame_buffer = MicrophoneFrameBuffer(max_frames=25)
    capture_stopped = Event()
    capture_errors: list[str] = []

    def on_audio(indata: bytes, frames: int, time_info: object, status: object) -> None:
        del frames, time_info
        if status:
            capture_errors.append(f"audio input status: {status}")
            capture_stopped.set()
            raise sd.CallbackAbort
        if len(indata) != frames * 2:
            capture_errors.append("audio callback returned an incomplete PCM16 frame")
            capture_stopped.set()
            raise sd.CallbackAbort
        try:
            frame_buffer.offer(bytes(indata))
        except AudioBackpressure as exc:
            capture_errors.append(str(exc))
            capture_stopped.set()
            raise sd.CallbackAbort

    recognizer = SherpaOnnxRecognizer(
        encoder=args.model_dir / "encoder.int8.onnx",
        decoder=args.model_dir / "decoder.onnx",
        joiner=args.model_dir / "joiner.int8.onnx",
        tokens=args.model_dir / "tokens.txt",
    )
    asr = LocalStreamingASR(recognizer, sample_rate_hz=args.sample_rate)
    sequence = 0
    started_at = time.monotonic()

    try:
        with sd.RawInputStream(
            samplerate=args.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=frame_samples,
            callback=on_audio,
        ):
            started_at = time.monotonic()
            print("正在本机识别；partial 仅显示，不写入文件或记忆。")
            while (
                time.monotonic() - started_at < args.seconds
                and not capture_stopped.is_set()
            ):
                try:
                    raw_frame = frame_buffer.take(timeout=0.1)
                except Empty:
                    continue
                event = asr.accept(
                    AudioFrame(
                        sequence=sequence,
                        sample_rate_hz=args.sample_rate,
                        samples=pcm16le_to_float_samples(raw_frame),
                    )
                )
                sequence += 1
                if event is not None:
                    print(f"[{event.kind}] {event.text}", flush=True)

        if capture_errors:
            raise RuntimeError(capture_errors[0])

        while True:
            try:
                raw_frame = frame_buffer.take_nowait()
            except Empty:
                break
            event = asr.accept(
                AudioFrame(
                    sequence=sequence,
                    sample_rate_hz=args.sample_rate,
                    samples=pcm16le_to_float_samples(raw_frame),
                )
            )
            sequence += 1
            if event is not None:
                print(f"[{event.kind}] {event.text}", flush=True)

        silence = tuple(0.0 for _ in range(frame_samples))
        for _ in range(math.ceil(1600 / args.frame_ms)):
            event = asr.accept(
                AudioFrame(
                    sequence=sequence,
                    sample_rate_hz=args.sample_rate,
                    samples=silence,
                )
            )
            sequence += 1
            if event is not None:
                print(f"[{event.kind}] {event.text}", flush=True)
    except KeyboardInterrupt:
        print("\n用户停止了本机采集；未补造 final。")
    finally:
        frame_buffer.close()

    if capture_errors:
        raise SystemExit(f"本机采集已安全停止：{capture_errors[0]}")


if __name__ == "__main__":
    main()
