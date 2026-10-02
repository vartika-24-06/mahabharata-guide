"""
Q&A exchange logging - every question handle_ask answers (or declines)
gets a row in Supabase's `qna_logs` table, for Vartika to review later
(volume, which questions get declined/no_answer, how labels split,
whether the query-rewrite retry is actually helping). Same spirit and
same best-effort approach as feedback_endpoint.py: a Supabase hiccup
here should never surface as a broken app to a visitor who just asked a
question, so a failed insert is logged server-side and otherwise
swallowed, never raised.

Deliberately separate from feedback (which only gets a row when a
visitor clicks a thumb): this logs every exchange whether or not
anyone rates it, so the two tables answer different questions -
feedback.md is thumbs-based, qna_logs is simply ask traffic.
"""
VALID_TYPES = {"decline", "no_answer", "factual", "philosophical", "ambiguous"}


def build_row(
    question: str,
    payload: dict,
    provider: str | None,
    model: str | None,
) -> dict:
    """Normalizes any of handle_ask's JSON response shapes (decline,
    no_answer, factual/philosophical, or ambiguous's two-sentence shape)
    into one flat row. answer_text/citations are derived per shape since
    only factual/philosophical have a single "answer"/"citations" pair -
    ambiguous carries two of each, decline/no_answer carry neither."""
    ptype = payload.get("type")

    if ptype == "ambiguous":
        answer_text = " ".join(
            s for s in (payload.get("factual_sentence"), payload.get("philosophical_sentence")) if s
        )
        citations = (payload.get("factual_citations") or []) + (payload.get("philosophical_citations") or [])
    elif ptype in ("decline", "no_answer"):
        answer_text = payload.get("message", "")
        citations = []
    else:
        answer_text = payload.get("answer", "")
        citations = payload.get("citations") or []

    return {
        "question": question,
        "type": ptype,
        "expanded": bool(payload.get("expanded", False)),
        "answer_text": answer_text,
        "citations": citations,
        "provider": provider,
        "model": model,
        "meaning_search_degraded": payload.get("meaning_search_degraded"),
        "query_rewritten": payload.get("query_rewritten"),
        "classifier_confidence": payload.get("classifier_confidence"),
    }


def log_exchange(resources: dict, row: dict) -> None:
    """Best-effort insert - never raises. Silently skipped (not an
    error) when there's no Supabase client at all, which is how the
    existing test suite exercises handle_ask (resources["supabase_client"]
    is set to None so tests don't need a real connection)."""
    supabase_client = resources.get("supabase_client")
    if supabase_client is None:
        return
    try:
        supabase_client.table("qna_logs").insert(row).execute()
    except Exception as exc:
        print(f"qna_log.log_exchange: failed to store exchange ({exc.__class__.__name__}): {exc}")
