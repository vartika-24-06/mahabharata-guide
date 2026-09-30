"""
Entry-screen spec, POST /api/ping: validates a visitor's API key + model
by sending a minimal real completion request to the provider.

Reuses llm_client.complete() (Task 11) rather than a separate
ProviderAdapter - it already normalizes every provider's auth/
unknown_model/rate_limit/other errors into the same LLMError taxonomy
the design's error table asks for, so there's nothing provider-specific
left to write here. The two extra failure modes the ping contract adds
on top of LLMError (502 network, 504 timeout) are handled at this layer
since they're about reaching the provider at all, not about what it said.
"""
import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import llm_client

PING_MESSAGE = "Reply with the single word: ok"
PING_MAX_TOKENS = 16


class PingRequest(BaseModel):
    provider: str | None = None
    model: str | None = None


def _error(status: int, kind: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": kind, "message": message})


async def handle_ping(request: Request, body: PingRequest) -> JSONResponse:
    # HeaderRedactionMiddleware strips this header before any route
    # handler runs (so it can never end up in a log line) and stashes
    # it on request.state instead - see entry_middleware.py. Falls back
    # to the raw header for callers/tests that bypass that middleware.
    provider_key = getattr(request.state, "provider_key", None) or request.headers.get("x-provider-key", "")
    if not provider_key:
        return _error(400, "missing_key", "API key must be provided")
    if not body.provider:
        return _error(400, "missing_provider", "Provider must be selected")
    if body.provider not in llm_client.DEFAULT_MODELS:
        return _error(400, "other", f"Unknown provider '{body.provider}'.")

    resolved_model = body.model or llm_client.DEFAULT_MODELS[body.provider]

    try:
        llm_client.complete(
            provider=body.provider,
            api_key=provider_key,
            system="",
            user=PING_MESSAGE,
            model=resolved_model,
            max_tokens=PING_MAX_TOKENS,
            timeout=10,
        )
    except llm_client.LLMError as e:
        # Recorded so ThrottleMiddleware can decide whether this failure
        # counts toward the auth/unknown_model cooldown (design.md:
        # "the ProviderAdapter must set request.state.ping_error_code").
        request.state.ping_error_code = e.kind
        return _error(400, e.kind, str(e))
    except httpx.TimeoutException:
        request.state.ping_error_code = "timeout"
        return _error(504, "timeout", "Validation timed out after 10 seconds")
    except httpx.RequestError:
        request.state.ping_error_code = "network"
        return _error(502, "network", "Could not reach provider")

    request.state.ping_error_code = None
    return JSONResponse({"status": "ok", "model": resolved_model})
