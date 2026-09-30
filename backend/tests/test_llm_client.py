"""
Tests for llm_client.py's pure logic: JSON extraction from model output,
and error normalization from mocked HTTP responses (no real network
calls or API keys needed - api.openai.com isn't even reachable from this
sandbox, per the network notes elsewhere in this project).

Run with: python -m pytest tests/test_llm_client.py -v
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
import llm_client


def test_extract_json_plain():
    assert llm_client.extract_json('{"label": "factual", "confidence": 0.9}') == \
        {"label": "factual", "confidence": 0.9}


def test_extract_json_with_code_fence():
    text = '```json\n{"label": "philosophical", "confidence": 0.8}\n```'
    assert llm_client.extract_json(text) == {"label": "philosophical", "confidence": 0.8}


def test_extract_json_with_surrounding_sentence():
    text = 'Here is the classification: {"label": "ambiguous", "confidence": 0.4} Hope that helps!'
    assert llm_client.extract_json(text) == {"label": "ambiguous", "confidence": 0.4}


def _mock_response(status_code, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    return resp


def test_openai_auth_error():
    with patch("httpx.post", return_value=_mock_response(401)):
        try:
            llm_client.complete("openai", "bad-key", "sys", "hello")
            assert False, "should have raised"
        except llm_client.LLMError as e:
            assert e.kind == "auth"


def test_openai_unknown_model():
    with patch("httpx.post", return_value=_mock_response(404)):
        try:
            llm_client.complete("openai", "key", "sys", "hello", model="not-a-real-model")
            assert False, "should have raised"
        except llm_client.LLMError as e:
            assert e.kind == "unknown_model"


def test_openai_rate_limit():
    with patch("httpx.post", return_value=_mock_response(429)):
        try:
            llm_client.complete("openai", "key", "sys", "hello")
            assert False, "should have raised"
        except llm_client.LLMError as e:
            assert e.kind == "rate_limit"


def test_openai_success():
    mock_resp = _mock_response(200, {"choices": [{"message": {"content": "hello back"}}]})
    with patch("httpx.post", return_value=mock_resp):
        result = llm_client.complete("openai", "key", "sys", "hello")
        assert result == "hello back"


def test_anthropic_success():
    mock_resp = _mock_response(200, {"content": [{"text": "hello back"}]})
    with patch("httpx.post", return_value=mock_resp):
        result = llm_client.complete("anthropic", "key", "sys", "hello")
        assert result == "hello back"


def test_anthropic_auth_error():
    with patch("httpx.post", return_value=_mock_response(403)):
        try:
            llm_client.complete("anthropic", "bad-key", "sys", "hello")
            assert False, "should have raised"
        except llm_client.LLMError as e:
            assert e.kind == "auth"


def test_gemini_success():
    mock_resp = _mock_response(200, {"candidates": [{"content": {"parts": [{"text": "hello back"}]}}]})
    with patch("httpx.post", return_value=mock_resp):
        result = llm_client.complete("gemini", "key", "sys", "hello")
        assert result == "hello back"


def test_unknown_provider():
    try:
        llm_client.complete("not-a-provider", "key", "sys", "hello")
        assert False, "should have raised"
    except llm_client.LLMError as e:
        assert e.kind == "other"


if __name__ == "__main__":
    test_extract_json_plain()
    test_extract_json_with_code_fence()
    test_extract_json_with_surrounding_sentence()
    test_openai_auth_error()
    test_openai_unknown_model()
    test_openai_rate_limit()
    test_openai_success()
    test_anthropic_success()
    test_anthropic_auth_error()
    test_gemini_success()
    test_unknown_provider()
    print("All llm_client tests passed.")


def test_complete_safe_wraps_timeout_as_llm_error():
    with patch("llm_client.httpx.post", side_effect=llm_client.httpx.TimeoutException("timed out")):
        try:
            llm_client.complete_safe("openai", "k", "sys", "user")
            assert False, "expected LLMError"
        except llm_client.LLMError as e:
            assert e.kind == "other"
            assert "timed out" in str(e)


def test_complete_safe_wraps_connection_error_as_llm_error():
    with patch("llm_client.httpx.post", side_effect=llm_client.httpx.ConnectError("refused")):
        try:
            llm_client.complete_safe("openai", "k", "sys", "user")
            assert False, "expected LLMError"
        except llm_client.LLMError as e:
            assert e.kind == "other"
            assert "Could not reach the provider" in str(e)


def test_complete_safe_still_raises_llm_error_from_http_status():
    mock_response = MagicMock(status_code=401)
    with patch("llm_client.httpx.post", return_value=mock_response):
        try:
            llm_client.complete_safe("openai", "k", "sys", "user")
            assert False, "expected LLMError"
        except llm_client.LLMError as e:
            assert e.kind == "auth"


def test_complete_safe_passes_through_on_success():
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
    with patch("llm_client.httpx.post", return_value=mock_response):
        assert llm_client.complete_safe("openai", "k", "sys", "user") == "ok"
