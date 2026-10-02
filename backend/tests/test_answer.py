"""
Task 12 tests: citation building (the correctness-critical part - a
citation must never be fabricated or point to a passage that wasn't
actually retrieved) and answer-writing with a mocked LLM call.

Run with: python -m pytest tests/test_answer.py -v
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
import answer

FAKE_PASSAGES = [
    {"meta": {"parva_name": "UDYOGA PARVA", "section": 141, "passage_index": 5}, "text": "passage one text"},
    {"meta": {"parva_name": "BHISHMA PARVA", "section": 59, "passage_index": 7}, "text": "passage two text"},
    {"meta": {"parva_name": "VANA PARVA", "section": 83, "passage_index": 19}, "text": "passage three text"},
]


def test_build_citations_valid_ids():
    citations = answer.build_citations([1, 3], FAKE_PASSAGES)
    assert len(citations) == 2
    assert citations[0]["parva_name"] == "UDYOGA PARVA"
    assert citations[0]["excerpt"] == "passage one text"
    assert citations[1]["parva_name"] == "VANA PARVA"


def test_build_citations_drops_out_of_range_id():
    # Model hallucinated a passage number that doesn't exist (only 3 given)
    citations = answer.build_citations([1, 99], FAKE_PASSAGES)
    assert len(citations) == 1
    assert citations[0]["parva_name"] == "UDYOGA PARVA"


def test_build_citations_drops_zero_and_negative():
    citations = answer.build_citations([0, -1, 2], FAKE_PASSAGES)
    assert len(citations) == 1
    assert citations[0]["parva_name"] == "BHISHMA PARVA"


def test_build_citations_drops_non_numeric():
    citations = answer.build_citations(["one", None, 2], FAKE_PASSAGES)
    assert len(citations) == 1


def test_build_citations_accepts_passage_label_format():
    # Found via a live Gemini eval run: the prompt asks for bare
    # integers ("e.g. 1, 3") but Gemini sometimes echoes the context
    # block's own [P1]/[P2] labels back instead - int("P1") used to
    # raise and silently drop an otherwise well-cited real answer.
    citations = answer.build_citations(["P1", "p3"], FAKE_PASSAGES)
    assert len(citations) == 2
    assert citations[0]["parva_name"] == "UDYOGA PARVA"
    assert citations[1]["parva_name"] == "VANA PARVA"


def test_build_citations_still_drops_out_of_range_label_format():
    citations = answer.build_citations(["P99"], FAKE_PASSAGES)
    assert citations == []


def test_build_citations_mixed_int_and_label_formats_dedupe_together():
    # "P1" and 1 refer to the same passage - must not double-count.
    citations = answer.build_citations([1, "P1"], FAKE_PASSAGES)
    assert len(citations) == 1


def test_build_citations_dedupes():
    citations = answer.build_citations([1, 1, 1], FAKE_PASSAGES)
    assert len(citations) == 1


def test_build_citations_empty_list():
    assert answer.build_citations([], FAKE_PASSAGES) == []
    assert answer.build_citations(None, FAKE_PASSAGES) == []


# UX item 8: a citation whose excerpt is a real passage's opening
# sentence but not the sentence that actually supports the model's
# claim - confirmed live via "Why did Krishna choose to be Arjuna's
# charioteer?" (UDYOGA PARVA Section 7's third chunk opens with
# Duryodhana embracing Balarama, "that hero wielding a plough", and
# only several sentences later gets to Krishna agreeing to be Arjuna's
# charioteer - the actual answer). Modeled here with a short synthetic
# passage so the test doesn't depend on the real corpus.
_CHARIOTEER_PASSAGE = [{
    "meta": {"parva_name": "UDYOGA PARVA", "section": 7, "passage_index": 2},
    "text": (
        "Duryodhana embraced that hero wielding a plough for his weapon of "
        "battle, well pleased with the army he had secured. Arjuna then said "
        "it had always been his desire to have Krishna for driving his car. "
        "Krishna agreed, saying he would act as Arjuna's charioteer."
    ),
}]


def test_build_citations_without_reference_returns_full_passage():
    # Default behavior, unchanged for every caller that doesn't pass a
    # reference (test_citation_check.py's verbatim-excerpt guarantee
    # relies on this staying exactly the full passage text).
    citations = answer.build_citations([1], _CHARIOTEER_PASSAGE)
    assert citations[0]["excerpt"] == _CHARIOTEER_PASSAGE[0]["text"]


def test_build_citations_with_reference_favors_the_supporting_sentence():
    reference = "Krishna agreed to act as Arjuna's charioteer because Arjuna asked him to."
    citations = answer.build_citations([1], _CHARIOTEER_PASSAGE, reference)
    excerpt = citations[0]["excerpt"]
    assert "charioteer" in excerpt
    assert "plough" not in excerpt


def test_select_excerpt_result_is_always_a_genuine_substring():
    text = _CHARIOTEER_PASSAGE[0]["text"]
    reference = "Krishna agreed to act as Arjuna's charioteer."
    excerpt = answer._select_excerpt(text, reference, max_chars=80)
    stripped = excerpt.removeprefix("... ").removesuffix(" ...")
    assert stripped in text


def test_select_excerpt_falls_back_to_head_truncation_with_no_overlap():
    text = "A" * 300
    assert answer._select_excerpt(text, "completely unrelated words here") == ("A" * 220 + "...")


def test_select_excerpt_returns_short_text_unchanged():
    assert answer._select_excerpt("short text", "any reference") == "short text"


def test_write_answer_factual():
    mock_response = '{"answer": "Bhishma never married.", "used_ids": [1]}'
    with patch("llm_client.complete", return_value=mock_response):
        result = answer.write_answer("openai", "fake-key", "Did Bhishma marry?", "factual", FAKE_PASSAGES)
        assert result["answer"] == "Bhishma never married."
        assert result["used_ids"] == [1]


def test_write_answer_ambiguous():
    mock_response = ('{"factual_sentence": "The war happened.", "factual_ids": [1], '
                      '"philosophical_sentence": "It raises questions of duty.", "philosophical_ids": [2]}')
    with patch("llm_client.complete", return_value=mock_response):
        result = answer.write_answer("openai", "fake-key", "Was the war necessary?", "ambiguous", FAKE_PASSAGES)
        assert result["factual_sentence"] == "The war happened."
        assert result["philosophical_ids"] == [2]


def test_write_answer_malformed_response_returns_empty_dict():
    with patch("llm_client.complete", return_value="I cannot help with that, sorry"):
        result = answer.write_answer("openai", "fake-key", "some question", "factual", FAKE_PASSAGES)
        assert result == {}


def test_write_answer_invalid_label_raises():
    try:
        answer.write_answer("openai", "fake-key", "q", "not_a_label", FAKE_PASSAGES)
        assert False, "should have raised"
    except ValueError:
        pass


def test_suggest_related_topics():
    suggestions = answer.suggest_related_topics(FAKE_PASSAGES)
    assert len(suggestions) == 3
    assert "Udyoga Parva" in suggestions


def test_suggest_related_topics_respects_limit_and_dedupes():
    passages = FAKE_PASSAGES + [FAKE_PASSAGES[0]]  # duplicate parva
    suggestions = answer.suggest_related_topics(passages, limit=2)
    assert len(suggestions) == 2


if __name__ == "__main__":
    test_build_citations_valid_ids()
    test_build_citations_drops_out_of_range_id()
    test_build_citations_drops_zero_and_negative()
    test_build_citations_drops_non_numeric()
    test_build_citations_dedupes()
    test_build_citations_empty_list()
    test_write_answer_factual()
    test_write_answer_ambiguous()
    test_write_answer_malformed_response_returns_empty_dict()
    test_write_answer_invalid_label_raises()
    test_suggest_related_topics()
    test_suggest_related_topics_respects_limit_and_dedupes()
    print("All answer tests passed.")
