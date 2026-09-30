"""
Task 11 test: classifier logic (confidence threshold, malformed-response
fallback) with a mocked LLM call - no real API key or network needed.
Testing actual classification ACCURACY against the eval set needs a
real key and is a separate, human-judgment step (see classifier.py's
docstring on CONFIDENCE_THRESHOLD).

Run with: python -m pytest tests/test_classifier.py -v
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
import classifier


def _mock_complete(response_text):
    return patch("llm_client.complete", return_value=response_text)


def test_high_confidence_factual_passes_through():
    with _mock_complete('{"label": "factual", "confidence": 0.95}'):
        result = classifier.classify_question("openai", "fake-key", "Who was Karna's mother?")
        assert result["label"] == "factual"
        assert result["confidence"] == 0.95


def test_low_confidence_downgrades_to_ambiguous():
    with _mock_complete('{"label": "factual", "confidence": 0.3}'):
        result = classifier.classify_question("openai", "fake-key", "some tricky question")
        assert result["label"] == "ambiguous"
        assert result["raw_label"] == "factual"


def test_confidence_exactly_at_threshold_passes():
    with _mock_complete(f'{{"label": "philosophical", "confidence": {classifier.CONFIDENCE_THRESHOLD}}}'):
        result = classifier.classify_question("openai", "fake-key", "some question")
        assert result["label"] == "philosophical"


def test_malformed_json_falls_back_to_ambiguous():
    with _mock_complete('I think this question is about facts, sorry no JSON here'):
        result = classifier.classify_question("openai", "fake-key", "some question")
        assert result["label"] == "ambiguous"
        assert result["confidence"] == 0.0


def test_json_with_code_fence_parses_correctly():
    with _mock_complete('```json\n{"label": "ambiguous", "confidence": 0.9}\n```'):
        result = classifier.classify_question("openai", "fake-key", "some question")
        assert result["label"] == "ambiguous"
        assert result["confidence"] == 0.9


def test_invalid_label_falls_back_to_ambiguous():
    with _mock_complete('{"label": "not_a_real_label", "confidence": 0.9}'):
        result = classifier.classify_question("openai", "fake-key", "some question")
        assert result["label"] == "ambiguous"


if __name__ == "__main__":
    test_high_confidence_factual_passes_through()
    test_low_confidence_downgrades_to_ambiguous()
    test_confidence_exactly_at_threshold_passes()
    test_malformed_json_falls_back_to_ambiguous()
    test_json_with_code_fence_parses_correctly()
    test_invalid_label_falls_back_to_ambiguous()
    print("All classifier tests passed.")
