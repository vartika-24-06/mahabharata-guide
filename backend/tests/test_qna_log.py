"""Tests for qna_log.py's row-building and best-effort insert - no real
network, same approach as the other test files in this suite."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import qna_log


def test_build_row_factual():
    payload = {"type": "factual", "answer": "Bhishma never married.", "citations": [{"parva_name": "X", "section": 1, "excerpt": "..."}]}
    row = qna_log.build_row("Did Bhishma marry?", payload, "openai", "gpt-4o-mini")
    assert row["type"] == "factual"
    assert row["answer_text"] == "Bhishma never married."
    assert row["citations"] == payload["citations"]
    assert row["provider"] == "openai"
    assert row["model"] == "gpt-4o-mini"
    assert row["expanded"] is False


def test_build_row_ambiguous_combines_both_sentences_and_citation_lists():
    payload = {
        "type": "ambiguous",
        "factual_sentence": "Factually, X happened.",
        "factual_citations": [{"parva_name": "A", "section": 1, "excerpt": "a"}],
        "philosophical_sentence": "Philosophically, Y follows.",
        "philosophical_citations": [{"parva_name": "B", "section": 2, "excerpt": "b"}],
    }
    row = qna_log.build_row("Some ambiguous question?", payload, "anthropic", None)
    assert row["answer_text"] == "Factually, X happened. Philosophically, Y follows."
    assert len(row["citations"]) == 2


def test_build_row_decline_and_no_answer_have_no_citations():
    decline_row = qna_log.build_row("q", {"type": "decline", "message": "Can't help with that."}, "openai", None)
    assert decline_row["answer_text"] == "Can't help with that."
    assert decline_row["citations"] == []

    no_answer_row = qna_log.build_row(
        "q", {"type": "no_answer", "message": "Not covered.", "suggestions": ["X"]}, "openai", None
    )
    assert no_answer_row["answer_text"] == "Not covered."
    assert no_answer_row["citations"] == []


def test_build_row_carries_expand_and_retrieval_diagnostics():
    payload = {
        "type": "philosophical",
        "expanded": True,
        "answer": "Longer answer.",
        "citations": [],
        "meaning_search_degraded": True,
        "query_rewritten": True,
        "classifier_confidence": 0.42,
    }
    row = qna_log.build_row("q", payload, "gemini", "gemini-3.5-flash-lite")
    assert row["expanded"] is True
    assert row["meaning_search_degraded"] is True
    assert row["query_rewritten"] is True
    assert row["classifier_confidence"] == 0.42


def test_log_exchange_inserts_into_qna_logs_table():
    fake_supabase = MagicMock()
    resources = {"supabase_client": fake_supabase}
    row = {"question": "q", "type": "factual"}

    qna_log.log_exchange(resources, row)

    fake_supabase.table.assert_called_once_with("qna_logs")
    fake_supabase.table.return_value.insert.assert_called_once_with(row)


def test_log_exchange_is_a_noop_with_no_supabase_client():
    # Matches how the existing test suite exercises handle_ask -
    # resources["supabase_client"] is set to None there.
    qna_log.log_exchange({"supabase_client": None}, {"question": "q"})  # must not raise


def test_log_exchange_swallows_supabase_failures():
    fake_supabase = MagicMock()
    fake_supabase.table.return_value.insert.return_value.execute.side_effect = Exception("boom")
    resources = {"supabase_client": fake_supabase}

    qna_log.log_exchange(resources, {"question": "q"})  # must not raise
