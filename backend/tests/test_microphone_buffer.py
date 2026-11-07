from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path

import pytest

from pac_poc.microphone import AudioBackpressure, MicrophoneFrameBuffer
from scripts.run_live_microphone_poc import pcm16le_to_float_samples


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
