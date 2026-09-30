"""
Task 11: question classifier (design.md "Classification (Q&A)").

One short call to the VISITOR's own model (not our server key) returns a
label - factual, philosophical or ambiguous - and a confidence. Low
confidence becomes ambiguous rather than a shaky factual/philosophical
guess, since an ambiguous answer (two short cited readings, offering
"tell me more") degrades more gracefully than confidently answering the
wrong way.

CONFIDENCE_THRESHOLD is a placeholder, like scope.py's curated list and
rate_limit.py's numbers: design.md says "The accuracy bar and which
mistakes matter most are your decisions" - this needs tuning against the
real eval set once there's a real key to test with, which needs to
happen with a human weighing in on what threshold trades off acceptably
against what (see docs/qna-eval-set for the rows this matters most for:
11-22, the factual/philosophical/ambiguous cases).
"""
import json

import llm_client

CONFIDENCE_THRESHOLD = 0.6

VALID_LABELS = {"factual", "philosophical", "ambiguous"}

SYSTEM_PROMPT = """You classify questions about the Mahabharata epic into exactly one of three labels:

- "factual": asks about events, people, places - what happened, who did what.
- "philosophical": asks about meaning, duty, consequence, or moral themes as the epic treats them.
- "ambiguous": the question genuinely asks for both a factual answer and a philosophical one together.

Respond with ONLY a JSON object, no other text, no code fence:
{"label": "factual" | "philosophical" | "ambiguous", "confidence": <number between 0 and 1>}

confidence reflects how clearly the question fits its label - use a lower number for a question that could reasonably be read more than one way."""


def classify_question(
    provider: str,
    api_key: str,
    question: str,
    model: str | None = None,
) -> dict:
    """Returns {"label": ..., "confidence": ..., "raw_label": ...}.
    raw_label is what the model actually said before the confidence
    threshold was applied - label is what to act on (low confidence gets
    downgraded to "ambiguous" regardless of what the model said)."""
    response_text = llm_client.complete(
        provider=provider,
        api_key=api_key,
        system=SYSTEM_PROMPT,
        user=question,
        model=model,
        max_tokens=50,
    )

    try:
        parsed = llm_client.extract_json(response_text)
        raw_label = parsed["label"]
        confidence = float(parsed["confidence"])
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        # Model didn't follow the format - treat as maximally uncertain
        # rather than crashing the request.
        return {"label": "ambiguous", "confidence": 0.0, "raw_label": None}

    if raw_label not in VALID_LABELS:
        return {"label": "ambiguous", "confidence": confidence, "raw_label": raw_label}

    if confidence < CONFIDENCE_THRESHOLD:
        return {"label": "ambiguous", "confidence": confidence, "raw_label": raw_label}

    return {"label": raw_label, "confidence": confidence, "raw_label": raw_label}
