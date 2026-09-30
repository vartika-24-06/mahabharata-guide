"""
Task 20: citation check.

An automatic test that every citation answer.build_citations() produces
names a REAL parva and section from the actual corpus, and carries a
VERBATIM excerpt - not a hand-typed fake passage standing in for one.
tests/test_answer.py already unit-tests build_citations()'s id-validation
logic (drops out-of-range/negative/non-numeric/duplicate ids) against a
small FAKE_PASSAGES fixture - that proves the function's logic is right,
but not that real search results flowing through it actually produce
citations that are traceable back to the real text. This file closes
that gap by running real BM25 search against the real corpus
(data_processed/) and checking build_citations()'s output against
data_processed/passages.jsonl as ground truth - no API key or Supabase
needed, since BM25 and the local passages file are both self-hosted.

Run with: python -m pytest tests/test_citation_check.py -v
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import answer
import search

DATA_DIR = Path(__file__).parent.parent.parent / "data_processed"
PASSAGES_PATH = DATA_DIR / "passages.jsonl"

# A spread of real eval-set-style queries, not just one, so the check
# isn't accidentally passing on a single lucky retrieval.
SAMPLE_QUERIES = [
    "Did Bhishma get married?",
    "Who killed Drona?",
    "What does the Mahabharata say about duty?",
    "Why did Karna suffer so much?",
    "What happened in the dice game?",
    "Who was Arjun's charioteer?",
]


def load_ground_truth() -> dict[tuple, dict]:
    """Keys every real passage by (parva_file, section, passage_index) -
    the same key search._passage_key() uses - so a citation can be traced
    back to the exact real row it claims to come from."""
    ground_truth = {}
    with open(PASSAGES_PATH, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            key = (row["parva_file"], row["section"], row["passage_index"])
            ground_truth[key] = row
    return ground_truth


GROUND_TRUTH = load_ground_truth()
REAL_PARVA_NAMES = {row["parva_name"] for row in GROUND_TRUTH.values()}
BM25_INDEX = search.load_bm25_index()


def _passages_for_query(query: str, k: int = 12) -> list[dict]:
    """Builds a real `passages` list the same shape hybrid_search()
    hands to build_citations() - meta from real BM25 search, text filled
    in from the real corpus file directly (standing in for the Supabase
    lookup fill_missing_text() would otherwise do, so this test needs no
    live credentials)."""
    bm25_results = search.bm25_search(BM25_INDEX, query, k=k)
    passages = []
    for r in bm25_results:
        meta = r["meta"]
        key = (meta["parva_file"], meta["section"], meta["passage_index"])
        passages.append({"meta": meta, "text": GROUND_TRUTH[key]["text"]})
    return passages


def test_ground_truth_loaded():
    assert len(GROUND_TRUTH) >= 8000
    assert len(REAL_PARVA_NAMES) == 18


def test_citations_name_a_real_parva_and_section_with_verbatim_excerpt():
    failures = []

    for query in SAMPLE_QUERIES:
        passages = _passages_for_query(query)
        assert passages, f"query {query!r} retrieved nothing - can't test citations against it"

        # Simulate the model reporting every passage it was given, plus
        # a couple of invalid ids it might hallucinate (0, out of range,
        # a duplicate) - build_citations() should drop those silently
        # and only produce real citations for the valid ones.
        used_ids = list(range(1, len(passages) + 1)) + [0, len(passages) + 50, 1]
        citations = answer.build_citations(used_ids, passages)

        assert len(citations) == len(passages), (
            f"query {query!r}: expected {len(passages)} citations (one per "
            f"retrieved passage, deduped), got {len(citations)}"
        )

        for c in citations:
            if c["parva_name"] not in REAL_PARVA_NAMES:
                failures.append(f"{query!r}: {c['parva_name']!r} is not one of the 18 real parvas")
                continue

            # Section must be a real section within that parva - not just
            # any integer.
            real_sections_in_parva = {
                key[1] for key, row in GROUND_TRUTH.items() if row["parva_name"] == c["parva_name"]
            }
            if c["section"] not in real_sections_in_parva:
                failures.append(
                    f"{query!r}: {c['parva_name']} section {c['section']} "
                    f"does not exist in the real corpus"
                )
                continue

            # The excerpt must be the REAL text for that exact passage,
            # character for character - never paraphrased, truncated, or
            # substituted from a different passage.
            matching_rows = [
                row for key, row in GROUND_TRUTH.items()
                if row["parva_name"] == c["parva_name"] and key[1] == c["section"]
            ]
            if not any(row["text"] == c["excerpt"] for row in matching_rows):
                failures.append(
                    f"{query!r}: excerpt for {c['parva_name']} section {c['section']} "
                    f"does not verbatim-match any real passage text"
                )

    assert not failures, "Citation check failures:\n" + "\n".join(failures)


def test_citations_never_include_ids_outside_the_retrieved_set():
    """A stress case: a model reporting ids only from a tiny slice of
    what was retrieved, plus garbage ids in every shape build_citations()
    is documented to drop (Task 12) - id 0, negative, way out of range,
    a non-numeric string, and None. None of that garbage should ever
    surface as a citation, even against real passages."""
    passages = _passages_for_query(SAMPLE_QUERIES[0])
    used_ids = [1, 0, -5, len(passages) + 999, "not-a-number", None]
    citations = answer.build_citations(used_ids, passages)

    assert len(citations) == 1
    assert citations[0]["parva_name"] in REAL_PARVA_NAMES


def test_citations_are_stable_across_repeated_runs():
    """Same query, same used_ids -> same citations, byte for byte - a
    basic determinism check (no hidden randomness in build_citations()
    itself; BM25 scoring for a fixed query and index is also
    deterministic)."""
    query = random.choice(SAMPLE_QUERIES)
    passages_a = _passages_for_query(query)
    passages_b = _passages_for_query(query)
    used_ids = list(range(1, len(passages_a) + 1))

    citations_a = answer.build_citations(used_ids, passages_a)
    citations_b = answer.build_citations(used_ids, passages_b)
    assert citations_a == citations_b
