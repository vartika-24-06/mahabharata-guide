"""
Task 8 test: runs the scope check against every row in the real eval set
(docs/qna-eval-set), not a hand-picked subset - design.md's Testing
Strategy calls for running every eval-set query and checking expected
against actual.

Three rows (32, 33, 34) are deliberately excluded from the "must decline"
assertion here: they mention curated terms (Krishna, Mahabharata) so the
scope check alone correctly lets them through. What makes them declines
is prompt-reveal/persona/rule-override detection, which is Task 9's job,
not this one - testing them here would be testing the wrong layer.

Run with: python -m pytest tests/test_scope.py -v
(or: python -m pytest backend/tests/test_scope.py -v from the repo root)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import scope

EVAL_SET_PATH = Path(__file__).parent.parent.parent / "docs" / "qna-eval-set"

# Rows where the "Decline" label comes from Task 9's guardrails
# (prompt-reveal, persona, rule-override), not the scope check itself -
# the query mentions curated terms and correctly passes scope.
GUARDRAIL_ROWS = {32, 33, 34}

# Rows labeled Follow-up only pass scope with has_context=True; without
# context they're expected to decline like any other out-of-scope query
# (this is exactly the row 24/25 distinction design.md calls out).
FOLLOWUP_ROWS = {23, 25}


def load_eval_rows():
    """A couple of rows (23, 24) append a scenario annotation in
    parens - e.g. "(after an answer about Karna)" - describing the
    conversational setup, not text the user actually typed. Stripped
    here so the scope check sees the literal query, same as it would at
    request time; leaving it in would let row 23 pass on "Karna" alone,
    which isn't what the row is testing."""
    rows = []
    text = EVAL_SET_PATH.read_text(encoding="utf-8")
    for line in text.splitlines():
        m = re.match(r'\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*([\w-]+)\s*\|', line)
        if m:
            row_num, query, label = int(m.group(1)), m.group(2), m.group(3)
            query = re.sub(r'\s*\([^)]*\)\s*$', '', query).strip()
            rows.append((row_num, query, label))
    return rows


def test_eval_set_loads():
    rows = load_eval_rows()
    assert len(rows) >= 35, f"Expected at least 35 eval rows, found {len(rows)}"


def test_scope_check_against_eval_set():
    rows = load_eval_rows()
    failures = []

    for row_num, query, label in rows:
        if row_num in GUARDRAIL_ROWS:
            continue  # Task 9's job, not scope check's - see module docstring

        if row_num in FOLLOWUP_ROWS:
            # Must decline standalone, must pass with context
            in_scope_alone, _ = scope.check_scope(query, has_context=False)
            in_scope_with_ctx, _ = scope.check_scope(query, has_context=True)
            if in_scope_alone:
                failures.append(f"Row {row_num} ({query!r}): expected to decline "
                                 f"without context, but passed scope check")
            if not in_scope_with_ctx:
                failures.append(f"Row {row_num} ({query!r}): expected to pass as "
                                 f"a follow-up with context, but was declined")
            continue

        expected_in_scope = label != "Decline"
        in_scope, _ = scope.check_scope(query, has_context=False)
        if in_scope != expected_in_scope:
            failures.append(f"Row {row_num} ({query!r}): label={label}, "
                             f"expected in_scope={expected_in_scope}, got {in_scope}")

    assert not failures, "Scope check mismatches:\n" + "\n".join(failures)


if __name__ == "__main__":
    test_eval_set_loads()
    test_scope_check_against_eval_set()
    print("All scope check tests passed against the real eval set.")
