"""
Entry-screen spec: HeaderRedactionMiddleware and ThrottleMiddleware.

Adapted directly from design.md's own implementation patterns (section
"HeaderRedactionMiddleware / ThrottleMiddleware - Implementation
Pattern"), with minor changes only where this backend's actual routes
differ:
  - datetime.utcnow() -> datetime.now(timezone.utc) (utcnow is
    deprecated as of Python 3.12+).
  - ping_error_code is set by ping_endpoint.py's handle_ping(), same
    contract the design doc specifies for its ProviderAdapter.

Both are in-memory, single-process stores - the same v1 limitation
already documented and accepted for rate_limit.py's visitor request
throttle (resets on restart, doesn't work across multiple instances;
Render's free plan runs a single uvicorn worker, per entry-screen
tasks.md 2.1).
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

REDACTED_HEADERS = frozenset({"x-provider-key"})

IP_FAILURE_THRESHOLD = 20
IP_WINDOW_SECONDS = 900        # 15 minutes
SESSION_FAILURE_THRESHOLD = 5
COOLDOWN_SECONDS = 300          # 5 minutes
SESSION_TOKEN_RATE_LIMIT = 30   # per 15-minute window per IP

THROTTLE_COUNTED_ERRORS = frozenset({"auth", "unknown_model"})

_ip_buckets: dict[str, dict] = defaultdict(lambda: {"failures": [], "cooldown_until": None})
_session_buckets: dict[str, dict] = defaultdict(lambda: {"failures": 0, "cooldown_until": None})
_session_token_issue_log: dict[str, list] = defaultdict(list)


def _now():
    return datetime.now(timezone.utc)


class HeaderRedactionMiddleware(BaseHTTPMiddleware):
    """Strips X-Provider-Key from the request before any logging can see
    it. Route handlers read the key from request.state.provider_key,
    set here before the header is removed."""

    async def dispatch(self, request: Request, call_next):
        provider_key = request.headers.get("x-provider-key", "")
        request.state.provider_key = provider_key

        redacted_raw = [
            (name, value)
            for name, value in request.scope["headers"]
            if name.decode().lower() not in REDACTED_HEADERS
        ]
        request.scope["headers"] = redacted_raw

        return await call_next(request)


def _get_ip(request: Request) -> str:
    # Matches rate_limit.get_client_ip's own precedence (X-Forwarded-For
    # first, for when this sits behind Render's proxy).
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_cooldown(bucket: dict) -> int | None:
    if bucket["cooldown_until"] and _now() < bucket["cooldown_until"]:
        return int((bucket["cooldown_until"] - _now()).total_seconds())
    return None


class ThrottleMiddleware(BaseHTTPMiddleware):
    """Two independent throttles:
    - /api/session-token: flat IP rate limit (SESSION_TOKEN_RATE_LIMIT
      per IP_WINDOW_SECONDS), since it's free to call and otherwise
      unbounded.
    - /api/ping: a cooldown triggered by repeated auth/unknown_model
      failures (not rate_limit/other, which aren't the visitor's fault
      in the same way) - tracked per-IP (rolling window) AND per-session
      -token (consecutive), whichever trips first wins."""

    async def dispatch(self, request: Request, call_next):
        ip = _get_ip(request)
        path = request.url.path

        if path == "/api/session-token":
            now = _now()
            window_start = now - timedelta(seconds=IP_WINDOW_SECONDS)
            log = [t for t in _session_token_issue_log[ip] if t > window_start]
            if len(log) >= SESSION_TOKEN_RATE_LIMIT:
                _session_token_issue_log[ip] = log
                return JSONResponse(
                    status_code=429,
                    content={"error": "throttle", "message": "Too many requests."},
                    headers={"Retry-After": "60"},
                )
            log.append(now)
            _session_token_issue_log[ip] = log
            return await call_next(request)

        if path != "/api/ping":
            return await call_next(request)

        # entry-screen tasks.md amendment (Task 8.1): missing/empty token
        # buckets by IP instead of a shared "anonymous" key, so unrelated
        # visitors who haven't gotten a session token yet don't share one
        # throttle bucket.
        token = request.headers.get("x-session-token") or f"anon:{ip}"
        ip_bucket = _ip_buckets[ip]
        session_bucket = _session_buckets[token]

        remaining = [r for r in (_check_cooldown(ip_bucket), _check_cooldown(session_bucket)) if r is not None]
        if remaining:
            return JSONResponse(
                status_code=429,
                content={"error": "throttle", "message": "Too many failed attempts. Try again later."},
                headers={"Retry-After": str(max(remaining))},
            )

        response = await call_next(request)

        error_code = getattr(request.state, "ping_error_code", None)
        is_counted_failure = error_code in THROTTLE_COUNTED_ERRORS

        if response.status_code == 200:
            session_bucket["failures"] = 0
            session_bucket["cooldown_until"] = None
        elif is_counted_failure:
            now = _now()
            window_start = now - timedelta(seconds=IP_WINDOW_SECONDS)
            ip_bucket["failures"] = [t for t in ip_bucket["failures"] if t > window_start]
            ip_bucket["failures"].append(now)
            if len(ip_bucket["failures"]) >= IP_FAILURE_THRESHOLD:
                ip_bucket["cooldown_until"] = now + timedelta(seconds=COOLDOWN_SECONDS)
                ip_bucket["failures"] = []

            session_bucket["failures"] += 1
            if session_bucket["failures"] >= SESSION_FAILURE_THRESHOLD:
                session_bucket["cooldown_until"] = now + timedelta(seconds=COOLDOWN_SECONDS)
                session_bucket["failures"] = 0

        return response
