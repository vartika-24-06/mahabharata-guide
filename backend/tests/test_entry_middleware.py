"""HeaderRedactionMiddleware and ThrottleMiddleware, tested against a
tiny standalone Starlette app (not the full main.py) so the throttle's
in-memory buckets start clean for each test and aren't shared with
test_ping_endpoint.py's requests."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("SESSION_TOKEN_SECRET", "test-secret-not-for-prod")

import llm_client
import ping_endpoint
from entry_middleware import HeaderRedactionMiddleware, ThrottleMiddleware
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


def _fresh_app():
    """A fresh FastAPI app + fresh throttle buckets per test, so tests
    don't leak state into each other via the module-level dicts."""
    import entry_middleware
    entry_middleware._ip_buckets.clear()
    entry_middleware._session_buckets.clear()
    entry_middleware._session_token_issue_log.clear()

    app = FastAPI()
    app.add_middleware(HeaderRedactionMiddleware)
    app.add_middleware(ThrottleMiddleware)

    @app.post("/api/ping")
    async def ping(request: Request, body: ping_endpoint.PingRequest):
        return await ping_endpoint.handle_ping(request, body)

    @app.post("/api/session-token")
    async def session_token():
        return {"session_token": "fake-token-for-test"}

    @app.get("/inspect-headers")
    async def inspect_headers(request: Request):
        # Only reachable in tests - proves the key was actually stripped
        # from request.scope["headers"] by the time a handler runs.
        raw_header_names = [name.decode().lower() for name, _ in request.scope["headers"]]
        return {
            "x_provider_key_in_scope_headers": "x-provider-key" in raw_header_names,
            "provider_key_from_state": getattr(request.state, "provider_key", None),
        }

    return app


def test_header_redaction_strips_key_from_scope_but_keeps_it_on_state():
    client = TestClient(_fresh_app())
    response = client.get("/inspect-headers", headers={"X-Provider-Key": "sk-secret-123"})
    body = response.json()
    assert body["x_provider_key_in_scope_headers"] is False
    assert body["provider_key_from_state"] == "sk-secret-123"


def test_session_token_rate_limit_trips_after_30_requests():
    client = TestClient(_fresh_app())
    for _ in range(30):
        response = client.post("/api/session-token")
        assert response.status_code == 200
    response = client.post("/api/session-token")
    assert response.status_code == 429
    assert response.json()["error"] == "throttle"
    assert "Retry-After" in response.headers


def test_ping_ip_cooldown_after_repeated_auth_failures():
    client = TestClient(_fresh_app())
    with patch("llm_client.complete", side_effect=llm_client.LLMError("auth", "bad key")):
        # A distinct X-Session-Token per request isolates the IP-level
        # bucket from the per-token consecutive-failure bucket (tested
        # separately below) - otherwise the same "anonymous" token would
        # trip its own 5-failure cooldown first.
        for i in range(20):
            response = client.post(
                "/api/ping", json={"provider": "openai"},
                headers={"X-Provider-Key": "bad-key", "X-Session-Token": f"tab-{i}"},
            )
            assert response.status_code == 400

        # The 20th failure should have tripped the IP cooldown.
        response = client.post(
            "/api/ping", json={"provider": "openai"},
            headers={"X-Provider-Key": "bad-key", "X-Session-Token": "tab-final"},
        )
    assert response.status_code == 429
    assert response.json()["error"] == "throttle"


def test_ping_session_cooldown_after_5_consecutive_failures_same_token():
    client = TestClient(_fresh_app())
    headers = {"X-Provider-Key": "bad-key", "X-Session-Token": "tab-1"}
    with patch("llm_client.complete", side_effect=llm_client.LLMError("auth", "bad key")):
        for _ in range(5):
            client.post("/api/ping", json={"provider": "openai"}, headers=headers)
        response = client.post("/api/ping", json={"provider": "openai"}, headers=headers)
    assert response.status_code == 429


def test_rate_limit_and_other_errors_do_not_count_toward_ping_cooldown():
    # design.md: only auth/unknown_model count. A string of rate_limit
    # failures should never trip the cooldown.
    client = TestClient(_fresh_app())
    with patch("llm_client.complete", side_effect=llm_client.LLMError("rate_limit", "slow down")):
        for _ in range(25):
            response = client.post(
                "/api/ping", json={"provider": "openai"}, headers={"X-Provider-Key": "k"}
            )
    assert response.status_code == 400
    assert response.json()["error"] == "rate_limit"


def test_success_resets_session_failure_counter():
    client = TestClient(_fresh_app())
    headers = {"X-Provider-Key": "k", "X-Session-Token": "tab-2"}
    with patch("llm_client.complete", side_effect=llm_client.LLMError("auth", "bad key")):
        for _ in range(4):
            client.post("/api/ping", json={"provider": "openai"}, headers=headers)
    with patch("llm_client.complete", return_value="ok"):
        success = client.post("/api/ping", json={"provider": "openai"}, headers=headers)
        assert success.status_code == 200
    # Counter reset by the success above - 4 more failures shouldn't trip
    # the 5-consecutive-failure threshold.
    with patch("llm_client.complete", side_effect=llm_client.LLMError("auth", "bad key")):
        for _ in range(4):
            response = client.post("/api/ping", json={"provider": "openai"}, headers=headers)
    assert response.status_code == 400  # not yet throttled


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
