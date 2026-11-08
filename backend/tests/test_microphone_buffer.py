from __future__ import annotations

import struct
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from pac_poc.microphone import AudioBackpressure, MicrophoneFrameBuffer
from scripts import run_live_microphone_poc
from scripts.run_live_microphone_poc import is_complete_pcm16_frame, pcm16le_to_float_samples


def test_buffer_returns_frames_in_order() -> None:
    buffer = MicrophoneFrameBuffer(max_frames=2)
    buffer.offer(b"frame-1")
    buffer.offer(b"frame-2")

    assert buffer.take_nowait() == b"frame-1"
    assert buffer.take_nowait() == b"frame-2"


def test_buffer_fails_closed_and_clears_audio_on_overflow() -> None:
    buffer = MicrophoneFrameBuffer(max_frames=1)
    buffer.offer(b"frame-1")

    with pytest.raises(AudioBackpressure):
        buffer.offer(b"frame-2")

    assert buffer.closed
    assert buffer.queued_frames == 0
    with pytest.raises(RuntimeError, match="closed"):
        buffer.offer(b"frame-3")


def test_explicit_close_discards_buffered_audio() -> None:
    buffer = MicrophoneFrameBuffer(max_frames=2)
    buffer.offer(b"private audio")

    buffer.close()

    assert buffer.closed
    assert buffer.queued_frames == 0


def test_pcm16_little_endian_frames_convert_to_normalized_float_samples() -> None:
    samples = pcm16le_to_float_samples(struct.pack("<hh", 16384, -16384))

    assert samples == (0.5, -0.5)


def test_pcm16_callback_frame_size_matches_reported_sample_count() -> None:
    assert is_complete_pcm16_frame(b"\x00\x00" * 160, frames=160)
    assert not is_complete_pcm16_frame(b"\x00\x00" * 159, frames=160)


def test_microphone_cli_requires_interactive_user_start() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "scripts.run_live_microphone_poc", "unused-model-dir"],
        cwd=backend_dir,
        input="",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "interactive local terminal" in result.stderr


def test_microphone_script_entrypoint_imports_project_package() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_live_microphone_poc.py",
            "unused-model-dir",
            "--help",
        ],
        cwd=backend_dir,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Explicitly started, local-only microphone" in result.stdout


@pytest.mark.parametrize(
    ("failure", "raises_to_caller"),
    [(RuntimeError, True), (KeyboardInterrupt, False)],
    ids=["decoder-error", "user-interrupt"],
)
def test_microphone_cli_closes_stream_and_discards_buffer_on_exit(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: type[BaseException],
    raises_to_caller: bool,
) -> None:
    frame_buffer = MicrophoneFrameBuffer(max_frames=25)
    stream_closed = False

    class FakeInputStream:
        def __init__(self, **kwargs) -> None:
            self.callback = kwargs["callback"]

        def __enter__(self):
            self.callback(b"\x00\x00" * 3200, 3200, None, None)
            return self

        def __exit__(self, *_args) -> None:
            nonlocal stream_closed
            stream_closed = True

    class FailingASR:
        def accept(self, _frame):
            raise failure("synthetic decoder failure")

    monkeypatch.setattr(run_live_microphone_poc.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    monkeypatch.setattr(
        run_live_microphone_poc,
        "MicrophoneFrameBuffer",
        lambda **_kwargs: frame_buffer,
    )
    monkeypatch.setattr(
        run_live_microphone_poc,
        "resolve_model_files",
        lambda _path: SimpleNamespace(),
    )
    monkeypatch.setattr(run_live_microphone_poc, "SherpaOnnxRecognizer", lambda **_kwargs: object())
    monkeypatch.setattr(
        run_live_microphone_poc,
        "LocalStreamingASR",
        lambda *_args, **_kwargs: FailingASR(),
    )
    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(RawInputStream=FakeInputStream))
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_live_microphone_poc.py", "unused-model-dir", "--seconds", "1"],
    )

    if raises_to_caller:
        with pytest.raises(RuntimeError, match="synthetic decoder failure"):
            run_live_microphone_poc.main()
    else:
        run_live_microphone_poc.main()
        assert "用户停止了本机采集" in capsys.readouterr().out

    assert stream_closed
    assert frame_buffer.closed
    assert frame_buffer.queued_frames == 0
