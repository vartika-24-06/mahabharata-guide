/**
 * Thin fetch wrapper for the backend, matching the header/error contract
 * every backend endpoint follows (entry-screen design.md's /api/ping
 * contract, reused as-is by /api/ask - see backend/qna_endpoint.py's
 * module docstring): X-Provider-Key / X-Session-Token headers, and a
 * failure body of {"error": <kind>, "message": string}.
 */

export type Provider = "openai" | "anthropic" | "gemini";

export type PingErrorCode =
  | "auth"
  | "unknown_model"
  | "rate_limit"
  | "other"
  | "network"
  | "timeout"
  | "throttle"
  | "missing_provider"
  | "missing_key";

export interface ApiError {
  kind: PingErrorCode;
  message: string;
  retryAfterSeconds?: number;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

function isApiErrorBody(value: unknown): value is { error: string; message: string } {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    "message" in value
  );
}

/**
 * POSTs to the backend with the visitor's key/session-token headers
 * attached (when present), and normalizes every failure mode - a
 * {"error", "message"} body, a network failure, or a client-side abort -
 * into one ApiError shape. Never throws; callers branch on the
 * `ok` flag.
 */
export async function apiPost<TResponse>(
  path: string,
  body: unknown,
  opts: { providerKey?: string; sessionToken?: string; signal?: AbortSignal } = {}
): Promise<{ ok: true; data: TResponse } | { ok: false; error: ApiError }> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (opts.providerKey) headers["X-Provider-Key"] = opts.providerKey;
  if (opts.sessionToken) headers["X-Session-Token"] = opts.sessionToken;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      return { ok: false, error: { kind: "timeout", message: "The request timed out." } };
    }
    return { ok: false, error: { kind: "network", message: "Could not reach the server." } };
  }

  let json: unknown = null;
  try {
    json = await response.json();
  } catch {
    // Non-JSON body (shouldn't happen against this backend) - fall
    // through to a generic error below.
  }

  if (response.ok) {
    return { ok: true, data: json as TResponse };
  }

  const retryAfterHeader = response.headers.get("Retry-After");
  const retryAfterSeconds = retryAfterHeader ? parseInt(retryAfterHeader, 10) : undefined;

  if (isApiErrorBody(json)) {
    return {
      ok: false,
      error: { kind: json.error as PingErrorCode, message: json.message, retryAfterSeconds },
    };
  }
  return {
    ok: false,
    error: { kind: "other", message: `Request failed (${response.status}).`, retryAfterSeconds },
  };
}

// --- /api/session-token ---

export async function fetchSessionToken(): Promise<string | null> {
  const result = await apiPost<{ session_token: string }>("/api/session-token", {});
  return result.ok ? result.data.session_token : null;
}

// --- /api/ping ---

export interface PingResponse {
  status: "ok";
  model: string;
}

export function ping(
  provider: Provider,
  key: string,
  model: string,
  sessionToken: string | undefined,
  signal: AbortSignal
) {
  return apiPost<PingResponse>(
    "/api/ping",
    { provider, model },
    { providerKey: key, sessionToken, signal }
  );
}

// --- /api/ask (Task 13 / qna-mode) ---

export interface Citation {
  parva_name: string;
  section: number;
  excerpt: string;
}

export type AskResponse =
  | { type: "decline"; message: string }
  | { type: "no_answer"; message: string; suggestions: string[] }
  | { type: "factual" | "philosophical"; answer: string; citations: Citation[]; expanded?: boolean }
  | {
      type: "ambiguous";
      factual_sentence: string;
      factual_citations: Citation[];
      philosophical_sentence: string;
      philosophical_citations: Citation[];
    };

export interface AskExchange {
  question: string;
  type?: string;
}

export function askQuestion(
  key: ValidatedKeyLike,
  sessionToken: string | undefined,
  args: {
    question: string;
    expand?: boolean;
    label?: string;
    context?: AskExchange[];
  }
) {
  return apiPost<AskResponse>(
    "/api/ask",
    {
      provider: key.provider,
      model: key.model,
      question: args.question,
      expand: args.expand ?? false,
      label: args.label,
      context: args.context,
    },
    { providerKey: key.key, sessionToken }
  );
}

export interface ValidatedKeyLike {
  provider: Provider;
  key: string;
  model: string;
}

// --- /api/feedback (UX item 7) ---

export type FeedbackRating = "up" | "down";

export function submitFeedback(args: {
  question: string;
  answerType: string;
  answerText: string;
  citations: Citation[];
  rating: FeedbackRating;
  provider?: Provider;
  model?: string;
}) {
  return apiPost<{ status: "ok" }>("/api/feedback", {
    question: args.question,
    answer_type: args.answerType,
    answer_text: args.answerText,
    citations: args.citations,
    rating: args.rating,
    provider: args.provider,
    model: args.model,
  });
}
