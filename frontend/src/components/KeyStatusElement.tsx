import { useValidationState } from "../state/ValidationStateContext";

const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  gemini: "Gemini",
};

/** Entry-screen tasks.md Task 13: rendered at the app root, outside any
 * screen-specific subtree, so it's reachable everywhere. */
export function KeyStatusElement({ serverWakeState }: { serverWakeState: "unknown" | "waking" | "ready" }) {
  const { validatedKey, openKeyModal } = useValidationState();

  return (
    <div className="key-status">
      <span>
        {validatedKey ? PROVIDER_LABELS[validatedKey.provider] : "No key added yet"}
      </span>
      {serverWakeState === "waking" && <span className="waking">Waking up the server…</span>}
      <button type="button" className="link-button" onClick={openKeyModal}>
        Add / change key
      </button>
    </div>
  );
}
