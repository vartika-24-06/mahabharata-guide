# Implementation Plan: Mahabharata Entry Screen & API Key Handling

## Overview

This plan implements the Entry Screen, Path Selection, Key Modal, Key Status Element, and all API key handling for the Mahabharata guide web app. The work is split into five groups: verification, deployed skeleton, backend core, frontend key handling, and tests. The backend is Python/FastAPI deployed to Render; the frontend is React/TypeScript/Vite deployed to Vercel.

## Tasks

---

### Group 1 — Verification

- [ ] 1. Verify provider details and write documentation
  - For each of OpenAI, Anthropic, and Gemini, read the Default Models table in design.md (Revisions v2, item 6) and cross-check against current official documentation:
    - Default model ID (confirm it exists and is generally available)
    - Token-limit parameter name (`max_completion_tokens` vs `max_tokens` vs `generationConfig.maxOutputTokens`)
    - Minimum accepted token value for each parameter
    - HTTP status code and error code/type returned for an unknown model name
    - HTTP status code and error code/type returned for an invalid/unauthorised API key
  - Write all findings, discrepancies, and any corrected values to `docs/provider-verification-notes.md`
  - Note any provider details that could not be confirmed and flag them for manual verification before production launch
  - _Requirements: R5.1, R5.2, R7.1 (indirectly — correct defaults are required for the feature to work)_

---

### Group 2 — Deployed Skeleton

- [ ] 2. Initialise FastAPI project and deploy backend skeleton
  - [ ] 2.1 Create `backend/` directory with project structure
    - Create `backend/main.py`, `backend/requirements.txt`, `backend/runtime.txt`
    - Pin dependencies: `fastapi`, `uvicorn[standard]`, `httpx` (exact versions)
    - Implement `GET /health` returning `{"status": "ok"}` (used as Render liveness probe; see design.md Components → ProxyRouter)
    - Add a `render.yaml` or `Procfile` configured to run `uvicorn main:app --host 0.0.0.0 --port $PORT`
    - Run a single uvicorn worker (in-memory throttle counters require a single process; see design.md Revisions v2 item 6)
    - _Requirements: R10.1 (backend must be reachable from every screen)_
  - [ ]* 2.2 Deploy backend to Render and verify live `/health` endpoint
    - Push `backend/` to the repository and connect to Render as a web service
    - Confirm the live `/health` endpoint returns `{"status": "ok"}` via curl or browser
    - Note the live Render URL — it will be needed for `VITE_API_BASE_URL` in task 3
    - _Requirements: R10.1_

- [ ] 3. Initialise React/TypeScript/Vite frontend and deploy skeleton
  - [ ] 3.1 Create `frontend/` directory with Vite + React + TypeScript
    - Scaffold with `npm create vite@latest frontend -- --template react-ts`
    - Pin React, TypeScript, and Vite to exact versions in `package.json`
    - Add `VITE_API_BASE_URL` environment variable support (reads Render URL at build time; see design.md Revisions v2 item 3)
    - Implement `EntryScreen` component with:
      - `PathSelector`: two buttons labelled "Hear a Story" and "Ask a Question" (no logic yet)
      - A text input for the user's request
    - No key logic, no modal — static UI only
    - Add `vercel.json` (or `vite.config.ts` output config) for Vercel deployment
    - _Requirements: R1.1, R1.2, R1.3_
  - [ ]* 3.2 Deploy frontend to Vercel and verify live Entry Screen renders
    - Connect `frontend/` to Vercel and trigger a production deployment
    - Confirm the Entry Screen renders with both path buttons and the request input visible
    - Note the live Vercel URL — it will be needed for the backend CORS allow-list in task 9
    - _Requirements: R1.1, R1.2_

---

### Group 3 — Backend Core

- [ ] 4. Implement `POST /api/session-token`
  - [ ] 4.1 Implement the session-token endpoint
    - Create `backend/routers/session_token.py` and register the router in `main.py`
    - Generate a stateless HMAC-signed opaque token using `secrets.token_hex(16)`, `hmac`, `hashlib.sha256` per the token-construction snippet in design.md (FastAPI Endpoint Specifications → POST /api/session-token)
    - Read the signing secret from an environment variable (`SESSION_TOKEN_SECRET`); raise a startup error if the variable is missing
    - Return `{ "session_token": "<opaque-hmac-string>" }` with HTTP 200
    - No persistence — each call returns a fresh token with a new nonce and timestamp
    - Define the `SessionTokenResponse` Pydantic model from design.md (Data Models → FastAPI / Pydantic Models)
    - _Requirements: R12.1 (session token is the secondary throttle key)_
  - [ ]* 4.2 Write unit tests for session-token issuance
    - Assert response contains a non-empty `session_token` string
    - Assert two calls return different tokens (fresh nonce per call)
    - Assert the HMAC signature in the token is verifiable with the test secret key
    - _Requirements: R12.1_

