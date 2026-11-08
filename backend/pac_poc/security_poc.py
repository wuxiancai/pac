from __future__ import annotations

import hmac
import ipaddress
import time
from dataclasses import dataclass, field
from collections.abc import Callable
from enum import StrEnum
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn


LOCAL_API_BIND_HOST = "127.0.0.1"


@dataclass(frozen=True)
class LocalAPISession:
    token: str
    expires_at: float = field(default_factory=lambda: time.monotonic() + 300)


def create_local_api(*, session: LocalAPISession) -> FastAPI:
    """Create a POC-only API; the caller must bind its server to loopback."""
    if not session.token:
        raise ValueError("local API session token must not be empty")

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def protect_local_api(request: Request, call_next):
        if not _is_loopback_host(request.headers.get("host", "")):
            return JSONResponse({"detail": "invalid host"}, status_code=400)
        if request.headers.get("origin") is not None:
            return JSONResponse({"detail": "browser origins are not allowed"}, status_code=403)
        if time.monotonic() >= session.expires_at:
            return JSONResponse({"detail": "local session expired"}, status_code=401)
        authorization = request.headers.get("authorization", "")
        prefix = "Bearer "
        candidate = authorization[len(prefix) :] if authorization.startswith(prefix) else ""
        if not hmac.compare_digest(candidate.encode("utf-8"), session.token.encode("utf-8")):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def create_local_server(
    *,
    session: LocalAPISession,
    port: int,
    app_factory: Callable[..., FastAPI] = create_local_api,
) -> uvicorn.Server:
    """Build a single-worker server pinned to IPv4 loopback, including port 0 for tests."""
    if not 0 <= port <= 65535:
        raise ValueError("port must be between 0 and 65535")
    config = uvicorn.Config(
        app_factory(session=session),
        host=LOCAL_API_BIND_HOST,
        port=port,
        workers=1,
        reload=False,
        access_log=False,
        log_level="critical",
    )
    return uvicorn.Server(config)


def _is_loopback_host(host: str) -> bool:
    try:
        parsed = urlsplit(f"//{host}")
        if (
            parsed.netloc != host
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
        ):
            return False
        port = parsed.port
        address = ipaddress.ip_address(parsed.hostname or "")
    except (ValueError, AttributeError):
        return False
    return address.is_loopback and (port is None or 1 <= port <= 65535)


class DataLevel(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


@dataclass(frozen=True)
class ConsentGrant:
    provider: str
    model: str
    region: str
    purpose: str
    data_levels: frozenset[DataLevel]
    expires_at: float


@dataclass(frozen=True)
class OutboundRequest:
    provider: str
    model: str
    region: str
    purpose: str
    data_level: DataLevel


class ConsentManager:
    """In-memory exact-match consent registry; no grant exists by default."""

    def __init__(self) -> None:
        self._grants: dict[tuple[str, str, str, str], ConsentGrant] = {}

    def grant(self, grant: ConsentGrant) -> None:
        self._grants[(grant.provider, grant.model, grant.region, grant.purpose)] = grant

    def revoke(self, provider: str, model: str, region: str, purpose: str) -> bool:
        key = (provider, model, region, purpose)
        return self._grants.pop(key, None) is not None

    def exact_grant(
        self, provider: str, model: str, region: str, purpose: str
    ) -> ConsentGrant | None:
        return self._grants.get((provider, model, region, purpose))


class OutboundPolicy:
    def __init__(self, consent: ConsentManager) -> None:
        self._consent = consent

    def authorize(self, request: OutboundRequest) -> bool:
        if request.data_level is DataLevel.L3:
            return False
        grant = self._consent.exact_grant(
            request.provider, request.model, request.region, request.purpose
        )
        return bool(
            grant
            and time.time() < grant.expires_at
            and request.data_level in grant.data_levels
        )
