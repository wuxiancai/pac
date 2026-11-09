from __future__ import annotations

import asyncio
import socket
import threading
import time
import uuid

import httpx
import pytest
import uvicorn

from pac_poc.security_poc import (
    ConsentGrant,
    ConsentManager,
    ConsentStatus,
    DataLevel,
    LocalAPISession,
    LOCAL_API_WEBSOCKET_MAX_MESSAGE_BYTES,
    ModelAction,
    OutboundRequest,
    OutboundPolicy,
    create_local_api,
    create_local_server,
)


def asgi_get(app, path: str, headers: dict[str, str] | None = None) -> httpx.Response:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            return await client.get(path, headers=headers)

    return asyncio.run(request())


@pytest.fixture
def live_local_api():
    session = LocalAPISession(token="live-loopback-test-token")
    app = create_local_api(session=session)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="critical", access_log=False, lifespan="off")
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=1)
        pytest.fail("local API server did not start")
    try:
        yield port, session.token
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_local_api_requires_session_token_and_returns_no_token() -> None:
    session = LocalAPISession(token="test-token-never-logged")
    app = create_local_api(session=session)

    assert asgi_get(app, "/health", {"host": "127.0.0.1"}).status_code == 401
    response = asgi_get(
        app,
        "/health",
        {"host": "127.0.0.1", "authorization": "Bearer test-token-never-logged"},
    )

    assert response.status_code == 200
    assert "test-token-never-logged" not in response.text
    assert "test-token-never-logged" not in str(response.headers)


def test_local_server_caps_websocket_message_size_to_voice_frame_limit() -> None:
    server = create_local_server(
        session=LocalAPISession(token="test-token"), port=0
    )

    assert server.config.ws_max_size == LOCAL_API_WEBSOCKET_MAX_MESSAGE_BYTES
    assert LOCAL_API_WEBSOCKET_MAX_MESSAGE_BYTES == 12_804


def test_local_api_returns_valid_trace_id_and_preserves_valid_client_trace_id() -> None:
    app = create_local_api(session=LocalAPISession(token="trace-test-token"))
    headers = {
        "host": "127.0.0.1",
        "authorization": "Bearer trace-test-token",
    }

    generated = asgi_get(app, "/health", headers)
    generated_trace = uuid.UUID(generated.headers["x-trace-id"])
    assert str(generated_trace) == generated.headers["x-trace-id"]

    requested_trace = str(uuid.uuid4())
    propagated = asgi_get(app, "/health", {**headers, "x-trace-id": requested_trace})
    assert propagated.headers["x-trace-id"] == requested_trace

    invalid = asgi_get(app, "/health", {**headers, "x-trace-id": "client supplied text"})
    assert str(uuid.UUID(invalid.headers["x-trace-id"])) == invalid.headers["x-trace-id"]


def test_local_api_rejects_non_loopback_host_and_all_browser_origins() -> None:
    app = create_local_api(session=LocalAPISession(token="short-lived"))
    headers = {"authorization": "Bearer short-lived"}

    assert asgi_get(app, "/health", {**headers, "host": "example.com"}).status_code == 400
    assert asgi_get(
        app, "/health", {**headers, "host": "127.0.0.1", "origin": "https://example.com"}
    ).status_code == 403
    assert asgi_get(app, "/health", {**headers, "host": "127.0.0.1:invalid"}).status_code == 400


def test_expired_local_api_session_is_rejected() -> None:
    session = LocalAPISession(token="expired", expires_at=0)

    assert asgi_get(
        create_local_api(session=session),
        "/health",
        {"host": "127.0.0.1", "authorization": "Bearer expired"},
    ).status_code == 401


