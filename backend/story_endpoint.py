"""
Task 15: the real Story endpoint (POST /api/story).

Mirrors qna_endpoint.py's pipeline and header/error contract (rate limit
-> guardrails -> scope -> retrieval -> write -> citations; same
X-Provider-Key / HTTP 400 error shape), but for Story Mode.

STORY IDENTITY AND "EPISODES" - an honest simplification: the source
text has no marked story-arc boundaries, so a "story" here is just a
contiguous run of a catalogue subject's qualifying sections (Task 14),
chunked into fixed-size groups (EPISODE_SIZE) in the corpus's own
canonical book/section order. "Tell me more" means the next chunk for
the same subject; "I already know this one" jumps to a different chunk
for the same subject. This is a naive segmentation, not real
narrative-arc detection, and is documented here rather than presented as
more sophisticated than it is (see docs/decision-log.md).

A story_id ("<subject>#<episode_index>") identifies one episode. The
browser's Shown Stories list (story-mode Requirement 8) is a list of
these ids, sent back on each request so a repeat isn't preferred.
"""
import random

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import answer  # reuses build_citations() - same correctness guarantee as Q&A
import guardrails
import llm_client
import rate_limit
import scope
import story

EPISODE_SIZE = 3


class StoryRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    # "typed" | "character" | "parva" | "surprise" | "continue" | "another"
    request_type: str
    text: str | None = None            # request_type == "typed"
    subject: str | None = None         # "character" / "parva" / "continue" / "another"
    episode_index: int | None = None   # "continue" / "another": the CURRENT episode
    previous_text: str | None = None   # "continue": the snippet already shown, for continuity
    shown_stories: list[str] | None = None  # story_ids already shown this session


