from __future__ import annotations

from pathlib import Path

from pac_poc.asr import ModelFiles, RecognitionSnapshot
from pac_poc.voice_transcription import LocalVoiceTranscriber


class StubRecognizer:
    def __init__(self) -> None:
        self.accepted = 0
        self.reset_count = 0

    def accept(self, samples: tuple[float, ...], sample_rate_hz: int) -> None:
        assert sample_rate_hz == 16_000
        self.accepted += 1

    def decode(self) -> RecognitionSnapshot:
        return RecognitionSnapshot("你好")

    def reset(self) -> None:
        self.reset_count += 1


def test_end_and_abort_clear_recognizer_stream_and_allow_restart(monkeypatch) -> None:
    recognizer = StubRecognizer()
    monkeypatch.setattr(
        "pac_poc.voice_transcription.resolve_model_files",
        lambda _: ModelFiles(
            encoder=Path("encoder"),
            decoder=Path("decoder"),
            joiner=Path("joiner"),
            tokens=Path("tokens"),
        ),
    )
    monkeypatch.setattr(
        "pac_poc.voice_transcription.SherpaOnnxRecognizer",
        lambda **_: recognizer,
    )
    transcriber = LocalVoiceTranscriber(Path("unused-model-dir"))

    transcriber.begin_stream()
    assert transcriber.accept_stream_frame(b"\x00\x00", 0) is not None
    final = transcriber.end_stream(sequence=1)
    assert final is not None and (final.kind, final.text) == ("final", "你好")
    assert transcriber._stream is None

    transcriber.begin_stream()
    assert transcriber.accept_stream_frame(b"\x00\x00", 0) is not None
    transcriber.abort_stream()
    assert transcriber._stream is None
    transcriber.begin_stream()
    assert transcriber.accept_stream_frame(b"\x00\x00", 0) is not None
    transcriber.abort_stream()
    assert recognizer.reset_count == 6
