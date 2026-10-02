import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { ApiError, Provider, ValidatedKeyLike } from "../api/client";
import { ping } from "../api/client";

export interface PendingInput {
  text: string;
}

/** A key became available for this input - `nonce` lets QnAScreen tell
 * a fresh request apart from the same input object lingering in
 * state, since a plain object-identity check wouldn't change if the
 * same question were resubmitted twice. */
export interface RunRequest {
  nonce: number;
  input: PendingInput;
}

export interface CooldownState {
  active: boolean;
  remainingSeconds: number;
}

interface ValidationState {
  pendingInput: PendingInput | null;
  validatedKey: ValidatedKeyLike | null;
  modalState: "closed" | "open" | "validating";
  inlineError: ApiError | null;
  cooldown: CooldownState;
}

const STORAGE_KEY = "validated_key";

function loadValidatedKey(): ValidatedKeyLike | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as ValidatedKeyLike) : null;
  } catch {
    return null;
  }
}

function saveValidatedKey(key: ValidatedKeyLike | null) {
  try {
    if (key) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(key));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // sessionStorage unavailable (private mode, etc.) - the tab just
    // won't survive a refresh; not fatal for the current session.
  }
}

interface ValidationContextValue extends ValidationState {
  /** R1.3/R2.1: if a Validated Key already exists, fires the handoff
   * immediately via onReady; otherwise opens the Key Modal and queues
   * the input for after validation succeeds. */
  setPendingInput: (input: PendingInput) => void;
  submitKeyForValidation: (provider: Provider, key: string, model: string) => Promise<void>;
  dismissKeyModal: () => void;
  openKeyModal: () => void;
  /** R21: a real /api/ask or /api/story call came back with an auth
   * error - the key that seemed valid at /api/ping time no longer is. */
  invalidateKeyOnAuthError: (pendingInput: PendingInput) => void;
  clearInlineError: () => void;
}

const ValidationContext = createContext<ValidationContextValue | null>(null);

export function ValidationStateProvider({
  onReady,
  children,
}: {
  /** Called once a Validated Key is available for a given pending
   * input - either immediately (key already validated) or right after
   * the Key Modal succeeds (R5.4). This is the "handoff" the
   * entry-screen spec describes; here it navigates to the right
   * screen instead of logging to the console. */
  onReady: (input: PendingInput, key: ValidatedKeyLike) => void;
  children: ReactNode;
}) {
  const [pendingInput, setPendingInputState] = useState<PendingInput | null>(null);
  const [validatedKey, setValidatedKey] = useState<ValidatedKeyLike | null>(loadValidatedKey);
  const [modalState, setModalState] = useState<"closed" | "open" | "validating">("closed");
  const [inlineError, setInlineError] = useState<ApiError | null>(null);
  const [cooldown, setCooldown] = useState<CooldownState>({ active: false, remainingSeconds: 0 });
  const abortRef = useRef<AbortController | null>(null);

  // Cooldown countdown (design.md: setInterval, decrement each second).
  useEffect(() => {
    if (!cooldown.active) return;
    const id = setInterval(() => {
      setCooldown((c) => {
        if (c.remainingSeconds <= 1) return { active: false, remainingSeconds: 0 };
        return { active: true, remainingSeconds: c.remainingSeconds - 1 };
      });
    }, 1000);
    return () => clearInterval(id);
  }, [cooldown.active]);

  const setPendingInput = useCallback(
    (input: PendingInput) => {
      setPendingInputState(input);
      if (validatedKey) {
        onReady(input, validatedKey);
      } else {
        setModalState("open");
      }
    },
    [validatedKey, onReady]
  );

  const openKeyModal = useCallback(() => setModalState("open"), []);

  const dismissKeyModal = useCallback(() => {
    // P6/R23.1: dismissing never clears pendingInput - the user's typed
    // request is still there if they reopen the modal later.
    setModalState("closed");
    setInlineError(null);
  }, []);

  const clearInlineError = useCallback(() => setInlineError(null), []);

  const submitKeyForValidation = useCallback(
    async (provider: Provider, key: string, model: string) => {
      if (!provider) {
        setInlineError({ kind: "missing_provider", message: "Please select a provider." });
        return;
      }
      if (!key) {
        setInlineError({ kind: "missing_key", message: "Please enter an API key." });
        return;
      }

      setModalState("validating");
      setInlineError(null);

      const controller = new AbortController();
      abortRef.current = controller;
      const timeoutId = setTimeout(() => controller.abort(), 20000);

      const sessionToken = sessionStorage.getItem("session_token") ?? undefined;
      const result = await ping(provider, key, model, sessionToken, controller.signal);
      clearTimeout(timeoutId);

      if (result.ok) {
        const validated: ValidatedKeyLike = { provider, key, model: result.data.model };
        setValidatedKey(validated);
        saveValidatedKey(validated);
        setModalState("closed");
        setCooldown({ active: false, remainingSeconds: 0 });
        if (pendingInput) onReady(pendingInput, validated);
      } else {
        // P3: a failed validation never touches the existing validatedKey.
        setModalState("open");
        setInlineError(result.error);
        if (result.error.kind === "throttle" && result.error.retryAfterSeconds) {
          setCooldown({ active: true, remainingSeconds: result.error.retryAfterSeconds });
        }
      }
    },
    [pendingInput, onReady]
  );

  const invalidateKeyOnAuthError = useCallback((input: PendingInput) => {
    setValidatedKey(null);
    saveValidatedKey(null);
    setPendingInputState(input);
    setModalState("open");
    setInlineError({ kind: "auth", message: "This key was rejected. Please add a valid key." });
  }, []);

  const value: ValidationContextValue = {
    pendingInput,
    validatedKey,
    modalState,
    inlineError,
    cooldown,
    setPendingInput,
    submitKeyForValidation,
    dismissKeyModal,
    openKeyModal,
    invalidateKeyOnAuthError,
    clearInlineError,
  };

  return <ValidationContext.Provider value={value}>{children}</ValidationContext.Provider>;
}

export function useValidationState(): ValidationContextValue {
  const ctx = useContext(ValidationContext);
  if (!ctx) throw new Error("useValidationState must be used within a ValidationStateProvider");
  return ctx;
}
