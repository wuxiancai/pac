from __future__ import annotations

import secrets
import socket
import subprocess
import threading
import time
from pathlib import Path

from pac_poc.security_poc import LOCAL_API_BIND_HOST, LocalAPISession, create_local_server


def main() -> int:
    token = secrets.token_urlsafe(32)
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

    try:
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not server.started:
            return 1

        package = Path(__file__).resolve().parents[2] / "poc" / "macos-audio"
        result = subprocess.run(
            [
                "swift",
                "run",
                "--package-path",
                str(package),
                "local-api-client-poc",
                f"http://{LOCAL_API_BIND_HOST}:{port}",
            ],
            input=f"{token}\n",
            capture_output=True,
            text=True,
            timeout=150,
            check=False,
        )
        output = result.stdout + result.stderr
        if token in output or result.returncode != 0 or "local health OK" not in result.stdout:
            return 1
        print("Swift client reached local FastAPI over loopback.")
        return 0
    except (OSError, subprocess.SubprocessError):
        return 1
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()


if __name__ == "__main__":
    raise SystemExit(main())
