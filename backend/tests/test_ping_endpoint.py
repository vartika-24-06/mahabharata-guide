"""Entry-screen POST /api/ping: validates a visitor's key/model via a
minimal real completion call, mocked here - same approach as the other
endpoint test files (no real network)."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("SESSION_TOKEN_SECRET", "test-secret-not-for-prod")
os.environ.setdefault("OPENAI_API_KEY", "dummy")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "dummy")

import httpx
from fastapi.testclient import TestClient

import llm_client
import main

client = TestClient(main.app)


def test_missing_key_returns_400():
    response = client.post("/api/ping", json={"provider": "openai", "model": ""})
    assert response.status_code == 400
    assert response.json()["error"] == "missing_key"


def test_missing_provider_returns_400():
    response = client.post("/api/ping", json={}, headers={"X-Provider-Key": "k"})
    assert response.status_code == 400
    assert response.json()["error"] == "missing_provider"


def test_unknown_provider_returns_400_other():
    response = client.post(
        "/api/ping", json={"provider": "cohere"}, headers={"X-Provider-Key": "k"}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "other"


def test_success_returns_resolved_default_model():
    with patch("llm_client.complete", return_value="ok"):
        response = client.post(
            "/api/ping", json={"provider": "openai", "model": ""}, headers={"X-Provider-Key": "k"}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["model"] == "gpt-4o-mini"


def test_success_preserves_explicit_model():
    with patch("llm_client.complete", return_value="ok"):
        response = client.post(
            "/api/ping",
            json={"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
            headers={"X-Provider-Key": "k"},
        )
    assert response.status_code == 200
    assert response.json()["model"] == "claude-haiku-4-5-20251001"


def test_auth_error_maps_to_400():
    with patch("llm_client.complete", side_effect=llm_client.LLMError("auth", "bad key")):
        response = client.post(
            "/api/ping", json={"provider": "openai"}, headers={"X-Provider-Key": "k"}
        )
    assert response.status_code == 400
    assert response.json()["error"] == "auth"


def test_timeout_maps_to_504():
    with patch("llm_client.complete", side_effect=httpx.TimeoutException("timed out")):
        response = client.post(
            "/api/ping", json={"provider": "openai"}, headers={"X-Provider-Key": "k"}
        )
    assert response.status_code == 504
    assert response.json()["error"] == "timeout"


def test_network_error_maps_to_502():
    with patch("llm_client.complete", side_effect=httpx.ConnectError("no route")):
        response = client.post(
            "/api/ping", json={"provider": "openai"}, headers={"X-Provider-Key": "k"}
        )
    assert response.status_code == 502
    assert response.json()["error"] == "network"


def test_ping_uses_10_second_timeout():
    with patch("llm_client.complete", return_value="ok") as mock_complete:
        client.post("/api/ping", json={"provider": "openai"}, headers={"X-Provider-Key": "k"})
    assert mock_complete.call_args.kwargs["timeout"] == 10


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
