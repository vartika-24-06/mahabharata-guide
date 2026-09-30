"""Entry-screen POST /api/session-token: HMAC token issuance."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("SESSION_TOKEN_SECRET", "test-secret-not-for-prod")

import session_token


def test_issue_session_token_has_three_parts():
    token = session_token.issue_session_token()
    parts = token.split(":")
    assert len(parts) == 3  # nonce:timestamp:signature


def test_tokens_are_unique():
    tokens = {session_token.issue_session_token() for _ in range(20)}
    assert len(tokens) == 20


def test_missing_secret_raises_clear_error(monkeypatch):
    monkeypatch.delenv("SESSION_TOKEN_SECRET", raising=False)
    try:
        session_token.issue_session_token()
        assert False, "should have raised"
    except RuntimeError as e:
        assert "SESSION_TOKEN_SECRET" in str(e)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
