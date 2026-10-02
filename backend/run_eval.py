"""
Task 19: eval runner.

Runs every query in docs/qna-eval-set through the REAL pipeline (the
same modules qna_endpoint.py wires together: guardrails -> scope ->
hybrid search -> classify -> answer -> citations), compares the outcome
against each row's expected label, and prints a confusion table.

This needs a real BYOK API key to call the classifier/answer models, so
- like test_classifier_live.py before it - it's a script for YOU to run
locally with your own .env credentials, not something run from the
agent sandbox. It reuses that same key for both the "visitor" calls
(classify/answer) and, as already set up in .env, for our own
server-side embeddings key - see .env.example.

Usage (from backend/):
    python run_eval.py                        # openai, OPENAI_API_KEY, normal search
    python run_eval.py --provider anthropic    # uses ANTHROPIC_API_KEY
    python run_eval.py --model gpt-4o          # override the default model
    python run_eval.py --degrade               # force the embeddings call to fail,
                                                # confirming the keyword-only fallback
                                                # (design.md Property 8) end to end
    python run_eval.py --rows 17,21,22,35      # just the verdict-seeking spot-check rows
    python run_eval.py --limit 5               # first N rows only, for a quick smoke run

Row-parsing (load_eval_rows, GUARDRAIL_ROWS, FOLLOWUP_ROWS) is reused
from tests/test_scope.py rather than reimplemented here, so both stay
in sync with the same eval-set file.
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "tests"))

try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / ".env")
except ImportError:
    pass

import answer
import classifier
import guardrails
import llm_client
import query_rewrite
import scope
import search
from test_scope import load_eval_rows, GUARDRAIL_ROWS, FOLLOWUP_ROWS  # noqa: E402

# Rows the eval set itself flags as "verdict-seeking" (docs/qna-eval-set
# "What it tests" column) - design.md's Testing Strategy calls for a
# manual spot-check that no verdict leaked into the answer text (Q&A
# Requirement 10.3), which a label match alone can't catch.
VERDICT_CHECK_ROWS = {17, 21, 22, 35}

LABEL_MAP = {"Factual": "factual", "Philosophical": "philosophical", "Ambiguous": "ambiguous"}


class _FailingEmbeddings:
    """Stand-in for openai_client used with --degrade: raises on every
    embed call so hybrid_search's own try/except takes the keyword-only
    fallback path (search.py's real degraded-mode behavior), without
    needing a broken key or a network trick to force the failure."""

    class _Embeddings:
        def create(self, *a, **kw):
            raise RuntimeError("--degrade: embeddings call forced to fail")

    def __init__(self):
        self.embeddings = self._Embeddings()


def build_resources(degrade: bool) -> dict:
    import openai
    from supabase import create_client

    print("Loading BM25 keyword index...")
    bm25_index = search.load_bm25_index()

    print("Connecting to Supabase and OpenAI (our own embeddings key)...")
    openai_client = (
        _FailingEmbeddings() if degrade
        else openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    )
    supabase_client = create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    )
    return {"bm25_index": bm25_index, "openai_client": openai_client, "supabase_client": supabase_client}


def run_one(question: str, has_context: bool, provider: str, api_key: str, model: str | None,
            resources: dict) -> dict:
    """Runs the same sequence qna_endpoint.handle_ask does for the
    non-expand path, and returns enough detail for both the confusion
    table and the verdict spot-check."""
    guardrails_ok, guardrails_message = guardrails.check_guardrails(question)
    if not guardrails_ok:
        return {"actual": "decline", "reason": "guardrails", "message": guardrails_message}

    in_scope, decline_message = scope.check_scope(question, has_context=has_context)
    if not in_scope:
        return {"actual": "decline", "reason": "scope", "message": decline_message}

    passages, degraded = search.hybrid_search(
        query=question,
        bm25_index=resources["bm25_index"],
        openai_client=resources["openai_client"],
        supabase_client=resources["supabase_client"],
    )

    try:
        classification = classifier.classify_question(provider, api_key, question, model)
    except llm_client.LLMError as e:
        return {"actual": "provider_error", "reason": f"classify:{e.kind}", "message": str(e), "degraded": degraded}
    label = classification["label"]

    try:
        raw = answer.write_answer(provider, api_key, question, label, passages, model)
    except llm_client.LLMError as e:
        return {"actual": "provider_error", "reason": f"answer:{e.kind}", "message": str(e), "degraded": degraded}

    if label == "ambiguous":
        citations = answer.build_citations(raw.get("factual_ids"), passages) + \
            answer.build_citations(raw.get("philosophical_ids"), passages)
        text = f"F: {raw.get('factual_sentence', '')} | P: {raw.get('philosophical_sentence', '')}"
    else:
        citations = answer.build_citations(raw.get("used_ids"), passages)
        text = raw.get("answer", "")

    if not citations:
        # Query-rewrite retry (docs/decision-log.md): before giving up,
        # ask the visitor's own model for retrieval keywords in the
        # source's own period vocabulary and search again once. Mirrors
        # qna_endpoint.py's _retry_with_rewritten_query so this eval
        # measures the SAME behavior production actually has.
        rewritten = query_rewrite.rewrite_query(provider, api_key, question, model)
        if rewritten:
            retry_passages, retry_degraded = search.hybrid_search(
                query=rewritten,
                bm25_index=resources["bm25_index"],
                openai_client=resources["openai_client"],
                supabase_client=resources["supabase_client"],
            )
            try:
                retry_raw = answer.write_answer(provider, api_key, question, label, retry_passages, model)
            except llm_client.LLMError:
                retry_raw = {}
            if label == "ambiguous":
                retry_citations = answer.build_citations(retry_raw.get("factual_ids"), retry_passages) + \
                    answer.build_citations(retry_raw.get("philosophical_ids"), retry_passages)
                retry_text = (f"F: {retry_raw.get('factual_sentence', '')} | "
                              f"P: {retry_raw.get('philosophical_sentence', '')}")
            else:
                retry_citations = answer.build_citations(retry_raw.get("used_ids"), retry_passages)
                retry_text = retry_raw.get("answer", "")
            if retry_citations:
                return {"actual": label, "message": retry_text, "degraded": retry_degraded,
                        "confidence": classification["confidence"], "query_rewritten": True,
                        "rewritten_query": rewritten}
        # Diagnostic detail for a no_answer outcome: was retrieval itself
        # empty/thin (num_passages), or did search find passages but the
        # model's used_ids came back empty/invalid (raw_model_output)?
        # Those are two different problems to chase - the confusion table
        # alone can't tell them apart. rewritten_query is None when the
        # rewrite call itself failed/came back empty, vs. a string when
        # it ran but still didn't find a usable passage - also worth
        # telling apart by eye.
        return {"actual": "no_answer", "reason": "no_citations", "message": text, "degraded": degraded,
                "confidence": classification["confidence"], "num_passages": len(passages), "raw_model_output": raw,
                "rewritten_query": rewritten}

    return {"actual": label, "message": text, "degraded": degraded, "confidence": classification["confidence"],
            "query_rewritten": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", default="openai", choices=["openai", "anthropic", "gemini"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key", default=None, help="Defaults to <PROVIDER>_API_KEY from .env")
    parser.add_argument("--degrade", action="store_true",
                         help="Force the embeddings call to fail, to confirm the keyword-only fallback")
    parser.add_argument("--rows", default=None, help="Comma-separated row numbers to run, e.g. 17,21,22")
    parser.add_argument("--limit", type=int, default=None, help="Only run the first N rows")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get(f"{args.provider.upper()}_API_KEY")
    if not api_key:
        sys.exit(f"No API key found. Set {args.provider.upper()}_API_KEY in backend/.env or pass --api-key.")

    rows = load_eval_rows()
    if args.rows:
        wanted = {int(r) for r in args.rows.split(",")}
        rows = [r for r in rows if r[0] in wanted]
    if args.limit:
        rows = rows[: args.limit]

    resources = build_resources(args.degrade)

    confusion = defaultdict(lambda: defaultdict(int))
    mismatches = []
    verdict_spotchecks = []

    print(f"\nRunning {len(rows)} eval-set rows against {args.provider}"
          f"{' (--degrade: keyword-only search forced)' if args.degrade else ''}...\n")

    for row_num, query, expected in rows:
        if row_num in FOLLOWUP_ROWS:
            # Follow-up rows are graded on whether context correctly
            # changes decline vs answered, not on which specific label
            # the answer gets (docs/qna-eval-set's own definition).
            without = run_one(query, False, args.provider, api_key, args.model, resources)
            with_ctx = run_one(query, True, args.provider, api_key, args.model, resources)
            ok = without["actual"] == "decline" and with_ctx["actual"] != "decline"
            confusion["Follow-up"]["ok" if ok else "mismatch"] += 1
            print(f"#{row_num:2} [Follow-up] {query!r}\n"
                  f"       no context -> {without['actual']}   with context -> {with_ctx['actual']}"
                  f"{'  OK' if ok else '  MISMATCH'}")
            if not ok:
                mismatches.append((row_num, query, expected, f"no_ctx={without['actual']} with_ctx={with_ctx['actual']}"))
            continue

        has_context = False  # every other row is a standalone query in the eval set
        result = run_one(query, has_context, args.provider, api_key, args.model, resources)
        actual = result["actual"]

        if row_num in GUARDRAIL_ROWS:
            # Expected label is "Decline" via Task 9's guardrails, not
            # the scope check - same distinction test_scope.py draws.
            expected_norm = "decline"
        else:
            expected_norm = LABEL_MAP.get(expected, expected.lower())

        match = actual == expected_norm
        confusion[expected][actual] += 1
        degraded_note = "  [degraded]" if result.get("degraded") else ""
        rewrite_note = "  [fixed by query rewrite]" if result.get("query_rewritten") else ""
        print(f"#{row_num:2} [{expected:13}] {query!r}\n"
              f"       -> {actual}{degraded_note}{rewrite_note}{'  OK' if match else '  MISMATCH'}")

        if not match:
            mismatches.append((row_num, query, expected, actual))
            if actual == "no_answer":
                # Tells apart two different problems that both look like
                # "no_answer" in the confusion table: retrieval finding
                # nothing worth citing (num_passages low/0) vs. retrieval
                # finding passages but the model's used_ids coming back
                # empty or invalid (raw_model_output shows what it said).
                # rewritten_query shows what the retry tried (None if the
                # rewrite call itself failed/came back empty) - so a
                # still-failing row is visibly "retry attempted, still no
                # recall" vs. "retry never even ran."
                print(f"       [diagnostic] {result.get('num_passages', 0)} passages retrieved; "
                      f"model output: {result.get('raw_model_output')!r}; "
                      f"rewrite tried: {result.get('rewritten_query')!r}")
            elif "confidence" in result:
                # A wrong-label mismatch (e.g. classifier said "factual"
                # where the eval set expects "ambiguous") - print the
                # classifier's own confidence and the answer text it
                # produced, so you can judge by eye whether "actual" is a
                # defensible reading (same question decision-log.md
                # already made for eval-set rows 17/21/22/35) or a real
                # classifier miss, without needing a second run.
                print(f"       [diagnostic] classifier confidence {result['confidence']:.2f}; "
                      f"answer: {result.get('message', '')!r}")

        if row_num in VERDICT_CHECK_ROWS and actual not in ("decline", "no_answer", "provider_error"):
            verdict_spotchecks.append((row_num, query, result.get("message", "")))

    print("\n" + "=" * 70)
    print("CONFUSION TABLE (expected -> actual : count)")
    print("=" * 70)
    for expected_label, actuals in confusion.items():
        for actual_label, count in actuals.items():
            print(f"  {expected_label:13} -> {actual_label:15} : {count}")

    print("\n" + "=" * 70)
    print(f"MISMATCHES ({len(mismatches)})")
    print("=" * 70)
    for row_num, query, expected, actual in mismatches:
        print(f"  #{row_num}: expected {expected!r}, got {actual!r}  ({query!r})")
    if not mismatches:
        print("  none")

    print("\n" + "=" * 70)
    print(f"VERDICT SPOT-CHECK ({len(verdict_spotchecks)} rows - read these by eye for "
          f"leaked verdict language, Q&A Requirement 10.3)")
    print("=" * 70)
    for row_num, query, text in verdict_spotchecks:
        print(f"  #{row_num} {query!r}\n      {text}\n")


if __name__ == "__main__":
    main()
