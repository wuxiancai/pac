from __future__ import annotations

import json
import select
import subprocess
import sys
from pathlib import Path

import httpx


BACKEND = Path(__file__).resolve().parents[1]


def _readiness_line(process: subprocess.Popen[str], timeout: float = 8) -> dict[str, object]:
    assert process.stdout is not None
    ready, _, _ = select.select([process.stdout], [], [], timeout)
    assert ready, "service did not emit a readiness handshake before the deadline"
    line = process.stdout.readline()
    return json.loads(line)


def test_managed_local_service_emits_authenticated_loopback_handshake_and_stops() -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "pac_poc.local_service"],
        cwd=BACKEND,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        handshake = _readiness_line(process)
        assert set(handshake) == {"base_url", "token"}
        assert isinstance(handshake["token"], str) and len(handshake["token"]) >= 32
        base_url = str(handshake["base_url"])
        assert base_url.startswith("http://127.0.0.1:")
        with httpx.Client(timeout=2) as client:
            assert client.get(f"{base_url}/health").status_code == 401
            response = client.get(
                f"{base_url}/health",
                headers={"authorization": f"Bearer {handshake['token']}"},
            )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        assert process.stdin is not None
        process.stdin.write("stop\n")
        process.stdin.flush()
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()


def test_managed_local_service_exits_cleanly_when_owner_pipe_closes() -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "pac_poc.local_service"],
        cwd=BACKEND,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _readiness_line(process)
        assert process.stdin is not None
        process.stdin.close()
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()


def test_managed_local_service_stops_server_for_invalid_owner_command() -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "pac_poc.local_service"],
        cwd=BACKEND,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _readiness_line(process)
        assert process.stdin is not None
        process.stdin.write("unexpected\n")
        process.stdin.flush()
        assert process.wait(timeout=5) == 2
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()
