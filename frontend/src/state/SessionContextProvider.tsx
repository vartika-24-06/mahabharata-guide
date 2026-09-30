import { createContext, useCallback, useContext, useState } from "react";
import type { ReactNode } from "react";
import type { AskExchange } from "../api/client";

/**
 * design.md "Conversation memory (in the browser only)": the last few
 * Q&A exchanges and the list of shown story episodes, kept in the tab
 * for the life of the Session (qna-mode Requirement 8 / story-mode
 * Requirement 8) - NOT per-screen component state, which would be
 * thrown away every time the user switches to the other mode and back
 * (both specs explicitly require the opposite: 8.4 in each spec says
 * switching modes and returning keeps this context).
 *
 * Backed by sessionStorage rather than plain useState so it also
 * survives a same-tab page refresh, the same pattern already used for
 * the Validated Key - and, like sessionStorage generally, it disappears
 * on tab close without any extra code (Requirement 8.2/8.3: cleared on
 * tab close, never kept across Sessions).
 */
const MAX_RECENT_EXCHANGES = 3; // design.md: "the last three, to start"

const EXCHANGES_KEY = "recent_exchanges";
const SHOWN_STORIES_KEY = "shown_stories";

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
  shownStories: string[];
  addShownStory: (storyId: string) => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionContextProvider({ children }: { children: ReactNode }) {
  const [recentExchanges, setRecentExchanges] = useState<AskExchange[]>(() =>
    loadJson(EXCHANGES_KEY, [])
  );
  const [shownStories, setShownStories] = useState<string[]>(() => loadJson(SHOWN_STORIES_KEY, []));

  const addExchange = useCallback((exchange: AskExchange) => {
    setRecentExchanges((prev) => {
      const next = [...prev, exchange].slice(-MAX_RECENT_EXCHANGES);
      saveJson(EXCHANGES_KEY, next);
      return next;
    });
  }, []);

  const addShownStory = useCallback((storyId: string) => {
    setShownStories((prev) => {
      if (prev.includes(storyId)) return prev;
      const next = [...prev, storyId];
      saveJson(SHOWN_STORIES_KEY, next);
      return next;
    });
  }, []);

  return (
    <SessionContext.Provider value={{ recentExchanges, addExchange, shownStories, addShownStory }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSessionContext(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSessionContext must be used within a SessionContextProvider");
  return ctx;
}
