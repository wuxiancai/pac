from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence
from uuid import uuid4


@dataclass(frozen=True)
class AudioFrame:
    sequence: int
    sample_rate_hz: int
    samples: Sequence[float]


@dataclass(frozen=True)
class RecognitionSnapshot:
    text: str
    endpoint: bool = False


@dataclass(frozen=True)
class ASREvent:
    kind: str
    text: str
    sequence: int
    revision_id: str


@dataclass(frozen=True)
class ModelFiles:
    encoder: Path
    decoder: Path
    joiner: Path
    tokens: Path


def resolve_model_files(model_dir: Path) -> ModelFiles:
    """Find supported sherpa-onnx streaming transducer filenames."""
    layouts = (
        ModelFiles(
            encoder=model_dir / "encoder.int8.onnx",
            decoder=model_dir / "decoder.onnx",
            joiner=model_dir / "joiner.int8.onnx",
            tokens=model_dir / "tokens.txt",
        ),
        ModelFiles(
            encoder=model_dir / "encoder-epoch-99-avg-1.int8.onnx",
            decoder=model_dir / "decoder-epoch-99-avg-1.onnx",
            joiner=model_dir / "joiner-epoch-99-avg-1.int8.onnx",
            tokens=model_dir / "tokens.txt",
        ),
    )
    for files in layouts:
        if all(path.is_file() for path in (files.encoder, files.decoder, files.joiner, files.tokens)):
            return files
    expected = " or ".join(
        f"{files.encoder.name}, {files.decoder.name}, {files.joiner.name}, tokens.txt"
        for files in layouts
    )
    raise FileNotFoundError(f"unsupported streaming model files in {model_dir}; expected {expected}")


class StreamingRecognizer(Protocol):
    def accept(self, samples: Sequence[float], sample_rate_hz: int) -> None: ...

    def decode(self) -> RecognitionSnapshot: ...

    def reset(self) -> None: ...


class LocalStreamingASR:
    """Translate local recognizer snapshots into revisioned partial/final events."""

    def __init__(self, recognizer: StreamingRecognizer, *, sample_rate_hz: int) -> None:
        if sample_rate_hz <= 0:
            raise ValueError("sample rate must be positive")
        self._recognizer = recognizer
        self._sample_rate_hz = sample_rate_hz
        self._expected_sequence = 0
        self._last_text = ""
        self._revision_id = self._new_revision()

    def accept(self, frame: AudioFrame) -> ASREvent | None:
        if frame.sample_rate_hz != self._sample_rate_hz:
            raise ValueError(
                f"sample rate {frame.sample_rate_hz} does not match configured "
                f"sample rate {self._sample_rate_hz}"
            )
        if frame.sequence != self._expected_sequence:
            raise ValueError(
                f"sequence {frame.sequence} does not match expected sequence "
                f"{self._expected_sequence}"
            )
        if not frame.samples:
            raise ValueError("audio frame must contain samples")

        self._expected_sequence += 1
        self._recognizer.accept(frame.samples, frame.sample_rate_hz)
        snapshot = self._recognizer.decode()

        if snapshot.endpoint:
            event = ASREvent(
                kind="final",
                text=snapshot.text,
                sequence=frame.sequence,
                revision_id=self._revision_id,
            )
            self._recognizer.reset()
            self._last_text = ""
            self._revision_id = self._new_revision()
            return event if snapshot.text else None

        if snapshot.text != self._last_text:
            self._last_text = snapshot.text
            self._revision_id = self._new_revision()
            return ASREvent(
                kind="partial",
                text=snapshot.text,
                sequence=frame.sequence,
                revision_id=self._revision_id,
            )
        return None

    @staticmethod
    def _new_revision() -> str:
        return f"rev_{uuid4().hex}"


class SherpaOnnxRecognizer:
    """Thin local-only wrapper around sherpa-onnx OnlineRecognizer."""

    def __init__(self, *, encoder: Path, decoder: Path, joiner: Path, tokens: Path) -> None:
        for name, path in (
            ("encoder", encoder),
            ("decoder", decoder),
            ("joiner", joiner),
            ("tokens", tokens),
        ):
            if not path.is_file():
                raise FileNotFoundError(f"{name} model file not found: {path}")

        try:
            import sherpa_onnx
        except ImportError as exc:
            raise RuntimeError(
                "sherpa-onnx is not installed in the local POC environment"
            ) from exc

        self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            encoder=str(encoder),
            decoder=str(decoder),
            joiner=str(joiner),
            tokens=str(tokens),
            num_threads=2,
            sample_rate=16_000,
            feature_dim=80,
            decoding_method="greedy_search",
            enable_endpoint_detection=True,
        )
        self._stream = self._recognizer.create_stream()

    def accept(self, samples: Sequence[float], sample_rate_hz: int) -> None:
        self._stream.accept_waveform(sample_rate_hz, samples)
        while self._recognizer.is_ready(self._stream):
            self._recognizer.decode_stream(self._stream)

    def decode(self) -> RecognitionSnapshot:
        return RecognitionSnapshot(
            text=self._recognizer.get_result(self._stream),
            endpoint=self._recognizer.is_endpoint(self._stream),
        )

    def reset(self) -> None:
        self._recognizer.reset(self._stream)
