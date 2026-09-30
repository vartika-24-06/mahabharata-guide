"""
Task 21: redaction test for both keys.

Confirms neither the VISITOR's key (X-Provider-Key, read into
request.state.provider_key by HeaderRedactionMiddleware) nor OUR OWN
server-side embeddings key (search.py's openai_client) ever appears in
any log line - in the normal path and in the degraded (embeddings-
failure, keyword-only) path.

test_entry_middleware.py already proves the mechanism (the header is
gone from request.scope by the time a route handler runs). This file
checks the other half of the guarantee empirically: that when a REAL
provider/Supabase client call actually fails (not a mocked exception
message someone hand-wrote), the resulting exception - which is what
search.py's degraded-path print() interpolates - doesn't happen to
carry the key in its str()/repr(), the way some HTTP client libraries
embed request details (headers, URLs with query-string keys) in error
messages. Both are pointed at an unreachable host (127.0.0.1:1) so the
failure is genuine, not simulated with a canned exception.

Run with: python -m pytest tests/test_key_redaction.py -v
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import openai
from fastapi.testclient import TestClient
from supabase import create_client

import main
import search

client = TestClient(main.app)

UNREACHABLE_HOST = "http://127.0.0.1:1"  # connection refused, always - no network needed

VISITOR_CANARY = "sk-VISITOR-CANARY-do-not-leak-7f3a9c"
SERVER_CANARY = "sk-SERVER-EMBEDDINGS-CANARY-do-not-leak-1e8b02"
SUPABASE_CANARY = "sb-SUPABASE-SERVICE-CANARY-do-not-leak-44d1"


def _canary_openai_client():
    return openai.OpenAI(api_key=SERVER_CANARY, base_url=f"{UNREACHABLE_HOST}/v1")


def _canary_supabase_client():
    return create_client(UNREACHABLE_HOST, SUPABASE_CANARY)


def test_embeddings_failure_message_does_not_contain_server_key(capsys):
    """The exact call search.hybrid_search() makes when the embeddings
    API is unreachable - real client, real (connection-refused) failure,
    real exception flowing into the real print() at search.py's
    degraded-search branch."""
    bm25_index = search.load_bm25_index()
    results, degraded = search.hybrid_search(
        query="Did Bhishma get married?",
        bm25_index=bm25_index,
        openai_client=_canary_openai_client(),
        supabase_client=_canary_supabase_client(),
    )
    assert degraded is True

    captured = capsys.readouterr()
    assert SERVER_CANARY not in captured.out
    assert SERVER_CANARY not in captured.err


def test_supabase_text_fill_failure_message_does_not_contain_server_key(capsys):
    """search.fill_missing_text()'s own try/except (search.py:155) - hit
    whenever a BM25-only result needs its text looked up and that lookup
    fails."""
    results = [{"meta": {"parva_file": "maha01.txt", "book_number": 1,
                          "parva_name": "ADI PARVA", "section": 1, "passage_index": 0}}]
    search.fill_missing_text(_canary_supabase_client(), results)

    captured = capsys.readouterr()
    assert SUPABASE_CANARY not in captured.out
    assert SUPABASE_CANARY not in captured.err


def test_ask_endpoint_degraded_path_never_logs_either_key(capsys):
    """Full /api/ask request: a real visitor key header (canary),
    real degraded search (canary server key, unreachable host), and a
    mocked classifier/answer (Task 11/12 already have their own
    provider-call tests - this test's job is only to confirm neither key
    leaks anywhere in stdout/stderr across the full request, not to
    re-verify classify/answer logic)."""
    main.resources.update({
        "bm25_index": search.load_bm25_index(),
        "openai_client": _canary_openai_client(),
        "supabase_client": _canary_supabase_client(),
    })

    mock_answer = '{"answer": "Bhishma never married.", "used_ids": [1]}'
    with patch("classifier.classify_question",
               return_value={"label": "factual", "confidence": 0.9, "raw_label": "factual"}), \
         patch("llm_client.complete", return_value=mock_answer):
        response = client.post(
            "/api/ask",
            json={"provider": "openai", "question": "Did Bhishma get married?"},
            headers={"X-Provider-Key": VISITOR_CANARY, "X-Session-Token": "fake-token"},
        )

    assert response.status_code == 200
    assert response.json().get("meaning_search_degraded") is True

    captured = capsys.readouterr()
    assert VISITOR_CANARY not in captured.out
    assert VISITOR_CANARY not in captured.err
    assert SERVER_CANARY not in captured.out
    assert SERVER_CANARY not in captured.err
    # Belt and suspenders: the key shouldn't be echoed into the JSON
    # response body either, though that's a different guarantee than
    # "never logged".
    assert VISITOR_CANARY not in response.text
    assert SERVER_CANARY not in response.text


def test_story_typed_endpoint_degraded_path_never_logs_either_key(capsys):
    """story_endpoint.py's "typed" request path calls the same
    search.hybrid_search() as /api/ask - confirmed separately since it's
    a different call site, not because the underlying risk differs."""
    catalogue = {"characters": [], "parvas": []}
    main.resources.update({
        "bm25_index": search.load_bm25_index(),
        "openai_client": _canary_openai_client(),
        "supabase_client": _canary_supabase_client(),
        "catalogue": catalogue,
    })

    mock_story = '{"text": "A short story about Bhishma.", "used_ids": [1]}'
    with patch("story.write_snippet", return_value={"text": "A short story about Bhishma.", "used_ids": [1]}):
        response = client.post(
            "/api/story",
            json={"provider": "openai", "request_type": "typed", "text": "Tell me about Bhishma"},
            headers={"X-Provider-Key": VISITOR_CANARY, "X-Session-Token": "fake-token"},
        )

    captured = capsys.readouterr()
    assert VISITOR_CANARY not in captured.out
    assert VISITOR_CANARY not in captured.err
    assert SERVER_CANARY not in captured.out
    assert SERVER_CANARY not in captured.err
    assert VISITOR_CANARY not in response.text
    assert SERVER_CANARY not in response.text