def test_local_api_serves_only_authenticated_loopback_http(live_local_api) -> None:
    port, token = live_local_api
    url = f"http://127.0.0.1:{port}/health"

    assert httpx.get(url, timeout=2).status_code == 401
    response = httpx.get(
        url,
        headers={"authorization": f"Bearer {token}"},
        timeout=2,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"]
    assert response.json()["uptime_seconds"] >= 0
    assert "access-control-allow-origin" not in response.headers


def test_local_server_configuration_binds_only_ipv4_loopback() -> None:
    server = create_local_server(session=LocalAPISession(token="private"), port=0)

    assert server.config.host == "127.0.0.1"
    assert server.config.port == 0
    assert server.config.access_log is False


def test_cloud_egress_defaults_to_deny_and_l3_is_never_authorized() -> None:
    consent = ConsentManager()
    policy = OutboundPolicy(consent)
    request = OutboundRequest(
        provider="example-provider",
        model="model-a",
        region="region-a",
        purpose="answer-question",
        data_level=DataLevel.L1,
        action=ModelAction.GENERATE,
        source="cli-probe",
    )

    assert not policy.authorize(request)
    consent.grant(
        ConsentGrant(
            provider="example-provider",
            model="model-a",
            region="region-a",
            purpose="answer-question",
            data_levels=frozenset({DataLevel.L1, DataLevel.L3}),
            action_scopes=frozenset({ModelAction.GENERATE}),
            source_scopes=frozenset({"cli-probe"}),
            expires_at=9999999999,
        )
    )
    assert policy.authorize(request)
    assert not policy.authorize(
        OutboundRequest(**{**request.__dict__, "data_level": DataLevel.L3})
    )
    assert not policy.authorize(
        OutboundRequest(**{**request.__dict__, "region": "other-region"})
    )
    assert not policy.authorize(
        OutboundRequest(**{**request.__dict__, "purpose": "other-purpose"})
    )
    consent.grant(
        ConsentGrant(
            provider="example-provider",
            model="model-a",
            region="region-a",
            purpose="answer-question",
            data_levels=frozenset({DataLevel.L1}),
            action_scopes=frozenset({ModelAction.GENERATE}),
            source_scopes=frozenset({"cli-probe"}),
            expires_at=0,
        )
    )
    assert not policy.authorize(request)
    consent.grant(
        ConsentGrant(
            provider="example-provider",
            model="model-a",
            region="region-a",
            purpose="answer-question",
            data_levels=frozenset({DataLevel.L1}),
            action_scopes=frozenset({ModelAction.GENERATE}),
            source_scopes=frozenset({"cli-probe"}),
            expires_at=9999999999,
        )
    )
    assert policy.authorize(request)
    consent.revoke("example-provider", "model-a", "region-a", "answer-question")
    assert not policy.authorize(request)


def test_consent_action_and_source_scopes_are_matched_exactly() -> None:
    """FR-SEC-002: a grant cannot cover an operation or surface it did not list."""
    consent = ConsentManager()
    policy = OutboundPolicy(consent)
    base = dict(
        provider="example-provider",
        model="model-a",
        region="region-a",
        purpose="answer-question",
        data_level=DataLevel.L1,
        action=ModelAction.GENERATE,
        source="cli-probe",
    )
    consent.grant(
        ConsentGrant(
            provider="example-provider",
            model="model-a",
            region="region-a",
            purpose="answer-question",
            data_levels=frozenset({DataLevel.L1}),
            action_scopes=frozenset({ModelAction.GENERATE}),
            source_scopes=frozenset({"cli-probe"}),
            expires_at=9999999999,
        )
    )
    assert policy.authorize(OutboundRequest(**base))

    # A text-only grant must not authorize streaming or a tool proposal.
    for action in (ModelAction.STREAM, ModelAction.TOOL_PROPOSAL):
        assert not policy.authorize(OutboundRequest(**{**base, "action": action}))
    # A grant for one originating surface must not authorize another.
    assert not policy.authorize(OutboundRequest(**{**base, "source": "other-surface"}))


def test_revoked_grant_retains_revoked_status_and_blocks_new_requests() -> None:
    """FR-SEC-002 status field: revocation is observable, not merely absent."""
    consent = ConsentManager()
    policy = OutboundPolicy(consent)
    key = ("example-provider", "model-a", "region-a", "answer-question")
    consent.grant(
        ConsentGrant(
            provider=key[0],
            model=key[1],
            region=key[2],
            purpose=key[3],
            data_levels=frozenset({DataLevel.L1}),
            action_scopes=frozenset({ModelAction.GENERATE}),
            source_scopes=frozenset({"cli-probe"}),
            expires_at=9999999999,
        )
    )
    assert consent.exact_grant(*key).status is ConsentStatus.ACTIVE

    assert consent.revoke(*key) is True

    grant = consent.exact_grant(*key)
    assert grant is not None
    assert grant.status is ConsentStatus.REVOKED
    assert not policy.authorize(
        OutboundRequest(
            provider=key[0],
            model=key[1],
            region=key[2],
            purpose=key[3],
            data_level=DataLevel.L1,
            action=ModelAction.GENERATE,
            source="cli-probe",
        )
    )
    # Revoking an already-revoked grant reports no state change.
    assert consent.revoke(*key) is False
    assert consent.revoke("example-provider", "model-a", "region-a", "never-granted") is False
