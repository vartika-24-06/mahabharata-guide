"""
Task 13: the real Q&A endpoint (POST /api/ask), replacing /debug/search.

Wires together every piece built in Tasks 7-12, in the order design.md
and the qna-mode requirements imply:

  visitor rate limit (Task 10)
    -> guardrails (Task 9)
    -> scope check, with has_context from the browser's Session Context (Task 8)
    -> hybrid search (Task 7)
    -> classify the question with the VISITOR's own key (Task 11)
    -> write the answer with the VISITOR's own key (Task 12)
    -> build citations from OUR retrieved passages, never the model's text (Task 12)
    -> "text doesn't cover it" fallback when citations end up empty (qna-mode Req 9.3)

Header/error contract reuses the entry-screen spec's shape for a "real
request" (mahabharata-entry-screen/design.md, POST /api/complete /
Requirement R21, R22) even though the entry screen itself isn't built
yet in this repo: X-Provider-Key carries the visitor's raw key, and a
provider failure comes back as HTTP 400 {"error": <kind>, "message":
...} with kind one of auth/unknown_model/rate_limit/other - so whenever
the entry screen's key modal and throttle middleware do land, this
endpoint's error shape needs no change (qna-mode Requirement 11.3/11.4
point back at that exact handling).

Our OWN visitor request-rate limit (Task 10) is a different thing from
a provider rate-limiting the visitor's key, so it gets a different
status/shape (429 {"error": "throttled", ...}) rather than colliding
with the provider "rate_limit" kind at 400.

The visitor's key is read from a header and passed straight into
llm_client for the duration of this one request - never logged, never
stored (matches llm_client.py's and design.md's handling). FastAPI/
uvicorn's default access log records method+path, not headers, so no
extra redaction layer is added here; a full HeaderRedactionMiddleware
is the entry-screen spec's job when that gets built.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import answer
import classifier
import guardrails
import llm_client
import query_rewrite
import rate_limit
import scope
import search


class Exchange(BaseModel):
    question: str
    type: str | None = None


class AskRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    question: str
    expand: bool = False
    label: str | None = None  # only meaningful when expand=True
    context: list[Exchange] | None = None


def _error(status: int, kind: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": kind, "message": message})


def _citation_lists(label: str, raw: dict, passages: list[dict]):
    """Returns (has_any_citation, response_fields) for the short-answer
    shapes. Kept separate from the expand path since ambiguous has two
    citation lists and factual/philosophical have one."""
    if label == "ambiguous":
        factual_citations = answer.build_citations(
            raw.get("factual_ids"), passages, raw.get("factual_sentence", "")
        )
        philosophical_citations = answer.build_citations(
            raw.get("philosophical_ids"), passages, raw.get("philosophical_sentence", "")
        )
        has_any = bool(factual_citations or philosophical_citations)
        fields = {
            "type": "ambiguous",
            "factual_sentence": raw.get("factual_sentence", ""),
            "factual_citations": factual_citations,
            "philosophical_sentence": raw.get("philosophical_sentence", ""),
            "philosophical_citations": philosophical_citations,
        }
        return has_any, fields

    citations = answer.build_citations(raw.get("used_ids"), passages, raw.get("answer", ""))
    fields = {
        "type": label,
        "answer": raw.get("answer", ""),
        "citations": citations,
    }
    return bool(citations), fields


def _retry_with_rewritten_query(
    body: AskRequest, provider_key: str, question: str, resources: dict,
):
    """qna-mode Requirement 9's "checked again" moment, extended one
    step: when the first pass finds nothing citable, ask the visitor's
    own model for retrieval keywords in the source's own period
    vocabulary (query_rewrite.py) and retry hybrid_search once with
    those, rather than giving up immediately on a modern-phrasing-vs-
    archaic-translation vocabulary mismatch (docs/decision-log.md).

    Only called from the no-citations branch, never on every request -
    it's one extra LLM call, paid only on the subset of questions that
    would otherwise fail outright. Returns (None, None) if the rewrite
    itself fails or comes back empty, so callers can fall through to
    the original no_answer result rather than crash."""
    rewritten = query_rewrite.rewrite_query(body.provider, provider_key, question, body.model)
    if not rewritten:
        return None, None
    return search.hybrid_search(
        query=rewritten,
        bm25_index=resources["bm25_index"],
        openai_client=resources["openai_client"],
        supabase_client=resources["supabase_client"],
    )


async def handle_ask(request: Request, body: AskRequest, resources: dict) -> JSONResponse:
    # HeaderRedactionMiddleware strips this header before any route
    # handler runs (so it can never end up in a log line) and stashes
    # it on request.state instead - see entry_middleware.py. Falls back
    # to the raw header for callers/tests that bypass that middleware.
    provider_key = getattr(request.state, "provider_key", None) or request.headers.get("x-provider-key", "")
    if not provider_key:
        return _error(400, "missing_key", "API key must be provided")
    if not body.provider:
        return _error(400, "missing_provider", "Provider must be selected")

    # --- Our own visitor request limit (Task 10) - separate from a
    # provider rate-limiting the visitor's own key. ---
    client_ip = rate_limit.get_client_ip(request)
    rate_ok, rate_message = rate_limit.check_rate_limit(client_ip)
    if not rate_ok:
        return _error(429, "throttled", rate_message)

    question = body.question.strip()
    has_context = bool(body.context)

    # --- Guardrails, then scope (Tasks 9, 8) - both are normal "decline"
    # answers, not HTTP errors: the App is working correctly, it's just
    # saying no (qna-mode Requirement 9.4). ---
    guardrails_ok, guardrails_message = guardrails.check_guardrails(question)
    if not guardrails_ok:
        return JSONResponse({"type": "decline", "message": guardrails_message})

    in_scope, decline_message = scope.check_scope(question, has_context=has_context)
    if not in_scope:
        return JSONResponse({"type": "decline", "message": decline_message})

    # --- Retrieval (Task 7) ---
    passages, degraded = search.hybrid_search(
        query=question,
        bm25_index=resources["bm25_index"],
        openai_client=resources["openai_client"],
        supabase_client=resources["supabase_client"],
    )

    # --- Expand path: Tell Me More (qna-mode Requirement 7) ---
    if body.expand:
        label = body.label
        if label not in ("factual", "philosophical", "ambiguous"):
            try:
                classification = classifier.classify_question(
                    body.provider, provider_key, question, body.model
                )
            except llm_client.LLMError as e:
                return _error(400, e.kind, str(e))
            label = classification["label"]

        try:
            raw = answer.write_full_answer(
                body.provider, provider_key, question, label, passages, body.model
            )
        except llm_client.LLMError as e:
            return _error(400, e.kind, str(e))

        citations = answer.build_citations(raw.get("used_ids"), passages, raw.get("answer", ""))
        query_rewritten = False
        if not citations:
            retry_passages, retry_degraded = _retry_with_rewritten_query(
                body, provider_key, question, resources
            )
            if retry_passages is not None:
                try:
                    retry_raw = answer.write_full_answer(
                        body.provider, provider_key, question, label, retry_passages, body.model
                    )
                except llm_client.LLMError:
                    retry_raw = {}
                retry_citations = answer.build_citations(
                    retry_raw.get("used_ids"), retry_passages, retry_raw.get("answer", "")
                )
                if retry_citations:
                    raw, passages, degraded = retry_raw, retry_passages, retry_degraded
                    citations = retry_citations
                    query_rewritten = True

        if not citations:
            suggestions = answer.suggest_related_topics(passages)
            return JSONResponse({
                "type": "no_answer",
                "message": answer.NO_ANSWER_MESSAGE.format(suggestions=", ".join(suggestions)),
                "suggestions": suggestions,
            })
        return JSONResponse({
            "type": label,
            "expanded": True,
            "answer": raw.get("answer", ""),
            "citations": citations,
            "meaning_search_degraded": degraded,
            "query_rewritten": query_rewritten,
        })

    # --- Short-answer path (qna-mode Requirements 2-6) ---
    try:
        classification = classifier.classify_question(
            body.provider, provider_key, question, body.model
        )
    except llm_client.LLMError as e:
        return _error(400, e.kind, str(e))
    label = classification["label"]

    try:
        raw = answer.write_answer(body.provider, provider_key, question, label, passages, body.model)
    except llm_client.LLMError as e:
        return _error(400, e.kind, str(e))

    has_citations, fields = _citation_lists(label, raw, passages)
    query_rewritten = False
    if not has_citations:
        # qna-mode Requirement 9's "checked again" moment - now extended
        # with one retry: ask the visitor's own model for retrieval
        # keywords in the source's own period vocabulary and search
        # again before giving up (docs/decision-log.md).
        retry_passages, retry_degraded = _retry_with_rewritten_query(
            body, provider_key, question, resources
        )
        if retry_passages is not None:
            try:
                retry_raw = answer.write_answer(
                    body.provider, provider_key, question, label, retry_passages, body.model
                )
            except llm_client.LLMError:
                retry_raw = {}
            retry_has_citations, retry_fields = _citation_lists(label, retry_raw, retry_passages)
            if retry_has_citations:
                has_citations, fields = retry_has_citations, retry_fields
                passages, degraded = retry_passages, retry_degraded
                query_rewritten = True

    if not has_citations:
        # qna-mode Requirement 9: either the model found nothing usable
        # (raw == {}) or every id it reported was invalid/hallucinated -
        # both mean "don't show this as an answer" (design.md: "checked
        # again" after dropping citations) - even after the rewrite retry.
        suggestions = answer.suggest_related_topics(passages)
        return JSONResponse({
            "type": "no_answer",
            "message": answer.NO_ANSWER_MESSAGE.format(suggestions=", ".join(suggestions)),
            "suggestions": suggestions,
        })

    fields["meaning_search_degraded"] = degraded
    fields["classifier_confidence"] = classification["confidence"]
    fields["query_rewritten"] = query_rewritten
    return JSONResponse(fields)
