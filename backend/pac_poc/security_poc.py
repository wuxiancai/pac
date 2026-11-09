from __future__ import annotations

import asyncio
import hmac
import ipaddress
import threading
import time
import uuid
from dataclasses import dataclass, field, replace
from collections.abc import Callable
from enum import StrEnum
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import uvicorn


LOCAL_API_BIND_HOST = "127.0.0.1"
LOCAL_API_VERSION = "0.1.0"


@dataclass(frozen=True)
class LocalAPISession:
    token: str
    expires_at: float = field(default_factory=lambda: time.monotonic() + 300)


def create_local_api(*, session: LocalAPISession) -> FastAPI:
    """Create a POC-only API; the caller must bind its server to loopback."""
    if not session.token:
        raise ValueError("local API session token must not be empty")

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.started_at = time.monotonic()

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        code = {
            400: "bad_request",
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            409: "conflict",
            413: "payload_too_large",
            415: "unsupported_media_type",
            422: "request_rejected",
            503: "service_unavailable",
        }.get(error.status_code, "http_error")
        message = error.detail if isinstance(error.detail, str) else "request failed"
        return _error_response(request, error.status_code, code, message, headers=error.headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        # Do not echo rejected values: request bodies can contain prompts or secrets.
        return _error_response(request, 422, "validation_error", "request validation failed")

    @app.middleware("http")
    async def protect_local_api(request: Request, call_next):
        supplied = request.headers.get("x-trace-id", "")
        try:
            trace_id = str(uuid.UUID(supplied))
        except (ValueError, AttributeError):
            trace_id = str(uuid.uuid4())
        request.state.trace_id = trace_id
        if not _is_loopback_host(request.headers.get("host", "")):
            response = _error_response(request, 400, "invalid_host", "invalid host")
        elif request.headers.get("origin") is not None:
            response = _error_response(
                request, 403, "browser_origin_denied", "browser origins are not allowed"
            )
        elif time.monotonic() >= session.expires_at:
            response = _error_response(request, 401, "session_expired", "local session expired")
        else:
            authorization = request.headers.get("authorization", "")
            prefix = "Bearer "
            candidate = authorization[len(prefix) :] if authorization.startswith(prefix) else ""
            if not hmac.compare_digest(candidate.encode("utf-8"), session.token.encode("utf-8")):
                response = _error_response(request, 401, "unauthorized", "unauthorized")
            else:
                response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        return response

    @app.get("/health")
    async def health(request: Request) -> dict[str, str | float]:
        """Authenticated liveness only; omit provider, key, and user-data details."""
        return {
            "status": "ok",
            "version": LOCAL_API_VERSION,
            "uptime_seconds": round(time.monotonic() - request.app.state.started_at, 3),
        }

    return app


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    *,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        {
            "detail": message,
            "error": {"code": code, "trace_id": getattr(request.state, "trace_id", None)},
        },
        status_code=status_code,
        headers=headers,
    )


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


class ModelAction(StrEnum):
    """The operation actually performed against a Provider.

    Derived by the Gateway from the method invoked, never supplied by a caller,
    so a grant cannot be used for an action it did not enumerate.
    """

    GENERATE = "generate"
    STREAM = "stream"
    TOOL_PROPOSAL = "tool-proposal"


class ConsentStatus(StrEnum):
    """Lifecycle state of a Consent grant (FR-SEC-002 status field)."""

    ACTIVE = "active"
    REVOKED = "revoked"


@dataclass(frozen=True)
class ConsentGrant:
    """Exact-match Consent record bound to the FR-SEC-002 field set.

    `action_scopes` and `source_scopes` are required with no default: a grant
    must state which operations and which originating surfaces it covers.
    """

    provider: str
    model: str
    region: str
    purpose: str
    data_levels: frozenset[DataLevel]
    action_scopes: frozenset[ModelAction]
    source_scopes: frozenset[str]
    expires_at: float
    status: ConsentStatus = ConsentStatus.ACTIVE

    def is_live(self, now: float) -> bool:
        return self.status is ConsentStatus.ACTIVE and now < self.expires_at


@dataclass(frozen=True)
class OutboundRequest:
    provider: str
    model: str
    region: str
    purpose: str
    data_level: DataLevel
    action: ModelAction
    source: str


