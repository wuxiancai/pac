from __future__ import annotations

import argparse
import json
import math
import secrets
import socket
import sys
import re
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
        for value in (self.startup_timeout_seconds, self.shutdown_timeout_seconds):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError("service timeouts must be finite positive values")


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--database-key-stdin", action="store_true")
    options = parser.parse_args()
    database_key = _read_database_key() if options.database_key_stdin else None
    if options.database_key_stdin and database_key is None:
        return 1
    return run_local_service(database_key=database_key)


def _read_database_key() -> bytes | None:
    line = sys.stdin.readline(66)
    if len(line) != 65 or not line.endswith("\n"):
        return None
    encoded = line[:-1]
    if re.fullmatch(r"[0-9a-f]{64}", encoded) is None:
        return None
    return bytes.fromhex(encoded)


def run_local_service(
    *,
    settings: LocalServiceSettings = LocalServiceSettings(),
    app_factory: Callable[..., FastAPI] = create_beta_api,
    database_key: bytes | None = None,
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
        session = LocalAPISession(token=token, expires_at=float("inf"))
        if database_key is None:
            server = create_local_server(session=session, port=port, app_factory=app_factory)
        else:
            server = create_local_server(
                session=session,
                port=port,
                app_factory=lambda *, session: app_factory(session=session, database_key=database_key),
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
