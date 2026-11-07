from __future__ import annotations

import secrets
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from pac_poc.security_poc import LOCAL_API_BIND_HOST, LocalAPISession, create_local_server


def start_server(token: str) -> tuple[Any, socket.socket, threading.Thread, int]:
    session = LocalAPISession(token=token)
    server = create_local_server(session=session, port=0)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind((LOCAL_API_BIND_HOST, 0))
    listener.listen()
    port = listener.getsockname()[1]
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [listener]},
        daemon=True,
    )
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
        raise RuntimeError("local FastAPI server did not become ready")
    return server, listener, thread, port


def stop_server(server: Any, listener: socket.socket, thread: threading.Thread) -> bool:
    server.should_exit = True
    thread.join(timeout=5)
    listener.close()
    return not thread.is_alive()


def run_swift_client(package: Path, *, port: int, token: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["swift", "run", "--package-path", str(package), "local-api-client-poc",
         f"http://{LOCAL_API_BIND_HOST}:{port}"],
        input=f"{token}\n",
        capture_output=True,
        text=True,
        timeout=150,
        check=False,
    )


def main() -> int:
    package = Path(__file__).resolve().parents[2] / "poc" / "macos-audio"
    try:
        for _ in range(2):
            token = secrets.token_urlsafe(32)
            server, listener, thread, port = start_server(token)
            try:
                result = run_swift_client(package, port=port, token=token)
                output = result.stdout + result.stderr
                if token in output or result.returncode != 0 or "local health OK" not in result.stdout:
                    return 1
            finally:
                if not stop_server(server, listener, thread):
                    return 1
        print("Swift client reached local FastAPI over loopback; restart handshake passed.")
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
