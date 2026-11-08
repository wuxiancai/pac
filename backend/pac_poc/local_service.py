from __future__ import annotations

import json
import secrets
import socket
import sys
import threading
import time

from .beta_api import create_beta_api
from .security_poc import LOCAL_API_BIND_HOST, LocalAPISession, create_local_server


STARTUP_TIMEOUT_SECONDS = 5.0


def main() -> int:
    """Run the fixed POC API process and exchange readiness over standard pipes."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server = None
    server_thread: threading.Thread | None = None
    try:
        listener.bind((LOCAL_API_BIND_HOST, 0))
        listener.listen()
        port = listener.getsockname()[1]
        token = secrets.token_urlsafe(32)
        server = create_local_server(
            session=LocalAPISession(token=token), port=port, app_factory=create_beta_api
        )
        server_thread = threading.Thread(
            target=server.run,
            kwargs={"sockets": [listener]},
            name="pac-local-api",
            daemon=False,
        )
        server_thread.start()

        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while not server.started and server_thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not server.started:
            server.should_exit = True
            server_thread.join(timeout=STARTUP_TIMEOUT_SECONDS)
            return 1

        # stdout is a private owner pipe: exactly one credential-bearing handshake.
        sys.stdout.write(json.dumps({
            "base_url": f"http://{LOCAL_API_BIND_HOST}:{port}",
            "token": token,
        }, separators=(",", ":")) + "\n")
        sys.stdout.flush()

        command = sys.stdin.readline().strip()
        server.should_exit = True
        server_thread.join(timeout=STARTUP_TIMEOUT_SECONDS)
        if server_thread.is_alive():
            return 1
        return 0 if command in {"stop", ""} else 2
    except (OSError, RuntimeError, ValueError):
        if server is not None:
            server.should_exit = True
        if server_thread is not None:
            server_thread.join(timeout=STARTUP_TIMEOUT_SECONDS)
        return 1
    finally:
        listener.close()


if __name__ == "__main__":
    raise SystemExit(main())
