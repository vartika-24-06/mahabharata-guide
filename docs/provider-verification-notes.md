# Provider Verification Notes

This document captures verified provider details, parameter names, error codes, and default models for OpenAI, Anthropic, and Gemini, per the requirements and design specifications (including Revisions v2 and Revisions v3 overrides).

---

## Summary of Provider Configurations

| Provider  | Default Model ID          | API Header / Auth Mechanism           | Token Limit Parameter            | Minimum Ping Token Value | Unknown Model Error Response                        | Invalid API Key Error Response                         |
|-----------|---------------------------|---------------------------------------|----------------------------------|--------------------------|-----------------------------------------------------|--------------------------------------------------------|
| **OpenAI** | `gpt-4o-mini`             | `Authorization: Bearer <key>`         | `max_completion_tokens: 16`      | 16 tokens                | HTTP 404 (`model_not_found`) or HTTP 400            | HTTP 401 (`invalid_api_key` / `no_api_key`)            |
| **Anthropic** | `claude-haiku-4-5-20251001` | `x-api-key: <key>` + `anthropic-version: 2023-06-01` | `max_tokens: 16`                 | 16 tokens (required)     | HTTP 404 (`not_found_error`)                        | HTTP 401 (`authentication_error`) / 403 (`permission_error`) |
| **Gemini** | `gemini-3.5-flash-lite`   | `x-goog-api-key: <key>`               | `generationConfig.maxOutputTokens: 16` | 16 tokens           | HTTP 404 (`NOT_FOUND`)                              | HTTP 400 (`API_KEY_INVALID`) / 403 (`PERMISSION_DENIED`)    |

---

## Detailed Provider Analysis

### 1. OpenAI (Chat Completions API)
- **Endpoint**: `POST https://api.openai.com/v1/chat/completions`
- **Default Model**: `gpt-4o-mini`
- **Authentication**: `Authorization: Bearer <key>` header
- **Token Parameter**: `max_completion_tokens` (Value: `16`). `max_completion_tokens` is preferred over the deprecated `max_tokens` for the `gpt-4o` / `gpt-4o-mini` class of models.
- **Payload**:
  ```json
  {
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
    "max_completion_tokens": 16
  }
  ```
- **Error Normalisation**:
  - **Auth Error**: HTTP 401 with `error.code` equal to `invalid_api_key` or `no_api_key` → maps to `auth`.
  - **Unknown Model Error**: HTTP 404 with `error.code` equal to `model_not_found` (or HTTP 400 `invalid_request_error` mentioning model) → maps to `unknown_model`.
  - **Rate Limit / Quota**: HTTP 429 (`rate_limit_exceeded` or `insufficient_quota`) → maps to `rate_limit`.
  - **Server Error**: HTTP 5xx → maps to `other`.

---

### 2. Anthropic (Messages API)
- **Endpoint**: `POST https://api.anthropic.com/v1/messages`
- **Default Model**: `claude-haiku-4-5-20251001` (Fallback / alternative: `claude-3-5-haiku-20241022`)
- **Authentication**: `x-api-key: <key>` header (and `anthropic-version: 2023-06-01` header)
- **Token Parameter**: `max_tokens` (Value: `16`). `max_tokens` is a mandatory parameter in Anthropic's Messages API and must be a positive integer.
- **Payload**:
  ```json
  {
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 16,
    "messages": [{"role": "user", "content": "Reply with the single word: ok"}]
  }
  ```
- **Error Normalisation**:
  - **Auth Error**: HTTP 401 (`authentication_error`) or HTTP 403 (`permission_error`) → maps to `auth`.
  - **Unknown Model Error**: HTTP 404 (`not_found_error`) → maps to `unknown_model`.
  - **Rate Limit / Quota**: HTTP 429 (`rate_limit_error`) → maps to `rate_limit`.
  - **Server Error**: HTTP 529 (`overloaded_error`) or 500 (`api_error`) → maps to `other`.

---

### 3. Gemini (Native REST API)
- **Endpoint**: `POST https://generativelanguage.googleapis.com/v1beta/models/<model>:generateContent`
- **Default Model**: `gemini-3.5-flash-lite` (Fallback / alternative: `gemini-1.5-flash` or `gemini-2.0-flash`)
- **Authentication**: `x-goog-api-key: <key>` header (**CRITICAL**: Never pass the key as `?key=` query parameter in the URL to prevent API keys appearing in HTTP access logs).
- **Token Parameter**: `generationConfig.maxOutputTokens` (Value: `16`).
- **Payload**:
  ```json
  {
    "contents": [{"parts": [{"text": "Reply with the single word: ok"}]}],
    "generationConfig": {"maxOutputTokens": 16}
  }
  ```
- **Error Normalisation**:
  - **Auth Error**: HTTP 400 (`API_KEY_INVALID`) or HTTP 403 (`PERMISSION_DENIED`) → maps to `auth`.
  - **Unknown Model Error**: HTTP 404 (`NOT_FOUND`) → maps to `unknown_model`.
  - **Rate Limit / Quota**: HTTP 429 (`RESOURCE_EXHAUSTED`) → maps to `rate_limit`.
  - **Server Error**: HTTP 5xx → maps to `other`.

---

## Flags for Manual Verification Before Production Launch

1. **Gemini Model Availability**: Confirm whether `gemini-3.5-flash-lite` is active in GA for the user's target GCP region, or fallback to `gemini-1.5-flash` / `gemini-2.0-flash`.
2. **Anthropic Model Availability**: Confirm `claude-haiku-4-5-20251001` availability vs `claude-3-5-haiku-20241022` depending on account access tier.
3. **OpenAI `max_completion_tokens`**: Verify model provider behavior for legacy endpoints if a user inputs an older model (e.g. `gpt-3.5-turbo`) that expects `max_tokens` instead of `max_completion_tokens`.
