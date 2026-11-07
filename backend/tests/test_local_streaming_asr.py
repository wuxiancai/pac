from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pytest

from pac_poc.asr import AudioFrame, LocalStreamingASR


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
