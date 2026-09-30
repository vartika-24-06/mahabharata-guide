"""
Task 10: per-visitor request rate limit (design.md "Protecting the
service").

Keyed by network address (IP), not by any identity or key - this also
bounds how often our own embeddings key gets called per visitor (see
design.md "Meaning-based search"), so it's protecting both service
health and our own OpenAI usage.

In-memory only, by design: the app's whole privacy model is "the server
keeps nothing" (design.md - closing the tab clears session state), and a
single Render free-tier instance doesn't need a shared store for this.
Two real limitations worth knowing before relying on this in production:
  1. Resets to zero on every server restart/redeploy.
  2. Only works correctly with exactly one running instance - if this
     app ever runs on more than one dyno/worker, requests would be
     split across separate counters and the effective limit would be
     higher than intended. Fine for v1's single free-tier instance; would
     need a shared store (e.g. Redis, or a Supabase table) if that changes.

THE NUMBERS BELOW ARE PLACEHOLDER DEFAULTS, not a tuned decision - design.md
lists "the request-rate numbers" as an explicit open item. Revisit before
a real launch.
"""
import time

REQUESTS_PER_WINDOW = 20
WINDOW_SECONDS = 600  # 10 minutes

WAIT_MESSAGE_TEMPLATE = (
    "You're sending requests a little fast - please wait about {wait_s} "
    "seconds and try again."
)

# {ip: [timestamp, timestamp, ...]} - only recent timestamps within the
# window are kept; see _prune().
_request_log: dict[str, list[float]] = {}


def _prune(timestamps: list[float], now: float) -> list[float]:
    cutoff = now - WINDOW_SECONDS
    return [t for t in timestamps if t > cutoff]


def check_rate_limit(client_ip: str, now: float | None = None) -> tuple[bool, str | None]:
    """Returns (allowed, wait_message). If allowed, records this request
    against the visitor's count. Logs only a count and the fact of a
    rate-limit hit - never the request's question text (design.md
    "Protecting the service": logs contain counts and error types only)."""
    now = now if now is not None else time.time()

    timestamps = _prune(_request_log.get(client_ip, []), now)

    if len(timestamps) >= REQUESTS_PER_WINDOW:
        oldest = min(timestamps)
        wait_s = int(oldest + WINDOW_SECONDS - now) + 1
        print(f"Rate limit hit for a visitor ({len(timestamps)} requests "
              f"in the last {WINDOW_SECONDS}s)")
        return False, WAIT_MESSAGE_TEMPLATE.format(wait_s=wait_s)

    timestamps.append(now)
    _request_log[client_ip] = timestamps
    return True, None


def get_client_ip(request) -> str:
    """Render (and most PaaS hosts) sit behind a proxy, so the real
    visitor IP is in X-Forwarded-For, not request.client.host directly.
    Falls back to request.client.host for local dev, where there's no
    proxy in front."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
