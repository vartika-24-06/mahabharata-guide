import { useEffect, useState } from "react";
import { fetchSessionToken } from "../api/client";

const STORAGE_KEY = "session_token";

/**
 * Entry-screen spec's SessionTokenManager: fetches a per-tab HMAC token
 * on mount (non-blocking - this call also warms a sleeping free-tier
 * backend), reuses whatever's already in sessionStorage on a same-tab
 * refresh, and tracks a "waking" state if the first response takes more
 * than 2 seconds (Render free-tier cold start).
 */
export function useSessionToken() {
  const [sessionToken, setSessionToken] = useState<string | null>(() => {
    try {
      return sessionStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  });
  const [serverWakeState, setServerWakeState] = useState<"unknown" | "waking" | "ready">(
    sessionToken ? "ready" : "unknown"
  );

  useEffect(() => {
    if (sessionToken) return; // already have one for this tab

    let cancelled = false;
    const wakingTimer = setTimeout(() => {
      if (!cancelled) setServerWakeState("waking");
    }, 2000);

    fetchSessionToken().then((token) => {
      clearTimeout(wakingTimer);
      if (cancelled) return;
      if (token) {
        try {
          sessionStorage.setItem(STORAGE_KEY, token);
        } catch {
          // Non-fatal - the token just won't survive a refresh.
        }
        setSessionToken(token);
      }
      setServerWakeState("ready");
    });

    return () => {
      cancelled = true;
      clearTimeout(wakingTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { sessionToken, serverWakeState };
}