def _error(status: int, kind: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": kind, "message": message})


def _find_entry(catalogue: dict, subject: str) -> dict | None:
    for entry in catalogue["characters"] + catalogue["parvas"]:
        if entry["subject"] == subject:
            return entry
    return None


def _episodes(entry: dict) -> list[list[dict]]:
    refs = entry["section_refs"]
    return [refs[i:i + EPISODE_SIZE] for i in range(0, len(refs), EPISODE_SIZE)]


def _fetch_passages(supabase_client, section_refs: list[dict]) -> list[dict]:
    """Pulls every passage for a fixed list of (parva_name, section) pairs
    straight from Supabase, in passage order. No search/ranking needed -
    these sections are already known from the catalogue, unlike a typed
    request which goes through hybrid_search instead."""
    passages = []
    for ref in section_refs:
        response = (
            supabase_client.table("passages")
            .select("parva_file, book_number, parva_name, section, passage_index, text")
            .eq("parva_name", ref["parva_name"])
            .eq("section", ref["section"])
            .order("passage_index")
            .execute()
        )
        for row in response.data:
            passages.append({
                "meta": {
                    "parva_file": row["parva_file"],
                    "book_number": row["book_number"],
                    "parva_name": row["parva_name"],
                    "section": row["section"],
                    "passage_index": row["passage_index"],
                },
                "text": row["text"],
            })
    return passages


def _pick_unshown_episode(entry: dict, shown_stories: list[str]) -> int:
    """story-mode Requirement 3.3 / 5.2: prefer an episode not among
    Shown Stories. Falls back to episode 0 if every episode for this
    subject has already been shown - repeating is better than refusing."""
    shown = set(shown_stories or [])
    episodes = _episodes(entry)
    for i in range(len(episodes)):
        if f"{entry['subject']}#{i}" not in shown:
            return i
    return 0


def _pick_surprise(catalogue: dict, shown_stories: list[str]) -> tuple[dict, int]:
    """story-mode Requirement 5: pick from Featured Characters + Parvas,
    preferring a (subject, episode) combination not already shown."""
    shown = set(shown_stories or [])
    all_entries = catalogue["characters"] + catalogue["parvas"]
    candidates = []
    for entry in all_entries:
        for i in range(len(_episodes(entry))):
            if f"{entry['subject']}#{i}" not in shown:
                candidates.append((entry, i))
    if candidates:
        return random.choice(candidates)
    entry = random.choice(all_entries)
    return entry, 0


def _suggest_subjects(catalogue: dict, limit: int = 3) -> list[str]:
    return [c["subject"] for c in catalogue["characters"][:limit]]


def _snippet_response(story_id: str, subject: str, raw: dict, passages: list[dict],
                       catalogue: dict, complete: bool, degraded: bool = False) -> JSONResponse:
    citations = answer.build_citations(raw.get("used_ids"), passages)
    if not citations:
        return JSONResponse({
            "type": "no_story",
            "message": "The text doesn't have enough here to tell that story. "
                       f"You might try {', '.join(_suggest_subjects(catalogue))} instead.",
            "suggestions": _suggest_subjects(catalogue),
        })
    return JSONResponse({
        "type": "story",
        "story_id": story_id,
        "subject": subject,
        "text": raw.get("text", ""),
        "citations": citations,
        "complete": complete,
        "meaning_search_degraded": degraded,
    })


async def handle_story(request: Request, body: StoryRequest, resources: dict) -> JSONResponse:
    provider_key = request.headers.get("x-provider-key", "")
    if not provider_key:
        return _error(400, "missing_key", "API key must be provided")
    if not body.provider:
        return _error(400, "missing_provider", "Provider must be selected")

    client_ip = rate_limit.get_client_ip(request)
    rate_ok, rate_message = rate_limit.check_rate_limit(client_ip)
    if not rate_ok:
        return _error(429, "throttled", rate_message)

    catalogue = resources["catalogue"]
    supabase_client = resources["supabase_client"]

    if body.request_type == "typed":
        import search  # only needed for the typed-request search path
        text = (body.text or "").strip()
        guardrails_ok, guardrails_message = guardrails.check_guardrails(text)
        if not guardrails_ok:
            return JSONResponse({"type": "decline", "message": guardrails_message})
        in_scope, decline_message = scope.check_scope(text, has_context=False)
        if not in_scope:
            return JSONResponse({"type": "decline", "message": decline_message})

        passages, degraded = search.hybrid_search(
            query=text,
            bm25_index=resources["bm25_index"],
            openai_client=resources["openai_client"],
            supabase_client=supabase_client,
        )
        if not passages:
            return JSONResponse({
                "type": "no_story",
                "message": f"The text doesn't have a story matching that. "
                           f"You might try {', '.join(_suggest_subjects(catalogue))} instead.",
                "suggestions": _suggest_subjects(catalogue),
            })
        try:
            raw = story.write_snippet(body.provider, provider_key, text, passages, body.model)
        except llm_client.LLMError as e:
            return _error(400, e.kind, str(e))

        top_meta = passages[0]["meta"]
        story_id = f"typed:{top_meta['parva_name']}-{top_meta['section']}#0"
        return _snippet_response(story_id, text, raw, passages, catalogue, complete=True, degraded=degraded)

    if body.request_type in ("character", "parva"):
        entry = _find_entry(catalogue, body.subject or "")
        if entry is None:
            return _error(400, "other", f"Unknown subject: {body.subject!r}")
        episode_index = _pick_unshown_episode(entry, body.shown_stories)
        episodes = _episodes(entry)
        passages = _fetch_passages(supabase_client, episodes[episode_index])
        try:
            raw = story.write_snippet(body.provider, provider_key, entry["subject"], passages, body.model)
        except llm_client.LLMError as e:
            return _error(400, e.kind, str(e))
        story_id = f"{entry['subject']}#{episode_index}"
        complete = episode_index == len(episodes) - 1
        return _snippet_response(story_id, entry["subject"], raw, passages, catalogue, complete=complete)

    if body.request_type == "surprise":
        entry, episode_index = _pick_surprise(catalogue, body.shown_stories)
        episodes = _episodes(entry)
        passages = _fetch_passages(supabase_client, episodes[episode_index])
        try:
            raw = story.write_snippet(body.provider, provider_key, entry["subject"], passages, body.model)
        except llm_client.LLMError as e:
            return _error(400, e.kind, str(e))
        story_id = f"{entry['subject']}#{episode_index}"
        complete = episode_index == len(episodes) - 1
        return _snippet_response(story_id, entry["subject"], raw, passages, catalogue, complete=complete)

    if body.request_type == "continue":
        entry = _find_entry(catalogue, body.subject or "")
        if entry is None or body.episode_index is None:
            return _error(400, "other", "A subject and current episode_index are required to continue.")
        episodes = _episodes(entry)
        next_index = body.episode_index + 1
        if next_index >= len(episodes):
            # story-mode Requirement 7.6: told in full - say so, offer the
            # 7.3/7.5 choices (frontend's job; no new content to send).
            return JSONResponse({"type": "complete", "message": "That's the whole story the text has on this."})
        passages = _fetch_passages(supabase_client, episodes[next_index])
        try:
            raw = story.write_continuation(
                body.provider, provider_key, entry["subject"],
                body.previous_text or "", passages, body.model,
            )
        except llm_client.LLMError as e:
            return _error(400, e.kind, str(e))
        story_id = f"{entry['subject']}#{next_index}"
        complete = next_index == len(episodes) - 1
        return _snippet_response(story_id, entry["subject"], raw, passages, catalogue, complete=complete)

    if body.request_type == "another":
        entry = _find_entry(catalogue, body.subject or "")
        if entry is None:
            return _error(400, "other", f"Unknown subject: {body.subject!r}")
        episodes = _episodes(entry)
        other_indices = [i for i in range(len(episodes)) if i != body.episode_index]
        if not other_indices:
            # story-mode Requirement 7.4: no other story on this subject.
            return JSONResponse({
                "type": "no_other_story",
                "message": f"The text doesn't have another story about {entry['subject']}.",
            })
        shown = set(body.shown_stories or [])
        unshown = [i for i in other_indices if f"{entry['subject']}#{i}" not in shown]
        episode_index = unshown[0] if unshown else other_indices[0]
        passages = _fetch_passages(supabase_client, episodes[episode_index])
        try:
            raw = story.write_snippet(body.provider, provider_key, entry["subject"], passages, body.model)
        except llm_client.LLMError as e:
            return _error(400, e.kind, str(e))
        story_id = f"{entry['subject']}#{episode_index}"
        complete = episode_index == len(episodes) - 1
        return _snippet_response(story_id, entry["subject"], raw, passages, catalogue, complete=complete)

    return _error(400, "other", f"Unknown request_type: {body.request_type!r}")