- [ ] 5. Implement `HeaderRedactionMiddleware`
  - [ ] 5.1 Implement the middleware
    - Create `backend/middleware/header_redaction.py`
    - Implement `HeaderRedactionMiddleware` using the Implementation Pattern in design.md:
      - Save `request.headers.get("x-provider-key", "")` to `request.state.provider_key` before any modification
      - Rebuild `request.scope["headers"]` excluding `x-provider-key` so all downstream logging never sees the key
    - Register the middleware in `main.py` before `ThrottleMiddleware` and all route handlers
    - For Gemini native REST: set both the `httpx` logger and the `httpcore` logger to `WARNING` level (design.md Revisions v2 item 1) so the full Gemini request URL is never written to access logs at INFO
    - _Requirements: R8.7, R8.8_
  - [ ]* 5.2 Write unit tests for HeaderRedactionMiddleware
    - Assert `request.state.provider_key` contains the original key value after middleware runs
    - Assert `request.scope["headers"]` does not contain `x-provider-key` after middleware runs
    - Assert any log records emitted after the middleware do not contain the original key value
    - _Requirements: R8.7, R8.8_

- [ ] 6. Implement `ProviderAdapter`
  - [ ] 6.1 Implement OpenAI ping function
    - Create `backend/adapters/provider_adapter.py`
    - Define internal dataclasses `PingRequest`, `ProviderSuccess`, `ProviderError` (design.md Data Models → Normalised Error Envelope)
    - Implement `ping_openai(request: PingRequest) -> ProviderResult`:
      - `POST https://api.openai.com/v1/chat/completions`
      - Headers: `Authorization: Bearer <key>`, `Content-Type: application/json`
      - Body: `{ "model": "<model>", "messages": [{"role": "user", "content": "Reply with the single word: ok"}], "max_completion_tokens": 16 }`
      - 10-second httpx timeout
      - Map responses per design.md Provider Error Normalisation → OpenAI table: `401 invalid_api_key/no_api_key → auth`, `404 model_not_found → unknown_model`, `400 invalid_request_error with model in message → unknown_model`, `429 → rate_limit`, `5xx → other`, network error → `network`, timeout → `timeout`
      - Set `request.state.ping_error_code` on the FastAPI request object for ThrottleMiddleware consumption
    - _Requirements: R5.1, R15.1, R16.1, R17.1, R18.1, R19.1, R20.1_
  - [ ] 6.2 Implement Anthropic ping function
    - Implement `ping_anthropic(request: PingRequest) -> ProviderResult`:
      - `POST https://api.anthropic.com/v1/messages`
      - Headers: `x-api-key: <key>`, `anthropic-version: 2023-06-01`, `Content-Type: application/json`
      - Body: `{ "model": "<model>", "max_tokens": 16, "messages": [{"role": "user", "content": "Reply with the single word: ok"}] }` (`max_tokens` is required by Anthropic)
      - 10-second httpx timeout
      - Map responses per design.md Anthropic table: `401 authentication_error → auth`, `403 permission_error → auth`, `404 not_found_error → unknown_model`, `429 rate_limit_error → rate_limit`, `529 overloaded_error → other`, `500 api_error → other`, network → `network`, timeout → `timeout`
      - Set `request.state.ping_error_code`
    - _Requirements: R5.1, R15.1, R16.1, R17.1, R18.1, R19.1, R20.1_
  - [ ] 6.3 Implement Gemini ping function
    - Implement `ping_gemini(request: PingRequest) -> ProviderResult`:
      - Native REST: `POST https://generativelanguage.googleapis.com/v1beta/models/<model>:generateContent`
      - **Send the API key as the `x-goog-api-key` header** (design.md Revisions v2 item 1 — never in the URL query string)
      - Body: `{ "contents": [{"parts": [{"text": "Reply with the single word: ok"}]}], "generationConfig": {"maxOutputTokens": 16} }`
      - 10-second httpx timeout
      - Map responses per design.md Gemini table: `400 API_KEY_INVALID → auth`, `403 PERMISSION_DENIED → auth`, `404 NOT_FOUND → unknown_model`, `429 RESOURCE_EXHAUSTED → rate_limit`, `5xx → other`, network → `network`, timeout → `timeout`
      - Set `request.state.ping_error_code`
      - Set httpx and httpcore loggers to WARNING to suppress URL logging (Revisions v2 item 1)
    - _Requirements: R5.1, R15.1, R16.1, R17.1, R18.1, R19.1, R20.1_
  - [ ]* 6.4 Write unit tests for ProviderAdapter error normalisation (per provider)
    - For each provider: mock each HTTP status + error code in the normalisation tables
    - Assert correct `InternalErrorCode` returned for each case
    - Cover: auth, unknown_model, rate_limit, other, network, timeout for all three providers
    - Test 10-second timeout: mock httpx client that hangs → assert `{ error: "timeout" }`
    - Test network failure: mock httpx client that raises `httpx.ConnectError` → assert `{ error: "network" }`
    - _Requirements: R15.1, R16.1, R17.1, R18.1, R19.1, R20.1_

