from __future__ import annotations

import sys
from array import array
from pathlib import Path
from threading import Lock

from .asr import AudioFrame, LocalStreamingASR, SherpaOnnxRecognizer, resolve_model_files


SAMPLE_RATE_HZ = 16_000
FRAME_SAMPLES = 3_200  # 200 ms


class LocalVoiceTranscriber:
    """Decode in-memory 16 kHz PCM16 audio with the bundled local streaming model."""

    def __init__(self, model_dir: Path) -> None:
        self._model_dir = model_dir
        self._recognizer: SherpaOnnxRecognizer | None = None
        self._lock = Lock()

    def transcribe_pcm16le(self, pcm: bytes) -> str:
        if not pcm or len(pcm) % 2:
            raise ValueError("audio must be non-empty PCM16LE")

        values = array("h")
        values.frombytes(pcm)
        if sys.byteorder != "little":
            values.byteswap()

        with self._lock:
            if self._recognizer is None:
                model_files = resolve_model_files(self._model_dir)
                self._recognizer = SherpaOnnxRecognizer(**model_files.__dict__)
            self._recognizer.reset()
            asr = LocalStreamingASR(
                self._recognizer,
                sample_rate_hz=SAMPLE_RATE_HZ,
            )
            finals: list[str] = []
            pending = ""
            sequence = 0

            for offset in range(0, len(values), FRAME_SAMPLES):
                event = asr.accept(
                    AudioFrame(
                        sequence=sequence,
                        sample_rate_hz=SAMPLE_RATE_HZ,
                        samples=tuple(
                            sample / 32768.0
                            for sample in values[offset : offset + FRAME_SAMPLES]
                        ),
                    )
                )
                sequence += 1
                if event is not None:
                    if event.kind == "final":
                        finals.append(event.text)
                        pending = ""
                    else:
                        pending = event.text

            silence = (0.0,) * FRAME_SAMPLES
            for _ in range(8):
                event = asr.accept(
                    AudioFrame(
                        sequence=sequence,
                        sample_rate_hz=SAMPLE_RATE_HZ,
                        samples=silence,
                    )
                )
                sequence += 1
                if event is not None:
                    if event.kind == "final":
                        finals.append(event.text)
                        pending = ""
                    else:
                        pending = event.text

            return "".join(finals) if finals else pending
