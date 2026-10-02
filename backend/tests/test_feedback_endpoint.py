"""
UX item 7 tests: POST /api/feedback, mocking the Supabase insert - no
real network, same approach as the other endpoint test files.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)
# Same reasoning as test_qna_endpoint.py: lifespan doesn't run under a
# plain TestClient call, and every test here mocks the supabase client
# directly, so the real resource values never matter.
main.resources.update({"bm25_index": None, "openai_client": None, "supabase_client": None})

VALID_BODY = {
    "question": "What does Vidura say about greed?",
    "answer_type": "philosophical",
    "answer_text": "Vidura counsels against covetousness...",
    "citations": [
        {"parva_name": "UDYOGA PARVA", "section": 33, "excerpt": "Sleeplessness overtaketh..."}
    ],
    "rating": "up",
    "provider": "openai",
    "model": "gpt-4o-mini",
}


def test_valid_feedback_is_inserted_and_returns_ok():
    fake_supabase = MagicMock()
    main.resources["supabase_client"] = fake_supabase

    response = client.post("/api/feedback", json=VALID_BODY)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    fake_supabase.table.assert_called_once_with("feedback")
    inserted = fake_supabase.table.return_value.insert.call_args[0][0]
    assert inserted["question"] == VALID_BODY["question"]
    assert inserted["rating"] == "up"
    assert inserted["citations"][0]["parva_name"] == "UDYOGA PARVA"


def test_invalid_rating_returns_400():
    body = {**VALID_BODY, "rating": "sideways"}
    response = client.post("/api/feedback", json=body)
    assert response.status_code == 400
    assert response.json()["error"] == "other"


def test_blank_question_returns_400():
    body = {**VALID_BODY, "question": "   "}
    response = client.post("/api/feedback", json=body)
    assert response.status_code == 400


def test_supabase_failure_returns_502_not_500():
    fake_supabase = MagicMock()
    fake_supabase.table.return_value.insert.return_value.execute.side_effect = Exception("boom")
    main.resources["supabase_client"] = fake_supabase

    response = client.post("/api/feedback", json=VALID_BODY)

    assert response.status_code == 502
    assert response.json()["error"] == "other"


def test_citations_default_to_empty_list():
    body = {k: v for k, v in VALID_BODY.items() if k != "citations"}
    fake_supabase = MagicMock()
    main.resources["supabase_client"] = fake_supabase

    response = client.post("/api/feedback", json=body)

    assert response.status_code == 200
    inserted = fake_supabase.table.return_value.insert.call_args[0][0]
    assert inserted["citations"] == []
