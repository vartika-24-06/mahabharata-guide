"""
Query rewriting for the retrieval retry path (docs/decision-log.md:
raising search.hybrid_search's k from 12 to 20 helped one recall gap but
not others - "Did Bhishma get married?" and "Did Draupadi have any
siblings?" still miss).

Those misses share one shape: a modern phrasing of a well-known fact
("married", "siblings") shares no vocabulary with the source's own
19th-century translation ("vow of celibacy", "twins of the great
sacrifice"). BM25 can't bridge that gap by keyword score alone, however
wide k gets - it needs different words to search with.

The visitor's own LLM already knows the Mahabharata from training - it
doesn't need our corpus to know these are well-known facts, just to
suggest period-appropriate search terms. This call is used ONLY to
generate retrieval keywords for a retry search - it is never shown to
the visitor and never treated as the answer itself. The actual answer
still comes from answer.write_answer()/build_citations() against really
retrieved passages, same no-hallucination contract as everywhere else in
this app (answer.py's module docstring). If this call fails or returns
nothing usable, the caller should fall through to the original
no_answer result (fail open) rather than crash - see rewrite_query's
None return.
"""
import llm_client

SYSTEM_PROMPT = """You help find search terms for questions about the Mahabharata epic, which will be run as a keyword search against a formal, 19th-century English prose translation (archaic, literal, third person - in the style of Kisari Mohan Ganguli's translation).

Given a question, use what you already know about this story to suggest 5-8 keywords or short phrases likely to appear in that kind of translation when describing the real answer - character names, classical synonyms for modern words (for example "siblings" -> "brothers and sisters", "married" -> "wife" / "espoused" / "marriage", "killed" -> "slew" / "slain"), and specific events or parva names if relevant.

Respond with ONLY the keywords/phrases, space-separated, no other text, no explanation, no code fence."""


def rewrite_query(
    provider: str,
    api_key: str,
    question: str,
    model: str | None = None,
) -> str | None:
    """Returns a keyword string to retry search.hybrid_search with, or
    None if the call failed or came back empty. Callers should treat
    None as "couldn't rewrite, keep the original no_answer" rather than
    raising or retrying again - this is a best-effort second attempt,
    not a required step."""
    try:
        text = llm_client.complete_safe(
            provider=provider,
            api_key=api_key,
            system=SYSTEM_PROMPT,
            user=question,
            model=model,
            max_tokens=100,
        )
    except llm_client.LLMError as exc:
        # Printed rather than silently swallowed - a caller only sees
        # "rewrite tried: None" either way, and auth/rate_limit/timeout
        # vs. "the model just returned nothing" are different problems
        # worth telling apart when debugging a still-failing eval row.
        print(f"query_rewrite.rewrite_query failed ({exc.kind}): {exc}")
        return None

    text = text.strip()
    if not text:
        print("query_rewrite.rewrite_query: model returned an empty response.")
    return text or None