- [ ] 7. Implement `POST /api/ping` route
  - [ ] 7.1 Implement the ping endpoint
    - Create `backend/routers/ping.py` and register in `main.py`
    - Accept request body matching `PingRequest` Pydantic model: `{ provider, model? }`; read key from `request.state.provider_key` (set by HeaderRedactionMiddleware)
    - Guard: if `provider` missing → return `400 { "error": "missing_provider", "message": "Provider must be selected" }` without calling ProviderAdapter
    - Guard: if key is empty string → return `400 { "error": "missing_key", "message": "API key must be provided" }` without calling ProviderAdapter
    - Apply per-provider default models when `model` is absent or empty string:
      - OpenAI → `gpt-4o-mini`
      - Anthropic → `claude-haiku-4-5` (Revisions v2 item 5 gives `claude-haiku-4-5-20251001` as default; use whichever value is confirmed by provider-verification-notes.md from task 1)
      - Gemini → `gemini-3.5-flash-lite`
    - Call `ProviderAdapter.ping()` with the resolved model
    - On `ProviderSuccess`: return `200 { "status": "ok", "model": "<resolved-model-id>" }`
    - On `ProviderError`: map error codes to HTTP status per the error table in design.md: `auth/unknown_model/rate_limit/other/missing_provider/missing_key → 400`, `network → 502`, `timeout → 504`
    - Return `PingResponse` or `PingErrorResponse` Pydantic models
    - _Requirements: R5.1, R5.2, R5.3, R7.1, R13.1, R13.2, R14.1, R14.2, R15.1, R16.1, R17.1, R18.1, R19.1, R20.1_
  - [ ]* 7.2 Write integration tests for the ping endpoint (mocked provider responses)
    - For each provider: mock the provider HTTP endpoint and exercise the full path from `POST /api/ping` through ProviderAdapter to the normalised response
    - Cover: success, auth error, unknown model, rate-limit, generic error, network failure, timeout
    - Assert `model` field in success response equals the resolved model ID (default applied when client sent empty string)
    - _Requirements: R5.1, R5.2, R5.3, R7.1_

