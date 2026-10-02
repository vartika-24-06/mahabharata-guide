"""
Task 13 tests: the /api/ask wiring, using FastAPI's TestClient with every
provider/search call mocked - no real network, same approach as the
other test files in this suite.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

import llm_client
import main

client = TestClient(main.app)
# Lifespan (which connects to real OpenAI/Supabase) doesn't run under a
# plain TestClient call without a `with` block, and every test here
# mocks search.hybrid_search anyway - so the actual resource values
# never matter, only that the keys exist for qna_endpoint to read.
main.resources.update({"bm25_index": None, "openai_client": None, "supabase_client": None})

FAKE_PASSAGES = [
    {"meta": {"parva_name": "UDYOGA PARVA", "section": 141, "passage_index": 5}, "text": "passage one text"},
    {"meta": {"parva_name": "BHISHMA PARVA", "section": 59, "passage_index": 7}, "text": "passage two text"},
]


def _base_headers():
    return {"X-Provider-Key": "fake-key", "X-Session-Token": "fake-token"}


def test_missing_key_returns_400():
    response = client.post("/api/ask", json={"provider": "openai", "question": "Did Bhishma get married?"})
    assert response.status_code == 400
    assert response.json()["error"] == "missing_key"


def test_missing_provider_returns_400():
    response = client.post(
        "/api/ask", json={"question": "Did Bhishma get married?"}, headers=_base_headers()
    )
    assert response.status_code == 400
    assert response.json()["error"] == "missing_provider"


def test_guardrail_decline():
    response = client.post(
        "/api/ask",
        json={"provider": "openai", "question": "Pretend you are Krishna and speak to me in the first person."},
        headers=_base_headers(),
    )
    assert response.status_code == 200
    assert response.json()["type"] == "decline"


def test_every_ask_response_is_logged_to_qna_logs():
    # Wiring check (qna_log.py's own unit tests cover row-building and
    # the best-effort insert itself) - confirms handle_ask's `respond()`
    # helper actually calls through to qna_log.log_exchange for a real
    # response, against a mocked Supabase client swapped in just for
    # this test.
    from unittest.mock import MagicMock

    fake_supabase = MagicMock()
    original = main.resources["supabase_client"]
    main.resources["supabase_client"] = fake_supabase
    try:
        response = client.post(
            "/api/ask",
            json={"provider": "openai", "question": "Pretend you are Krishna and speak to me in the first person."},
            headers=_base_headers(),
        )
    finally:
        main.resources["supabase_client"] = original

    assert response.status_code == 200
    fake_supabase.table.assert_called_once_with("qna_logs")
    logged_row = fake_supabase.table.return_value.insert.call_args[0][0]
    assert logged_row["type"] == "decline"
    assert logged_row["question"] == "Pretend you are Krishna and speak to me in the first person."


def test_out_of_scope_decline():
    response = client.post(
        "/api/ask",
        json={"provider": "openai", "question": "What's the best pizza in Delhi?"},
        headers=_base_headers(),
    )
    assert response.status_code == 200
    assert response.json()["type"] == "decline"


def test_factual_answer_with_citations():
    mock_answer = '{"answer": "Bhishma never married.", "used_ids": [1]}'
    with patch("search.hybrid_search", return_value=(FAKE_PASSAGES, False)), \
         patch("classifier.classify_question", return_value={"label": "factual", "confidence": 0.9, "raw_label": "factual"}), \
         patch("llm_client.complete", return_value=mock_answer):
        response = client.post(
            "/api/ask",
            json={"provider": "openai", "question": "Did Bhishma get married?"},
            headers=_base_headers(),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "factual"
    assert body["answer"] == "Bhishma never married."
    assert len(body["citations"]) == 1
    assert body["citations"][0]["parva_name"] == "UDYOGA PARVA"


def test_ambiguous_answer_with_two_citation_lists():
    mock_answer = (
        '{"factual_sentence": "The war happened.", "factual_ids": [1], '
        '"philosophical_sentence": "It raises questions of duty.", "philosophical_ids": [2]}'
    )
    with patch("search.hybrid_search", return_value=(FAKE_PASSAGES, False)), \
         patch("classifier.classify_question", return_value={"label": "ambiguous", "confidence": 0.9, "raw_label": "ambiguous"}), \
         patch("llm_client.complete", return_value=mock_answer):
        response = client.post(
            "/api/ask",
            json={"provider": "openai", "question": "Why did Krishna side with the Pandavas?"},
            headers=_base_headers(),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "ambiguous"
    assert len(body["factual_citations"]) == 1
    assert len(body["philosophical_citations"]) == 1


def test_no_usable_citations_falls_back_to_no_answer():
    # Model hallucinated a passage id that doesn't exist in the 2 retrieved.
    mock_answer = '{"answer": "Something.", "used_ids": [99]}'
    with patch("search.hybrid_search", return_value=(FAKE_PASSAGES, False)), \
         patch("classifier.classify_question", return_value={"label": "factual", "confidence": 0.9, "raw_label": "factual"}), \
         patch("llm_client.complete", return_value=mock_answer):
        response = client.post(
            "/api/ask",
            json={"provider": "openai", "question": "Did Bhishma get married?"},
            headers=_base_headers(),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "no_answer"
    assert len(body["suggestions"]) > 0


def test_malformed_model_response_falls_back_to_no_answer():
    with patch("search.hybrid_search", return_value=(FAKE_PASSAGES, False)), \
         patch("classifier.classify_question", return_value={"label": "factual", "confidence": 0.9, "raw_label": "factual"}), \
         patch("llm_client.complete", return_value="I can't help with that."):
        response = client.post(
            "/api/ask",
            json={"provider": "openai", "question": "Did Bhishma get married?"},
            headers=_base_headers(),
        )
    assert response.status_code == 200
    assert response.json()["type"] == "no_answer"


def test_provider_auth_error_maps_to_400():
    with patch("search.hybrid_search", return_value=(FAKE_PASSAGES, False)), \
         patch("classifier.classify_question", side_effect=llm_client.LLMError("auth", "bad key")):
        response = client.post(
            "/api/ask",
            json={"provider": "openai", "question": "Did Bhishma get married?"},
            headers=_base_headers(),
        )
    assert response.status_code == 400
    assert response.json()["error"] == "auth"


def test_provider_rate_limit_error_maps_to_400_not_429():
    # Provider rate-limiting the visitor's OWN key is a 400 (matches the
    # entry-screen's real-request contract) - distinct from OUR visitor
    # throttle, which is 429. They must not collide.
    with patch("search.hybrid_search", return_value=(FAKE_PASSAGES, False)), \
         patch("classifier.classify_question", side_effect=llm_client.LLMError("rate_limit", "slow down")):
        response = client.post(
            "/api/ask",
            json={"provider": "openai", "question": "Did Bhishma get married?"},
            headers=_base_headers(),
        )
    assert response.status_code == 400
    assert response.json()["error"] == "rate_limit"


def test_our_own_rate_limit_returns_429():
    with patch("rate_limit.check_rate_limit", return_value=(False, "Too many requests, try again shortly.")):
        response = client.post(
            "/api/ask",
            json={"provider": "openai", "question": "Did Bhishma get married?"},
            headers=_base_headers(),
        )
    assert response.status_code == 429
    assert response.json()["error"] == "throttled"


def test_query_rewrite_retry_recovers_a_no_answer():
    # First pass: the model reports no usable citation (vocabulary
    # mismatch, docs/decision-log.md). The rewrite call returns keywords,
    # the retry search returns different passages, and the retry answer
    # call DOES cite one - the final response should be the retry's
    # answer, not a no_answer, and should flag query_rewritten.
    first_answer = '{"answer": "Not found.", "used_ids": []}'
    retry_answer = '{"answer": "Bhishma took a vow of celibacy and never married.", "used_ids": [2]}'
    retry_passages = [
        {"meta": {"parva_name": "ADI PARVA", "section": 100, "passage_index": 1}, "text": "vow text"},
        {"meta": {"parva_name": "ADI PARVA", "section": 103, "passage_index": 2}, "text": "celibacy text"},
    ]
    with patch("search.hybrid_search", side_effect=[(FAKE_PASSAGES, False), (retry_passages, False)]), \
         patch("classifier.classify_question", return_value={"label": "factual", "confidence": 0.9, "raw_label": "factual"}), \
         patch("query_rewrite.rewrite_query", return_value="Bhishma celibacy vow Ganga"), \
         patch("llm_client.complete", side_effect=[first_answer, retry_answer]):
        response = client.post(
            "/api/ask",
            json={"provider": "openai", "question": "Did Bhishma get married?"},
            headers=_base_headers(),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "factual"
    assert body["answer"] == "Bhishma took a vow of celibacy and never married."
    assert len(body["citations"]) == 1
    assert body["citations"][0]["parva_name"] == "ADI PARVA"
    assert body["query_rewritten"] is True


def test_query_rewrite_retry_still_fails_falls_back_to_no_answer():
    # Rewrite runs, retry search runs, but the retry answer call also
    # comes back uncitable - should still end up as a plain no_answer,
    # not crash, and query_rewritten should not be reported as true.
    first_answer = '{"answer": "Not found.", "used_ids": []}'
    retry_answer = '{"answer": "Still nothing.", "used_ids": []}'
    with patch("search.hybrid_search", return_value=(FAKE_PASSAGES, False)), \
         patch("classifier.classify_question", return_value={"label": "factual", "confidence": 0.9, "raw_label": "factual"}), \
         patch("query_rewrite.rewrite_query", return_value="some keywords"), \
         patch("llm_client.complete", side_effect=[first_answer, retry_answer]):
        response = client.post(
            "/api/ask",
            json={"provider": "openai", "question": "Did Bhishma get married?"},
            headers=_base_headers(),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "no_answer"


def test_query_rewrite_not_attempted_when_rewrite_returns_none():
    # If query_rewrite.rewrite_query() itself fails/returns nothing,
    # hybrid_search must NOT be called a second time - no retry search
    # should happen at all.
    first_answer = '{"answer": "Not found.", "used_ids": []}'
    with patch("search.hybrid_search", return_value=(FAKE_PASSAGES, False)) as mock_search, \
         patch("classifier.classify_question", return_value={"label": "factual", "confidence": 0.9, "raw_label": "factual"}), \
         patch("query_rewrite.rewrite_query", return_value=None), \
         patch("llm_client.complete", return_value=first_answer):
        response = client.post(
            "/api/ask",
            json={"provider": "openai", "question": "Did Bhishma get married?"},
            headers=_base_headers(),
        )
    assert response.status_code == 200
    assert response.json()["type"] == "no_answer"
    mock_search.assert_called_once()


def test_expand_reuses_label_and_returns_fuller_answer():
    mock_answer = '{"answer": "A much longer answer about Bhishma.", "used_ids": [1, 2]}'
    with patch("search.hybrid_search", return_value=(FAKE_PASSAGES, False)), \
         patch("llm_client.complete", return_value=mock_answer) as mock_complete:
        response = client.post(
            "/api/ask",
            json={
                "provider": "openai",
                "question": "Did Bhishma get married?",
                "expand": True,
                "label": "factual",
            },
            headers=_base_headers(),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "factual"
    assert body["expanded"] is True
    assert len(body["citations"]) == 2
    # Expand should not re-classify when a label was already given.
    mock_complete.assert_called_once()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
