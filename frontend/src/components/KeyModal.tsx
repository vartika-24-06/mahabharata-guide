import { useState } from "react";
import type { FormEvent } from "react";
import type { PingErrorCode, Provider } from "../api/client";
import { useValidationState } from "../state/ValidationStateContext";

const PROVIDER_OPTIONS: { value: Provider; label: string }[] = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "gemini", label: "Gemini" },
];

// entry-screen tasks.md 12.2: one distinct message per PingErrorCode.
const ERROR_MESSAGES: Record<PingErrorCode, string> = {
  auth: "API key is invalid or unauthorised.",
  unknown_model: "Model name not recognised by this provider.",
  rate_limit: "Rate limit or quota exhausted. You can retry with the same key.",
  other: "An unexpected provider error occurred. You can retry.",
  network: "Could not reach the server. Check your connection and retry.",
  timeout: "Validation timed out. The server may be waking up - please retry.",
  throttle: "Too many failed attempts. Please wait before retrying.",
  missing_provider: "Please select a provider.",
  missing_key: "Please enter an API key.",
};

export function KeyModal() {
  const { modalState, inlineError, cooldown, submitKeyForValidation, dismissKeyModal } =
    useValidationState();
  const [provider, setProvider] = useState<Provider | "">("");
  const [key, setKey] = useState("");
  const [model, setModel] = useState("");
  const [showKey, setShowKey] = useState(false);

  if (modalState === "closed") return null;

  const isValidating = modalState === "validating";
  const saveDisabled = isValidating || cooldown.active;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (saveDisabled) return;
    submitKeyForValidation(provider as Provider, key, model.trim());
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Add API key">
      <div className="modal">
        <h2>Add your API key</h2>
        <form onSubmit={handleSubmit}>
          <label className="field">
            <span>Provider</span>
            <select
              value={provider}
              onChange={(e) => {
                setProvider(e.target.value as Provider);
                setKey("");
              }}
            >
              <option value="" disabled>
                Select a provider
              </option>
              {PROVIDER_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>API key</span>
            <div className="key-field-row">
              <input
                type={showKey ? "text" : "password"}
                value={key}
                onChange={(e) => setKey(e.target.value)}
                autoComplete="off"
              />
              <button type="button" onClick={() => setShowKey((s) => !s)}>
                {showKey ? "Hide" : "Show"}
              </button>
            </div>
          </label>

          <label className="field">
            <span>Model (optional)</span>
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="Leave blank to use the default model"
            />
          </label>

          {inlineError && (
            <p className="inline-error" role="alert">
              {ERROR_MESSAGES[inlineError.kind]}
              {inlineError.kind === "throttle" && cooldown.active
                ? ` (${cooldown.remainingSeconds}s)`
                : ""}
            </p>
          )}

          <p className="disclosure">
            Your key is held in this tab only and is never stored on our servers or written to
            logs.
          </p>

          <div className="modal-actions">
            <button type="button" onClick={dismissKeyModal} disabled={isValidating}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={saveDisabled}>
              {isValidating ? "Validating..." : "Save key"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
