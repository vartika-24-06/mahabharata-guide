"""
Task 15: story writer (design.md "Story mode"; story-mode requirements
6, 7, 9).

Mirrors answer.py's approach and reuses its build_citations(): the
visitor's own model writes from numbered reference passages and reports
which ones it used, and citations are built entirely from those ids by
OUR code, never from anything the model writes - same correctness
guarantee as Q&A answers (design.md Properties 1/2), just for a
narrated snippet instead of a short answer.
"""
import json

import llm_client

_BASE_RULES = """Rules for the story:
- Third person, plain modern English.
- Never state your own verdict on whether a person or action was right, wrong, a hero or a villain. If the text itself records a character or narrator giving a judgement, you may report that they said so, attributed and citable - but never state it as your own conclusion.
- Never tell the reader what lesson to take or how they should act.
- Only use events, dialogue and outcomes that appear in the numbered passages below. Never invent anything the passages don't support.
- Tell difficult or violent scenes plainly - war, betrayal, deceit, loss - at the level of the source material; don't soften or sensationalize (story-mode Requirement 9)."""


def _build_context_block(passages: list[dict]) -> str:
    lines = []
    for i, p in enumerate(passages, start=1):
        meta = p["meta"]
        lines.append(f"[P{i}] ({meta['parva_name']}, Section {meta['section']}): {p.get('text', '')}")
    return "\n\n".join(lines)


def _snippet_prompt(subject: str) -> str:
    return f"""You are telling a short story from the Mahabharata about {subject}, using only the numbered passages provided.

{_BASE_RULES}

Write a snippet of about 150 words - enough to read in about a minute on a phone (story-mode Requirement 6.1).

Respond with ONLY a JSON object, no other text, no code fence:
{{"text": "<about 150 word story snippet>", "used_ids": [<passage numbers you actually drew on, e.g. 1, 3>]}}"""


def _continuation_prompt(subject: str) -> str:
    return f"""You already told part of a story from the Mahabharata about {subject}. Continue it with the NEXT part, using only the new numbered passages provided below (these follow on from what was already told).

{_BASE_RULES}

Write about 150 words continuing the story - don't repeat what was already told, and don't summarize the earlier part.

Respond with ONLY a JSON object, no other text, no code fence:
{{"text": "<about 150 word continuation>", "used_ids": [<passage numbers you actually drew on>]}}"""


def write_snippet(
    provider: str,
    api_key: str,
    subject: str,
    passages: list[dict],
    model: str | None = None,
) -> dict:
    """passages: the sections chosen for this episode (see
    story_endpoint.py), each with meta + text. Returns the model's raw
    {"text", "used_ids"} - use answer.build_citations() next. Raises
    llm_client.LLMError on provider failure, same as answer.write_answer."""
    context = _build_context_block(passages)
    user_prompt = f"Numbered passages:\n{context}"

    response_text = llm_client.complete(
        provider=provider,
        api_key=api_key,
        system=_snippet_prompt(subject),
        user=user_prompt,
        model=model,
        max_tokens=400,
    )
    try:
        return llm_client.extract_json(response_text)
    except (json.JSONDecodeError, ValueError):
        return {}


def write_continuation(
    provider: str,
    api_key: str,
    subject: str,
    previous_text: str,
    passages: list[dict],
    model: str | None = None,
) -> dict:
    """Task 15 / story-mode Requirement 7.2 ("Tell me more"): continues
    the same story with the next episode's passages. previous_text is
    given for narrative continuity only (so the model doesn't repeat
    itself) - it is never itself a source of citable content, only the
    new `passages` are."""
    context = _build_context_block(passages)
    user_prompt = (
        f"What was already told:\n{previous_text}\n\n"
        f"New numbered passages (continue from here):\n{context}"
    )

    response_text = llm_client.complete(
        provider=provider,
        api_key=api_key,
        system=_continuation_prompt(subject),
        user=user_prompt,
        model=model,
        max_tokens=400,
    )
    try:
        return llm_client.extract_json(response_text)
    except (json.JSONDecodeError, ValueError):
        return {}
