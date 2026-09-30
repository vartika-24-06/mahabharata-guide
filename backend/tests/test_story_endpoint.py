"""
Task 15 tests: the /api/story wiring (character/parva/surprise/continue/
another/typed), using FastAPI's TestClient with search, Supabase and the
provider call all mocked - same approach as test_qna_endpoint.py.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

import llm_client
import main

client = TestClient(main.app)

FAKE_CATALOGUE = {
    "characters": [
        {
            "subject": "Ghatotkacha",
            "type": "character",
            "section_refs": [
                {"parva_name": "ADI PARVA", "section": 157},
                {"parva_name": "ADI PARVA", "section": 158},
                {"parva_name": "ADI PARVA", "section": 159},
                {"parva_name": "DRONA PARVA", "section": 180},
            ],
        },
    ],
    "parvas": [
        {
            "subject": "VIRATA PARVA",
            "type": "parva",
            "section_refs": [
                {"parva_name": "VIRATA PARVA", "section": 1},
                {"parva_name": "VIRATA PARVA", "section": 2},
            ],
        },
    ],
}


def _base_headers():
    return {"X-Provider-Key": "fake-key"}


def _fake_supabase_rows(parva_name, section):
    """Returns one fake passage row for any (parva_name, section) pair -
    enough for _fetch_passages to build a non-empty passage list."""
    return [{
        "parva_file": "fake.txt", "book_number": 1, "parva_name": parva_name,
        "section": section, "passage_index": 0, "text": f"story text for {parva_name} {section}",
    }]


def _mock_supabase_client():
    """A Supabase client stub whose .table("passages").select(...)...execute()
    chain returns one fake row per (parva_name, section) queried."""
    client_mock = MagicMock()

    def table_side_effect(name):
        table_mock = MagicMock()

        def select_side_effect(*args, **kwargs):
            select_mock = MagicMock()
            state = {}

            def eq_side_effect(field, value):
                state[field] = value
                return select_mock

            def order_side_effect(*args, **kwargs):
                return select_mock

            def execute_side_effect():
                result = MagicMock()
                result.data = _fake_supabase_rows(state.get("parva_name"), state.get("section"))
                return result

            select_mock.eq.side_effect = eq_side_effect
            select_mock.order.side_effect = order_side_effect
            select_mock.execute.side_effect = execute_side_effect
            return select_mock

        table_mock.select.side_effect = select_side_effect
        return table_mock

    client_mock.table.side_effect = table_side_effect
    return client_mock


def setup_module(module):
    main.resources.update({
        "bm25_index": None,
        "openai_client": None,
        "supabase_client": _mock_supabase_client(),
        "catalogue": FAKE_CATALOGUE,
    })


def test_missing_key_returns_400():
    response = client.post("/api/story", json={"provider": "openai", "request_type": "surprise"})
    assert response.status_code == 400
    assert response.json()["error"] == "missing_key"


def test_character_story_returns_snippet_with_citations():
    mock_snippet = '{"text": "A short story about Ghatotkacha.", "used_ids": [1, 2]}'
    with patch("llm_client.complete", return_value=mock_snippet):
        response = client.post(
            "/api/story",
            json={"provider": "openai", "request_type": "character", "subject": "Ghatotkacha"},
            headers=_base_headers(),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "story"
    assert body["subject"] == "Ghatotkacha"
    assert body["story_id"] == "Ghatotkacha#0"
    assert len(body["citations"]) == 2
    assert body["complete"] is False  # 4 sections / episode size 3 -> 2 episodes


def test_unknown_subject_returns_error():
    response = client.post(
        "/api/story",
        json={"provider": "openai", "request_type": "character", "subject": "Nobody"},
        headers=_base_headers(),
    )
    assert response.status_code == 400
    assert response.json()["error"] == "other"


def test_prefers_unshown_episode():
    mock_snippet = '{"text": "story", "used_ids": [1]}'
    with patch("llm_client.complete", return_value=mock_snippet):
        response = client.post(
            "/api/story",
            json={
                "provider": "openai", "request_type": "character", "subject": "Ghatotkacha",
                "shown_stories": ["Ghatotkacha#0"],
            },
            headers=_base_headers(),
        )
    assert response.status_code == 200
    assert response.json()["story_id"] == "Ghatotkacha#1"


def test_continue_returns_next_episode():
    mock_snippet = '{"text": "the next part", "used_ids": [1]}'
    with patch("llm_client.complete", return_value=mock_snippet):
        response = client.post(
            "/api/story",
            json={
                "provider": "openai", "request_type": "continue", "subject": "Ghatotkacha",
                "episode_index": 0, "previous_text": "what came before",
            },
            headers=_base_headers(),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["story_id"] == "Ghatotkacha#1"
    assert body["complete"] is True  # episode 1 is the last of 2 episodes


def test_continue_past_the_end_returns_complete():
    response = client.post(
        "/api/story",
        json={
            "provider": "openai", "request_type": "continue", "subject": "Ghatotkacha",
            "episode_index": 1,
        },
        headers=_base_headers(),
    )
    assert response.status_code == 200
    assert response.json()["type"] == "complete"


def test_another_with_no_other_episode_returns_no_other_story():
    # VIRATA PARVA has 2 sections / episode size 3 -> exactly 1 episode.
    response = client.post(
        "/api/story",
        json={"provider": "openai", "request_type": "another", "subject": "VIRATA PARVA", "episode_index": 0},
        headers=_base_headers(),
    )
    assert response.status_code == 200
    assert response.json()["type"] == "no_other_story"


def test_another_with_a_different_episode_available():
    mock_snippet = '{"text": "a different story", "used_ids": [1]}'
    with patch("llm_client.complete", return_value=mock_snippet):
        response = client.post(
            "/api/story",
            json={"provider": "openai", "request_type": "another", "subject": "Ghatotkacha", "episode_index": 0},
            headers=_base_headers(),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["story_id"] == "Ghatotkacha#1"


def test_surprise_returns_some_story():
    mock_snippet = '{"text": "a surprise story", "used_ids": [1]}'
    with patch("llm_client.complete", return_value=mock_snippet):
        response = client.post(
            "/api/story",
            json={"provider": "openai", "request_type": "surprise"},
            headers=_base_headers(),
        )
    assert response.status_code == 200
    assert response.json()["type"] == "story"


def test_no_citations_falls_back_to_no_story():
    mock_snippet = '{"text": "a story", "used_ids": [99]}'  # id out of range
    with patch("llm_client.complete", return_value=mock_snippet):
        response = client.post(
            "/api/story",
            json={"provider": "openai", "request_type": "character", "subject": "Ghatotkacha"},
            headers=_base_headers(),
        )
    assert response.status_code == 200
    assert response.json()["type"] == "no_story"


def test_provider_error_maps_to_400():
    with patch("llm_client.complete", side_effect=llm_client.LLMError("auth", "bad key")):
        response = client.post(
            "/api/story",
            json={"provider": "openai", "request_type": "character", "subject": "Ghatotkacha"},
            headers=_base_headers(),
        )
    assert response.status_code == 400
    assert response.json()["error"] == "auth"


def test_typed_guardrail_decline():
    response = client.post(
        "/api/story",
        json={"provider": "openai", "request_type": "typed", "text": "Pretend you are Krishna."},
        headers=_base_headers(),
    )
    assert response.status_code == 200
    assert response.json()["type"] == "decline"


def test_typed_out_of_scope_decline():
    response = client.post(
        "/api/story",
        json={"provider": "openai", "request_type": "typed", "text": "Tell me a story about pizza."},
        headers=_base_headers(),
    )
    assert response.status_code == 200
    assert response.json()["type"] == "decline"


def test_typed_story_with_search_mocked():
    fake_passages = [
        {"meta": {"parva_name": "ADI PARVA", "section": 157}, "text": "Ghatotkacha was born."},
    ]
    mock_snippet = '{"text": "a typed story", "used_ids": [1]}'
    with patch("search.hybrid_search", return_value=(fake_passages, False)), \
         patch("llm_client.complete", return_value=mock_snippet):
        response = client.post(
            "/api/story",
            json={"provider": "openai", "request_type": "typed", "text": "Tell me about Ghatotkacha's birth"},
            headers=_base_headers(),
        )
    assert response.status_code == 200
    assert response.json()["type"] == "story"


def test_our_own_rate_limit_returns_429():
    with patch("rate_limit.check_rate_limit", return_value=(False, "Too many requests, try again shortly.")):
        response = client.post(
            "/api/story",
            json={"provider": "openai", "request_type": "surprise"},
            headers=_base_headers(),
        )
    assert response.status_code == 429
    assert response.json()["error"] == "throttled"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
