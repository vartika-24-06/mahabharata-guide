"""
Entry-screen spec, POST /api/session-token: issues a stateless
HMAC-signed opaque token used as the secondary component of the throttle
key (IP + token), giving per-tab fairness on shared IPs. The backend
doesn't need to validate the token on every request - its signature just
prevents trivial forgery (design.md: "A forged or replayed token shifts
throttle tracking to the attacker's chosen key but does not grant API
access; the worst outcome is a different throttle bucket, not a security
bypass.").
"""
import hashlib
import hmac
import os
import secrets
import time


def _secret_key() -> bytes:
    # Held server-side only, same handling as the two API keys this
    # backend already never logs (the visitor's own key, our embeddings
    # key) - just for signing, never sent anywhere.
    secret = os.environ.get("SESSION_TOKEN_SECRET")
    if not secret:
        raise RuntimeError(
            "SESSION_TOKEN_SECRET is not set. Generate one (e.g. "
            "`python -c \"import secrets; print(secrets.token_hex(32))\"`) "
            "and set it as an environment variable / in backend/.env."
        )
    return secret.encode()


def issue_session_token() -> str:
    nonce = secrets.token_hex(16)
    ts = str(int(time.time()))
    payload = f"{nonce}:{ts}"
    sig = hmac.new(_secret_key(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"
