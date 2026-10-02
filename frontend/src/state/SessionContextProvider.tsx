import { createContext, useCallback, useContext, useState } from "react";
import type { ReactNode } from "react";
import type { AskExchange } from "../api/client";

/**
 * design.md "Conversation memory (in the browser only)": the last few
 * Q&A exchanges, kept in the tab for the life of the Session (qna-mode
 * Requirement 8).
 *
 * Backed by sessionStorage rather than plain useState so it also
 * survives a same-tab page refresh, the same pattern already used for
 * the Validated Key - and, like sessionStorage generally, it disappears
 * on tab close without any extra code (Requirement 8.2/8.3: cleared on
 * tab close, never kept across Sessions).
 */
const MAX_RECENT_EXCHANGES = 3; // design.md: "the last three, to start"

const EXCHANGES_KEY = "recent_exchanges";

function loadJson<T>(key: string, fallback: T): T {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function saveJson(key: string, value: unknown) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // sessionStorage unavailable - context just won't survive a
    // refresh; not fatal for the current render.
  }
}

interface SessionContextValue {
  recentExchanges: AskExchange[];
  addExchange: (exchange: AskExchange) => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionContextProvider({ children }: { children: ReactNode }) {
  const [recentExchanges, setRecentExchanges] = useState<AskExchange[]>(() =>
    loadJson(EXCHANGES_KEY, [])
  );

  const addExchange = useCallback((exchange: AskExchange) => {
    setRecentExchanges((prev) => {
      const next = [...prev, exchange].slice(-MAX_RECENT_EXCHANGES);
      saveJson(EXCHANGES_KEY, next);
      return next;
    });
  }, []);

  return (
    <SessionContext.Provider value={{ recentExchanges, addExchange }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSessionContext(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSessionContext must be used within a SessionContextProvider");
  return ctx;
}
