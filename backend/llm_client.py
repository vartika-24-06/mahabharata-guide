"""
Provider-agnostic client for the VISITOR's own BYOK key (OpenAI,
Anthropic or Gemini) - never our own server-side key (that's OpenAI
embeddings only, handled separately in search.py/push_to_supabase.py).

Endpoints, auth headers and payload shapes verified against each
provider's docs (see docs/provider-verification-notes.md). Uses raw
httpx calls rather than each provider's SDK, matching the entry-screen
design's proxy architecture (mahabharata-entry-screen/design.md:
ProviderAdapter) and avoiding three extra heavy SDK dependencies for
calls this simple.

The visitor's key passes through this module only for the duration of
one request - never logged, never written to disk, never held past the
function call that used it (design.md / entry-screen Requirement 8).
"""
import json
import re

import httpx


class LLMError(Exception):
    """kind is one of: auth, unknown_model, rate_limit, other - matches
    the normalization in docs/provider-verification-notes.md, so callers
    can show a consistent message regardless of provider."""
    def __init__(self, kind: str, message: str):
        self.kind = kind
        super().__init__(message)


def _call_openai(api_key: str, model: str, system: str, user: str, max_tokens: int, timeout: float) -> str:
    response = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_completion_tokens": max_tokens,
        },
        timeout=timeout,
    )
    if response.status_code == 401:
        raise LLMError("auth", "OpenAI rejected this API key.")
    if response.status_code in (404, 400):
        raise LLMError("unknown_model", f"OpenAI doesn't recognize model '{model}'.")
    if response.status_code == 429:
        raise LLMError("rate_limit", "OpenAI rate-limited this request.")
    if response.status_code >= 500:
        raise LLMError("other", "OpenAI's API returned a server error.")
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _call_anthropic(api_key: str, model: str, system: str, user: str, max_tokens: int, timeout: float) -> str:
    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=timeout,
    )
    if response.status_code in (401, 403):
        raise LLMError("auth", "Anthropic rejected this API key.")
    if response.status_code == 404:
        raise LLMError("unknown_model", f"Anthropic doesn't recognize model '{model}'.")
    if response.status_code == 429:
        raise LLMError("rate_limit", "Anthropic rate-limited this request.")
    if response.status_code >= 500:
        raise LLMError("other", "Anthropic's API returned a server error.")
    response.raise_for_status()
    return response.json()["content"][0]["text"]


def _call_gemini(api_key: str, model: str, system: str, user: str, max_tokens: int, timeout: float) -> str:
    response = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": api_key},
        json={
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        },
        timeout=timeout,
    )
    if response.status_code == 400:
        raise LLMError("auth", "Gemini rejected this API key.")
    if response.status_code == 403:
        raise LLMError("auth", "Gemini rejected this API key.")
    if response.status_code == 404:
        raise LLMError("unknown_model", f"Gemini doesn't recognize model '{model}'.")
    if response.status_code == 429:
        raise LLMError("rate_limit", "Gemini rate-limited this request.")
    if response.status_code >= 500:
        raise LLMError("other", "Gemini's API returned a server error.")
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]


DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "gemini": "gemini-3.5-flash-lite",
}

_PROVIDER_FUNCS = {
    "openai": _call_openai,
    "anthropic": _call_anthropic,
    "gemini": _call_gemini,
}


def complete(provider: str, api_key: str, system: str, user: str,
             model: str | None = None, max_tokens: int = 800,
             timeout: float = 30) -> str:
    """Calls the visitor's chosen provider with their own key. Raises
    LLMError (kind: auth/unknown_model/rate_limit/other) on failure -
    callers should catch this and show the visitor a plain message,
    never the raw provider error (which could leak key-shaped details).
    Raw httpx exceptions (timeout, connection failure) are NOT caught
    here - they're about reaching the provider at all rather than what
    it said, so callers that need a distinct network/timeout response
    (entry-screen's /api/ping) catch httpx.TimeoutException /
    httpx.RequestError themselves. timeout defaults to 30s (Q&A/story
    answers can be slower); /api/ping passes 10s per the entry-screen
    spec's own validation timeout."""
    if provider not in _PROVIDER_FUNCS:
        raise LLMError("other", f"Unknown provider '{provider}'. "
                        f"Expected one of: {', '.join(_PROVIDER_FUNCS)}.")
    model = model or DEFAULT_MODELS[provider]
    return _PROVIDER_FUNCS[provider](api_key, model, system, user, max_tokens, timeout)


def complete_safe(provider: str, api_key: str, system: str, user: str,
                   model: str | None = None, max_tokens: int = 800,
                   timeout: float = 30) -> str:
    """Same contract as complete(), but also normalizes a raw httpx
    timeout/connection failure into LLMError (kind "other") instead of
    letting it propagate uncaught.

    Found via a real live-eval run (Task 19): a genuine OpenAI read
    timeout during answer.write_answer() crashed run_eval.py with a raw
    httpx.ReadTimeout traceback - and the exact same call, from the same
    module, is what qna_endpoint.py and story_endpoint.py use in
    production, each of which only catches LLMError. Without this, a
    slow provider response would 500 the whole request instead of
    returning the qna-mode/story-mode "provider had a problem" response
    (Requirement 11) those endpoints are supposed to give. complete()
    itself is left as-is (and still used directly by /api/ping, which
    wants its own distinct 504/502 codes) - this wrapper is for the
    classifier/answer/story callers that just want one LLMError shape at
    their existing try/except call sites."""
    try:
        return complete(provider, api_key, system, user, model, max_tokens, timeout)
    except httpx.TimeoutException:
        raise LLMError("other", "The provider timed out before responding. Please try again.")
    except httpx.RequestError as exc:
        raise LLMError("other", f"Could not reach the provider ({exc.__class__.__name__}).")


def extract_json(text: str) -> dict:
    """Models sometimes wrap JSON in a markdown code fence or add a
    sentence before/after it despite being asked for JSON only. Strips
    a code fence if present, then finds the first {...} block."""
    text = text.strip()
    fence_match = re.match(r'^```(?:json)?\s*(.*?)\s*```$', text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    brace_match = re.search(r'\{.*\}', text, re.DOTALL)
    if brace_match:
        text = brace_match.group(0)
    return json.loads(text)
