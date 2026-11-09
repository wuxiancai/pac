from __future__ import annotations

import json
import math
import secrets
import socket
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import FastAPI

from .beta_api import create_beta_api
from .security_poc import LOCAL_API_BIND_HOST, LocalAPISession, create_local_server


STARTUP_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class LocalServiceSettings:
    startup_timeout_seconds: float = STARTUP_TIMEOUT_SECONDS
    shutdown_timeout_seconds: float = STARTUP_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if any(
            not math.isfinite(value) or value <= 0
            for value in (self.startup_timeout_seconds, self.shutdown_timeout_seconds)
        ):
            raise ValueError("service timeouts must be finite positive values")


def main() -> int:
    return run_local_service()


def run_local_service(
    *,
    settings: LocalServiceSettings = LocalServiceSettings(),
    app_factory: Callable[..., FastAPI] = create_beta_api,
) -> int:
    """Compose and run the loopback API; settings and app construction are injectable."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server = None
    server_thread: threading.Thread | None = None
    try:
        listener.bind((LOCAL_API_BIND_HOST, 0))
        listener.listen()
        port = listener.getsockname()[1]
        token = secrets.token_urlsafe(32)
        # This random token is private to the owning app and is discarded when
        # the supervisor closes the process pipe, so the beta session follows
        # the process lifetime instead of the short POC demo timeout.
        server = create_local_server(
            session=LocalAPISession(token=token, expires_at=float("inf")),
            port=port,
            app_factory=app_factory,
        )
        server_thread = threading.Thread(
            target=server.run,
            kwargs={"sockets": [listener]},
            name="pac-local-api",
            daemon=False,
        )
        server_thread.start()

        deadline = time.monotonic() + settings.startup_timeout_seconds
        while not server.started and server_thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not server.started:
            server.should_exit = True
            server_thread.join(timeout=settings.shutdown_timeout_seconds)
            return 1

        # stdout is a private owner pipe: exactly one credential-bearing handshake.
        sys.stdout.write(json.dumps({
            "base_url": f"http://{LOCAL_API_BIND_HOST}:{port}",
            "token": token,
        }, separators=(",", ":")) + "\n")
        sys.stdout.flush()

        command = sys.stdin.readline().strip()
        server.should_exit = True
        server_thread.join(timeout=settings.shutdown_timeout_seconds)
        if server_thread.is_alive():
            return 1
        return 0 if command in {"stop", ""} else 2
    except (OSError, RuntimeError, ValueError):
        if server is not None:
            server.should_exit = True
        if server_thread is not None:
            server_thread.join(timeout=settings.shutdown_timeout_seconds)
        return 1
    finally:
        listener.close()


if __name__ == "__main__":
    raise SystemExit(main())
