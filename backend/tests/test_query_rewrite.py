"""
Tests for query_rewrite.py: the retrieval-retry helper that asks the
visitor's own model for period-vocabulary search keywords when the
first search+answer pass finds nothing citable (docs/decision-log.md).
Mocked llm_client calls only - no real network or API keys needed, same
approach as the rest of this suite.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
import llm_client
import query_rewrite


def test_returns_stripped_keywords_on_success():
    with patch("llm_client.complete", return_value="  Bhishma celibacy vow Ganga  \n"):
        result = query_rewrite.rewrite_query("openai", "key", "Did Bhishma get married?")
    assert result == "Bhishma celibacy vow Ganga"


def test_returns_none_on_llm_error():
    with patch("llm_client.complete", side_effect=llm_client.LLMError("rate_limit", "slow down")):
        result = query_rewrite.rewrite_query("openai", "key", "Did Bhishma get married?")
    assert result is None


def test_returns_none_on_empty_response():
    with patch("llm_client.complete", return_value="   "):
        result = query_rewrite.rewrite_query("openai", "key", "Did Bhishma get married?")
    assert result is None


def test_passes_provider_model_and_question_through():
    # complete_safe() calls llm_client.complete() positionally
    # (provider, api_key, system, user, model, max_tokens, timeout,
    # json_mode) - same call shape every other complete_safe caller in
    # this codebase (classifier.py, answer.py) relies on.
    with patch("llm_client.complete", return_value="keywords") as mock_complete:
        query_rewrite.rewrite_query(
            "anthropic", "key", "Did Draupadi have siblings?", model="claude-haiku-4-5-20251001"
        )
    args, _ = mock_complete.call_args
    provider, api_key, system, user, model = args[:5]
    assert provider == "anthropic"
    assert api_key == "key"
    assert user == "Did Draupadi have siblings?"
    assert model == "claude-haiku-4-5-20251001"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