@dataclass(frozen=True)
class _InFlightRequest:
    loop: asyncio.AbstractEventLoop
    task: asyncio.Task[object]


class ConsentOperationLease:
    """Unregister one authorized outbound operation when its Gateway call ends."""

    def __init__(
        self,
        manager: ConsentManager,
        key: tuple[str, str, str, str],
        operation_id: int,
    ) -> None:
        self._manager: ConsentManager | None = manager
        self._key = key
        self._operation_id = operation_id

    def close(self) -> None:
        manager = self._manager
        if manager is None:
            return
        self._manager = None
        manager._unregister_in_flight(self._key, self._operation_id)


class ConsentManager:
    """In-memory exact-match consent registry; no grant exists by default."""

    def __init__(self) -> None:
        self._grants: dict[tuple[str, str, str, str], ConsentGrant] = {}
        self._in_flight: dict[
            tuple[str, str, str, str], dict[int, _InFlightRequest]
        ] = {}
        self._next_operation_id = 1
        self._lock = threading.RLock()

    def grant(self, grant: ConsentGrant) -> None:
        key = (grant.provider, grant.model, grant.region, grant.purpose)
        with self._lock:
            self._grants[key] = grant

    def revoke(self, provider: str, model: str, region: str, purpose: str) -> bool:
        """Mark a grant REVOKED instead of dropping it, so the state is observable.

        FR-SEC-003 requires revocation to block new requests; a retained REVOKED
        record makes that transition explicit rather than an absent key.
        """
        key = (provider, model, region, purpose)
        with self._lock:
            existing = self._grants.get(key)
            if existing is None or existing.status is ConsentStatus.REVOKED:
                return False
            self._grants[key] = replace(existing, status=ConsentStatus.REVOKED)
            in_flight = tuple(self._in_flight.get(key, {}).values())
        for operation in in_flight:
            if operation.loop.is_closed():
                continue
            try:
                operation.loop.call_soon_threadsafe(
                    operation.task.cancel, "consent revoked"
                )
            except RuntimeError:
                # The owning event loop may close between the check and scheduling.
                continue
        return True

    def exact_grant(
        self, provider: str, model: str, region: str, purpose: str
    ) -> ConsentGrant | None:
        with self._lock:
            return self._grants.get((provider, model, region, purpose))

    def begin_authorized_request(
        self, request: OutboundRequest
    ) -> ConsentOperationLease | None:
        """Atomically recheck exact consent and register the current asyncio task."""
        loop = asyncio.get_running_loop()
        task = asyncio.current_task()
        if task is None:
            return None
        key = (request.provider, request.model, request.region, request.purpose)
        with self._lock:
            grant = self._grants.get(key)
            if not self._grant_authorizes(grant, request):
                return None
            operation_id = self._next_operation_id
            self._next_operation_id += 1
            self._in_flight.setdefault(key, {})[operation_id] = _InFlightRequest(
                loop=loop,
                task=task,
            )
        return ConsentOperationLease(self, key, operation_id)

    def _unregister_in_flight(
        self, key: tuple[str, str, str, str], operation_id: int
    ) -> None:
        with self._lock:
            operations = self._in_flight.get(key)
            if operations is None:
                return
            operations.pop(operation_id, None)
            if not operations:
                self._in_flight.pop(key, None)

    @staticmethod
    def _grant_authorizes(
        grant: ConsentGrant | None, request: OutboundRequest
    ) -> bool:
        return bool(
            request.data_level is not DataLevel.L3
            and grant
            and grant.is_live(time.time())
            and request.data_level in grant.data_levels
            and request.action in grant.action_scopes
            and request.source in grant.source_scopes
        )


class OutboundPolicy:
    def __init__(self, consent: ConsentManager) -> None:
        self._consent = consent

    def authorize(self, request: OutboundRequest) -> bool:
        grant = self._consent.exact_grant(
            request.provider, request.model, request.region, request.purpose
        )
        return self._consent._grant_authorizes(grant, request)

    def begin_authorized_request(
        self, request: OutboundRequest
    ) -> ConsentOperationLease | None:
        return self._consent.begin_authorized_request(request)