- [ ] 8. Implement `ThrottleMiddleware`
  - [ ] 8.1 Implement the middleware
    - Create `backend/middleware/throttle.py`
    - Implement the two-bucket in-memory throttle exactly as specified in design.md ThrottleMiddleware section:
      - IP bucket: 20 qualifying failures in a rolling 15-minute window → 5-minute cooldown
      - Session-token bucket: 5 consecutive qualifying failures → 5-minute cooldown
      - Only `auth` and `unknown_model` increment either counter; `timeout`, `network`, `rate_limit`, and `other` do not
      - `Retry-After` = max of both buckets' remaining times when blocked
    - Implement real-IP extraction per design.md Revisions v2 item 2: read the rightmost entry of `X-Forwarded-For` (the address appended by Render's proxy); fall back to `request.client.host` if the header is absent — **do not use `ProxyHeadersMiddleware(trusted_hosts="*")`**
    - Also throttle `POST /api/session-token`: max 30 IP requests per 15-minute window; return 429 with `Retry-After: 60` when exceeded
    - Document in code the known v1 limitation: counters reset on server restart (single worker, no Redis)
    - Register after `HeaderRedactionMiddleware` in `main.py` so the key is already stripped before throttle logic runs
    - Return `429 { "error": "throttle", "message": "Too many failed attempts. Try again later." }` with `Retry-After` header when blocked
    - When a request is blocked by the session-token bucket but not the IP bucket (or vice versa), `Retry-After` is the max across whichever buckets are active
    - _Requirements: R12.1, R12.2, R12.3, R12.4, R12.5_
  - [ ]* 8.2 Write unit tests for ThrottleMiddleware
    - Test IP bucket: N qualifying failures within window → cooldown triggered; N−1 failures → not triggered
    - Test session-token bucket: 5 consecutive qualifying failures → cooldown triggered; success resets counter
    - Test that `timeout`, `network`, `rate_limit`, `other` failures do NOT increment any counter
    - Test `Retry-After` = max of both buckets' remaining times when both active
    - Test `/api/session-token` IP throttle: 31st request within 15-minute window returns 429
    - Test P5 (cooldown timing) using a mock clock
    - _Requirements: R12.1, R12.2, R12.3, R12.4, R12.5_

- [ ] 9. Configure CORS
  - Add `CORSMiddleware` in `main.py` per the CORS Configuration section of design.md
  - `allow_origins`: `["https://<actual-vercel-url>", "http://localhost:5173"]` — replace the placeholder with the real Vercel URL from task 3.2
  - `allow_methods`: `["GET", "POST"]`
  - `allow_headers`: `["X-Provider-Key", "X-Session-Token", "Content-Type"]`
  - `allow_credentials=False`
  - Add an environment variable (`ALLOWED_ORIGIN_PROD`) so the Vercel URL can be set at deploy time without code changes
  - Note: do not proxy via Vercel rewrites; the frontend calls the backend directly via `VITE_API_BASE_URL` (Revisions v2 item 3)
  - _Requirements: R8.7, R8.8 (CORS headers restrict which origins can send `X-Provider-Key`)_

---

### Group 4 — Frontend Key Handling

- [ ] 10. Implement `ValidationStateManager`
  - [ ] 10.1 Implement the full state container
    - Create `frontend/src/state/ValidationStateManager.ts`
    - Implement the full `ClientState` interface and `IValidationStateManager` interface from design.md (Components and Interfaces section)
    - Implement all state transitions from the State Transitions table in design.md (State Model section):
      - Page load with no sessionStorage → defaults
      - Page load with sessionStorage present → restore `validatedKey` and `sessionToken`; reset `cooldown` to `{ active: false, remainingSeconds: 0 }` (cooldown not persisted across refreshes)
      - `setPendingInput`: if `validatedKey` present → trigger handoff stub; else set `pendingInput` and `modalState: 'open'`
      - `submitKeyForValidation`: transition `modalState` to `'validating'`; call `pingProvider()`
      - `onValidationSuccess`: write `validatedKey` to `sessionStorage['validated_key']` (JSON); set `modalState: 'closed'`; trigger handoff
      - `onValidationFailure`: keep `validatedKey` unchanged (P3); set `modalState: 'open'`; update `inlineError`; if error is `throttle`, set `cooldown` from `retryAfterSeconds`
      - `dismissKeyModal`: set `modalState: 'closed'`; leave `pendingInput` unchanged (P6, R23.1)
      - `invalidateKeyOnAuthError`: clear `sessionStorage['validated_key']`; set `validatedKey: null`; set `pendingInput`; set `modalState: 'open'` (R21)
      - Cooldown countdown: use `setInterval` to decrement `cooldown.remainingSeconds` each second; on reaching 0 set `cooldown.active: false`
    - Persist only `validated_key` and `session_token` to `sessionStorage`; nothing to `localStorage` or cookies
    - Export as a React context + hook (`useValidationState`) for use by all components
    - _Requirements: R2.1, R2.2, R2.3, R5.3, R5.4, R8.1, R8.2, R8.3, R8.4, R8.5, R8.6, R9.1, R12.1, R12.2, R12.3, R12.4, R21.1, R21.2, R21.3, R23.1, R23.2_
  - [ ]* 10.2 Write unit tests for ValidationStateManager
    - Test every row in the State Transitions table using a mock sessionStorage (jsdom or manual stub)
    - Parameterise over all `PingErrorCode` values for `onValidationFailure` — assert `validatedKey` is unchanged after each (P3)
    - Test P1: `setPendingInput` with `validatedKey: null` must not call `IMode.receive()` — only opens modal
    - Test P2: `submitKeyForValidation` with missing provider or empty key must not call fetch
    - Test P6: `dismissKeyModal` must leave `pendingInput` deep-equal to pre-dismiss value
    - Test P8: after any call to `onValidationSuccess` or `onValidationFailure`, `modalState ∈ { 'closed', 'open' }` (never `'validating'`)
    - Test cooldown countdown: simulate timer ticks; assert `remainingSeconds` decrements and `active` becomes `false` at 0
    - _Requirements: R2.2, R2.3, R5.3, R9.1, R12.2, R12.3, R12.4, R23.1, R23.2_

- [ ] 11. Implement `SessionTokenManager`
  - [ ] 11.1 Implement the session token fetch and lifecycle
    - Create `frontend/src/state/SessionTokenManager.ts`
    - Implement `ISessionTokenManager` interface from design.md (Components and Interfaces section)
    - On `EntryScreen` mount: call `ensureSessionToken()` non-blocking (do not await at mount time) — this also warms the backend server (design.md Cold-Start Mitigation section)
    - If no response within 2 seconds, transition `serverWakeState` to `'waking'` via `ValidationStateManager.setServerWakeState()`
    - On response: store token in `sessionStorage['session_token']`; call `ValidationStateManager.setSessionToken(token)`; set `serverWakeState: 'ready'`
    - On page refresh within same tab: read existing token from `sessionStorage` without a network call
    - `ensureSessionToken()`: if token already in sessionStorage → return immediately; if in-flight → await the same promise; if not started → start and return
    - If the session token has not resolved when the user presses "Save key": both the token wait and the ping share the single 20-second `AbortController` deadline (Revisions v2 item 4). If still unavailable, use `"anon:{ip}"` as fallback — but because client does not know the IP, fall back to the literal string `"anonymous"` (Revisions v2 item 4 uses `anon:{ip}` server-side; the client sends `"anonymous"` as the `X-Session-Token` value)
    - Call backend at `${VITE_API_BASE_URL}/api/session-token`
    - _Requirements: R12.1 (session token feeds throttle secondary key)_

- [ ] 12. Implement `KeyModal` component
  - [ ] 12.1 Implement the modal structure and form fields
    - Create `frontend/src/components/KeyModal.tsx`
    - Render only when `modalState !== 'closed'` (driven by `useValidationState`)
    - Provider selector: dropdown with options "OpenAI", "Anthropic", "Gemini"; no default selection (R3.2); on change → clear Key Field value (R4.1) and clear any `inlineError`
    - Key Field: `<input type="password">` (masked by default); show/hide toggle that switches between `type="password"` and `type="text"` (R3.4)
    - Model Field: `<input type="text">` optional free-text (R3.5); placeholder text indicating it is optional
    - "Save key" button (R3.6)
    - Inline error display area: renders a distinct message for each `PingErrorCode` (see below)
    - Loading indicator: visible when `modalState === 'validating'` (R6.1)
    - Disclosure statement verbatim: "Your key is held in this tab only and is never stored on our servers or written to logs." (R3.7)
    - Dismiss/close control: calls `dismissKeyModal()` — preserves `pendingInput`, no generation (R23.1, R23.2)
    - _Requirements: R3.1, R3.2, R3.3, R3.4, R3.5, R3.6, R3.7, R4.1_
  - [ ] 12.2 Implement client-side validation and ping call
    - On "Save key" press:
      - If no provider selected → set `inlineError: 'missing_provider'`; do not call fetch (R13.1, R13.2)
      - If Key Field empty → set `inlineError: 'missing_key'`; do not call fetch (R14.1, R14.2)
      - Otherwise: call `ValidationStateManager.submitKeyForValidation(provider, key, model)`
    - Disable "Save key" button when `modalState === 'validating'` (R6.2) OR when `cooldown.active === true` (R12.2)
    - When `cooldown.active`, display `cooldown.remainingSeconds` as a visible countdown (R12.3)
    - Implement `pingProvider()` with a single 20-second `AbortController` abort (Revisions v2 item 4):
      - `POST ${VITE_API_BASE_URL}/api/ping` with `X-Provider-Key`, `X-Session-Token` headers
      - On `AbortError` → treat as `{ error: "timeout" }` (design.md Cold-Start Mitigation)
      - On fetch network error → treat as `{ error: "network" }`
      - On any non-success response → read `error` field from JSON body
    - Map all `PingErrorCode` values to distinct inline error messages:
      - `auth` → "API key is invalid or unauthorised." (R15.1)
      - `unknown_model` → "Model name not recognised by this provider." (distinct from auth/rate-limit — R16.1)
      - `rate_limit` → "Rate limit or quota exhausted. You can retry with the same key." (R17.1)
      - `other` → "An unexpected provider error occurred. You can retry." (R18.1)
      - `network` → "Could not reach the server. Check your connection and retry." (R19.1)
      - `timeout` → "Validation timed out. The server may be waking up — please retry." (R20.2)
      - `throttle` → "Too many failed attempts. Please wait [N] seconds before retrying." (R12.3)
      - `missing_provider` → "Please select a provider." (R13.1)
      - `missing_key` → "Please enter an API key." (R14.1)
    - On success: modal closes and handoff fires (driven by `ValidationStateManager`)
    - _Requirements: R5.1, R6.1, R6.2, R12.2, R12.3, R13.1, R13.2, R14.1, R14.2, R15.1, R15.2, R16.1, R16.2, R17.1, R17.2, R18.1, R18.2, R19.1, R19.2, R20.2, R20.3, R23.1, R23.2_

- [ ] 13. Implement `KeyStatusElement`
  - [ ] 13.1 Implement the persistent key status component
    - Create `frontend/src/components/KeyStatusElement.tsx`
    - Render at application root level in `frontend/src/App.tsx` — outside any route-specific subtrees so it is reachable from every screen (R10.1)
    - When `validatedKey === null`: display "No key added yet" (R10.2)
    - When `validatedKey` is set: display the provider display name ("OpenAI", "Anthropic", or "Gemini") (R10.3)
    - Always render an "Add / change key" control (button or link); on activation → call `openKeyModal()` (R11.1, R11.2)
    - When `serverWakeState === 'waking'`: display "Waking up the server…" status indicator (design.md Components → KeyStatusElement)
    - _Requirements: R10.1, R10.2, R10.3, R11.1, R11.2_

- [ ] 14. Wire handoff from Entry Screen to mode stubs
  - [ ] 14.1 Implement the handoff trigger and stub mode receiver
    - Create `frontend/src/modes/ModeStub.ts` implementing the `IMode` interface from design.md (Handoff Interface section)
    - `receive(context: HandoffContext)`: logs `pendingInput` and `validatedKey.provider` to the browser console (story mode and Q&A mode are out of scope)
    - Wire `ValidationStateManager.onValidationSuccess` to call `ModeStub.receive({ pendingInput, validatedKey })` after closing the modal (R5.4)
    - Wire `ValidationStateManager.setPendingInput`: when `validatedKey` is already present, call `ModeStub.receive()` immediately without opening the modal (R1.3)
    - Implement real-request auth error handling in `EntryScreen`: when a mode returns an auth error, call `ValidationStateManager.invalidateKeyOnAuthError(pendingInput)` which clears `validatedKey`, sets `pendingInput`, and opens the modal (R21.1, R21.2, R21.3)
    - Implement real-request rate-limit error display in `EntryScreen`: render inline error with "Retry" button (resubmits with existing `validatedKey`) and "Add / change key" button (opens modal) (R22.1, R22.2, R22.3)
    - _Requirements: R1.3, R2.3, R5.3, R5.4, R21.1, R21.2, R21.3, R22.1, R22.2, R22.3_

---

### Group 5 — Tests

- [ ] 15. **(Required)** Write key-redaction integration test
  - [ ] 15.1 Write the log-redaction integration test for POST /api/ping
    - Create `backend/tests/test_header_redaction_integration.py`
    - Implement a test that:
      1. Sends `POST /api/ping` with a known sentinel key value (e.g. `"TEST-KEY-SENTINEL-abc123"`) via the FastAPI test client
      2. Captures all log output produced during the full request-handling cycle (route handler + middleware chain) by attaching a log handler to the root Python logger before the request and removing it after
      3. Asserts that no captured log record's formatted message string-contains the sentinel key value
    - The test must exercise the full middleware stack (HeaderRedactionMiddleware applied) — not a unit test of the middleware alone
    - Use `pytest` with `caplog` or a custom log capture fixture
    - Satisfies Property 4 / R8.8
    - _Requirements: R8.8_

- [ ] 16. **(Required)** Write ProviderAdapter error-normalisation unit tests
  - [ ] 16.1 Write error-normalisation tests for OpenAI
    - Create `backend/tests/test_provider_adapter.py`
    - Mock `httpx.AsyncClient.post` to return controlled responses
    - For OpenAI: test every row in the Provider Error Normalisation → OpenAI table from design.md
      - `401 invalid_api_key` → `auth`
      - `401 no_api_key` → `auth`
      - `404 model_not_found` → `unknown_model`
      - `400 invalid_request_error` with model name in message → `unknown_model`
      - `429 rate_limit_exceeded` → `rate_limit`
      - `429 insufficient_quota` → `rate_limit`
      - `500` (any) → `other`
      - Network error (`httpx.ConnectError`) → `network`
      - Timeout (mock httpx timeout exception) → `timeout`
    - _Requirements: R15.1, R16.1, R17.1, R18.1, R19.1, R20.1_
  - [ ] 16.2 Write error-normalisation tests for Anthropic
    - Continuing in `backend/tests/test_provider_adapter.py`
    - For Anthropic: test every row in the Provider Error Normalisation → Anthropic table
      - `401 authentication_error` → `auth`
      - `403 permission_error` → `auth`
      - `404 not_found_error` → `unknown_model`
      - `429 rate_limit_error` → `rate_limit`
      - `529 overloaded_error` → `other`
      - `500 api_error` → `other`
      - Network error → `network`
      - Timeout → `timeout`
    - _Requirements: R15.1, R16.1, R17.1, R18.1, R19.1, R20.1_
  - [ ] 16.3 Write error-normalisation tests for Gemini
    - Continuing in `backend/tests/test_provider_adapter.py`
    - For Gemini: test every row in the Provider Error Normalisation → Gemini table
      - `400 API_KEY_INVALID` → `auth`
      - `403 PERMISSION_DENIED` → `auth`
      - `404 NOT_FOUND` → `unknown_model`
      - `429 RESOURCE_EXHAUSTED` → `rate_limit`
      - `500` (any) → `other`
      - Network error → `network`
      - Timeout → `timeout`
    - Also assert that the Gemini ping request sends the API key as the `x-goog-api-key` header and never includes it in the request URL (Revisions v2 item 1)
    - _Requirements: R15.1, R16.1, R17.1, R18.1, R19.1, R20.1_

- [ ] 17. **(Optional)** Write ValidationStateManager unit tests
  - [ ] 17.1 Write comprehensive state-transition and property tests
    - Create `frontend/src/state/__tests__/ValidationStateManager.test.ts` (using Vitest or Jest + jsdom)
    - Test every row in the State Transitions table from design.md State Model section
    - Parameterise `onValidationFailure` over all `PingErrorCode` values; assert `validatedKey` is reference-identical before and after (P3)
    - Test P1: `setPendingInput` with `validatedKey: null` never calls `IMode.receive()` — uses fast-check arbitrary `PendingInput` inputs
    - Test P2: `submitKeyForValidation` with undefined provider or empty key string never calls `fetch` — uses fast-check
    - Test P6: `dismissKeyModal` with any `PendingInput` variant; assert `pendingInput` deep-equal after dismiss and `modalState === 'closed'` — uses fast-check
    - Test P8: after every possible `onValidationSuccess`/`onValidationFailure`/`dismissKeyModal` call, assert `modalState ∈ { 'closed', 'open' }` — uses fast-check
    - Test cooldown countdown: simulate `setInterval` ticks using fake timers; assert `remainingSeconds` decrements and `cooldown.active` becomes `false` at 0 (P5)
    - Use a mock `sessionStorage` (in-memory object)
    - _Requirements: R2.2, R2.3, R5.3, R9.1, R12.2, R12.3, R12.4, R23.1, R23.2_

- [ ] 18. **(Optional)** Write ThrottleMiddleware unit tests
  - [ ] 18.1 Write comprehensive throttle logic tests
    - Create `backend/tests/test_throttle_middleware.py`
    - Test IP bucket: exactly `IP_FAILURE_THRESHOLD` qualifying failures within window → cooldown triggered on next request; `IP_FAILURE_THRESHOLD − 1` → not triggered
    - Test session-token bucket: 5 consecutive qualifying failures → cooldown triggered; a success resets the consecutive counter
    - Test that `timeout`, `network`, `rate_limit`, and `other` error codes do NOT increment the IP or session-token bucket
    - Test that `auth` and `unknown_model` DO increment both buckets
    - Test `Retry-After` value: when both buckets are in cooldown, assert `Retry-After = max(ip_remaining, session_remaining)`
    - Test `/api/session-token` throttle: 31st request from the same IP within a 15-minute window returns 429
    - Test rolling window expiry: failures older than 15 minutes do not count toward the IP threshold
    - Use a mock clock (`freezegun` or equivalent) for time-dependent assertions (P5)
    - _Requirements: R12.1, R12.2, R12.3, R12.4, R12.5_

- [ ] 19. **(Optional)** Write E2E tests
  - [ ] 19.1 Write Playwright E2E tests for key flows
    - Create `e2e/tests/entry_screen.spec.ts` using Playwright against a fully running stack (FastAPI backend + Vite frontend) with provider endpoints mocked at the network level
    - **Happy path**: Load app → select path → enter request → submit → Key Modal opens (R2.1) → enter provider/key/model → press Save key → validation succeeds → Key Modal closes → handoff stub logs context to console → assert console output contains `pendingInput` and provider name
    - **Page-refresh key survival**: Complete validation → confirm `sessionStorage['validated_key']` is set → reload page → assert `validatedKey` is restored → submit a request → assert Key Modal does NOT open (handoff fires immediately) (R8.2)
    - **Modal dismiss preserves pending input**: Submit request (no Validated Key) → Key Modal opens → dismiss without saving → assert original request input is still present in the UI (R23.1)
    - **Rate-limit inline error**: Mock provider to return 429 rate-limit on a real request → assert inline error appears on the current screen with "Retry" and "Add / change key" options visible (R22.1, R22.2, R22.3)
    - _Requirements: R1.1, R1.3, R2.1, R2.2, R8.2, R22.1, R22.2, R22.3, R23.1_

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Tasks 15 and 16 are **required** tests; tasks 17–19 are **optional**
- Tasks 1–14 are all required implementation tasks
- Task 1 is a research/documentation task, not a coding task — run it first
- Each task references specific requirements (R-numbers) from requirements.md for traceability
- Revisions v2 in design.md is authoritative wherever it conflicts with earlier sections: Gemini key goes in `x-goog-api-key` header (not URL), do not use `ProxyHeadersMiddleware(trusted_hosts="*")`, use direct `VITE_API_BASE_URL` (no Vercel rewrites), single uvicorn worker, Anthropic default model is `claude-haiku-4-5-20251001`
- Provider details (default model IDs especially) should be confirmed via task 1 before task 7 is finalised
- The story mode and Q&A mode internals are out of scope; task 14 uses a console-log stub as the handoff receiver

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "4.1"] },
    { "id": 3, "tasks": ["4.2", "5.1", "10.1"] },
    { "id": 4, "tasks": ["5.2", "6.1", "6.2", "6.3", "11.1"] },
    { "id": 5, "tasks": ["6.4", "7.1", "12.1"] },
    { "id": 6, "tasks": ["7.2", "8.1", "12.2"] },
    { "id": 7, "tasks": ["8.2", "9", "13.1"] },
    { "id": 8, "tasks": ["14.1"] },
    { "id": 9, "tasks": ["15.1", "16.1", "16.2", "16.3", "10.2"] },
    { "id": 10, "tasks": ["17.1", "18.1"] },
    { "id": 11, "tasks": ["19.1"] }
  ]
}
```

## Task amendments (authoritative: supersede the tasks above where they conflict)

- Task 9 (CORS): add `expose_headers=["Retry-After"]`. Add CORSMiddleware
  LAST in main.py so it is the outermost layer (Starlette runs the
  last-added middleware first) and so 429 responses carry CORS headers.
- Task 8.1: if the X-Session-Token header is missing or empty, the session
  bucket key is `anon:{ip}`.
- Task 11.1: replace the "anonymous" fallback. If no token has resolved when
  the ping is sent, omit the X-Session-Token header entirely.
- Tasks 2.2 and 3.2 are manual steps done by the developer, not by the coding
  agent. Do not skip them. Required environment variables:
  SESSION_TOKEN_SECRET and ALLOWED_ORIGIN_PROD (Render),
  VITE_API_BASE_URL (Vercel).
- New manual task 8.3 (after the backend is deployed): send a request to
  /api/ping with a fake `X-Forwarded-For: 1.2.3.4` header and confirm the
  throttle keys on the real client IP, not the forged value. Record the
  result in docs/provider-verification-notes.md.
- Task 7.1: set `request.state.ping_error_code` in the route handler, not
  inside the provider adapters (the adapters never see the request object).