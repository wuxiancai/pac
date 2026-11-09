from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pytest

from pac_poc.asr import AudioFrame, LocalStreamingASR, resolve_model_files


@dataclass(frozen=True)
class Snapshot:
    text: str
    endpoint: bool = False


class FakeStream(Protocol):
    def accept(self, samples: tuple[float, ...], sample_rate_hz: int) -> None: ...

    def decode(self) -> Snapshot: ...

    def reset(self) -> None: ...


class FakeRecognizer:
    def __init__(self, snapshots: list[Snapshot]) -> None:
        self.snapshots = iter(snapshots)
        self.accepted: list[tuple[tuple[float, ...], int]] = []
        self.reset_count = 0

    def accept(self, samples: tuple[float, ...], sample_rate_hz: int) -> None:
        self.accepted.append((samples, sample_rate_hz))

    def decode(self) -> Snapshot:
        return next(self.snapshots)

    def reset(self) -> None:
        self.reset_count += 1


def test_partial_revisions_are_emitted_but_only_endpoint_is_final() -> None:
    recognizer = FakeRecognizer(
        [Snapshot("今天天气"), Snapshot("今天天气很好"), Snapshot("今天天气很好。", endpoint=True)]
    )
    asr = LocalStreamingASR(recognizer, sample_rate_hz=16_000)

    events = [
        asr.accept(AudioFrame(sequence=i, sample_rate_hz=16_000, samples=(0.0,)))
        for i in range(3)
    ]

    assert [(event.kind, event.text) for event in events] == [
        ("partial", "今天天气"),
        ("partial", "今天天气很好"),
        ("final", "今天天气很好。"),
    ]
    assert events[0].revision_id != events[1].revision_id
    assert recognizer.reset_count == 1


def test_rejects_wrong_sample_rate_without_fallback() -> None:
    recognizer = FakeRecognizer([])
    asr = LocalStreamingASR(recognizer, sample_rate_hz=16_000)

    with pytest.raises(ValueError, match="sample rate"):
        asr.accept(AudioFrame(sequence=0, sample_rate_hz=48_000, samples=(0.0,)))

    assert recognizer.accepted == []


def test_rejects_sequence_gap_without_silently_dropping_audio() -> None:
    recognizer = FakeRecognizer([])
    asr = LocalStreamingASR(recognizer, sample_rate_hz=16_000)

    with pytest.raises(ValueError, match="sequence"):
        asr.accept(AudioFrame(sequence=1, sample_rate_hz=16_000, samples=(0.0,)))

    assert recognizer.accepted == []


def test_suppresses_duplicate_partial_text() -> None:
    recognizer = FakeRecognizer([Snapshot("你好"), Snapshot("你好")])
    asr = LocalStreamingASR(recognizer, sample_rate_hz=16_000)

    first = asr.accept(AudioFrame(sequence=0, sample_rate_hz=16_000, samples=(0.0,)))
    second = asr.accept(AudioFrame(sequence=1, sample_rate_hz=16_000, samples=(0.0,)))

    assert first is not None and first.text == "你好"
    assert second is None


def test_finish_flushes_endpoint_and_emits_final() -> None:
    recognizer = FakeRecognizer([Snapshot("你好"), Snapshot("你好。", endpoint=True)])
    asr = LocalStreamingASR(recognizer, sample_rate_hz=16_000)
    partial = asr.accept(AudioFrame(sequence=0, sample_rate_hz=16_000, samples=(0.0,)))

    final = asr.finish(sequence=1)

    assert partial is not None and partial.kind == "partial"
    assert final is not None
    assert (final.kind, final.text, final.sequence) == ("final", "你好。", 1)
    assert len(recognizer.accepted) == 2
    assert recognizer.accepted[-1][0] == (0.0,) * 3_200
    assert recognizer.reset_count == 1


def test_finish_promotes_last_partial_when_endpoint_is_not_detected() -> None:
    recognizer = FakeRecognizer([Snapshot("你好"), *[Snapshot("你好") for _ in range(3)]])
    asr = LocalStreamingASR(recognizer, sample_rate_hz=16_000)
    asr.accept(AudioFrame(sequence=0, sample_rate_hz=16_000, samples=(0.0,)))

    final = asr.finish(sequence=1)

    assert final is not None
    assert (final.kind, final.text, final.sequence) == ("final", "你好", 4)
    assert len(recognizer.accepted) == 4


def test_resolves_sherpa_onnx_epoch_named_bilingual_model_files(tmp_path) -> None:
    for name in (
        "encoder-epoch-99-avg-1.int8.onnx",
        "decoder-epoch-99-avg-1.onnx",
        "joiner-epoch-99-avg-1.int8.onnx",
        "tokens.txt",
    ):
        (tmp_path / name).touch()

    files = resolve_model_files(tmp_path)

    assert files.encoder.name == "encoder-epoch-99-avg-1.int8.onnx"
    assert files.decoder.name == "decoder-epoch-99-avg-1.onnx"
    assert files.joiner.name == "joiner-epoch-99-avg-1.int8.onnx"
    assert files.tokens.name == "tokens.txt"
