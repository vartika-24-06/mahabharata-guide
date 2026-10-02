"""
UX item 7: thumbs up/down feedback on an answer (POST /api/feedback).

Deliberately minimal, matching the scope Vartika chose: just log the
thumb and the Q&A data it's about to Supabase, for her to review
later - no automated action taken on it, no rate limiting beyond what
already applies globally. Not part of the design.md/qna-mode spec this
backend otherwise implements; it's a standalone addition.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class Citation(BaseModel):
    parva_name: str
    section: int
    excerpt: str


class FeedbackRequest(BaseModel):
    question: str
    answer_type: str
    answer_text: str
    citations: list[Citation] = []
    rating: str  # "up" | "down"
    provider: str | None = None
    model: str | None = None


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": "other", "message": message})


async def handle_feedback(request: Request, body: FeedbackRequest, resources: dict):
    if body.rating not in ("up", "down"):
        return _error(400, "rating must be 'up' or 'down'.")
    if not body.question.strip() or not body.answer_text.strip():
        return _error(400, "question and answer_text are required.")

    supabase_client = resources["supabase_client"]
    row = {
        "question": body.question,
        "answer_type": body.answer_type,
        "answer_text": body.answer_text,
        "citations": [c.model_dump() for c in body.citations],
        "rating": body.rating,
        "provider": body.provider,
        "model": body.model,
    }
    try:
        supabase_client.table("feedback").insert(row).execute()
    except Exception as exc:
        # Feedback is a nice-to-have log, not core Q&A - a Supabase
        # hiccup here shouldn't look like a broken app to a visitor who
        # just clicked a thumb. Logged server-side so Vartika can still
        # notice if it's happening a lot, per docs/decision-log.md's
        # pattern for other best-effort paths (search.py's embeddings
        # fallback, query_rewrite.py's LLMError handling).
        print(f"feedback_endpoint: failed to store feedback ({exc.__class__.__name__}): {exc}")
        return _error(502, "Could not save feedback right now.")

    return {"status": "ok"}
