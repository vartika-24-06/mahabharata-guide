import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { Citation, StoryResponse } from "../api/client";
import { requestStory } from "../api/client";
import { useValidationState } from "../state/ValidationStateContext";
import type { RunRequest } from "../state/ValidationStateContext";
import { useSessionContext } from "../state/SessionContextProvider";
import { FEATURED_CHARACTERS, PARVAS, displayParvaName } from "../storyCatalogue";

type PresetType = "character" | "parva" | "surprise";

/** Task 17: Story screen. Picker (typed/characters/parvas/surprise),
 * snippet with citation, the three post-snippet choices, switch to Q&A
 * (story-mode Requirements 1-11). Mode switching now happens via the
 * persistent tab bar in App.tsx. The presets stay visible at all times
 * (not just before a story is picked) so the tab's range of characters
 * and parvas is discoverable even mid-story, and doubles as the way
 * back to a new one - there's no separate "pick again" button. */
export function StoryScreen({ runRequest }: { runRequest: RunRequest | null }) {
  const { validatedKey, invalidateKeyOnAuthError, setPendingInput } = useValidationState();
  // story-mode Requirement 8.4: kept across a switch to Q&A and back,
  // so this comes from the session-lasting context, not local state
  // that would reset every time this screen unmounts.
  const { shownStories, addShownStory } = useSessionContext();
  const [typedText, setTypedText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [story, setStory] = useState<StoryResponse | null>(null);
  const [currentSubject, setCurrentSubject] = useState<string | null>(null);
  const [currentEpisode, setCurrentEpisode] = useState<number | null>(null);
  const lastHandledNonce = useRef<number | null>(null);

  const sessionToken = safeSessionToken();

  async function run(
    requestType: "typed" | "character" | "parva" | "surprise" | "continue" | "another",
    opts: { text?: string; subject?: string; episodeIndex?: number; previousText?: string } = {}
  ) {
    if (!validatedKey) return;
    setLoading(true);
    setError(null);

    const result = await requestStory(validatedKey, sessionToken, {
      requestType,
      text: opts.text,
      subject: opts.subject,
      episodeIndex: opts.episodeIndex,
      previousText: opts.previousText,
      shownStories,
    });

    setLoading(false);

    if (!result.ok) {
      if (result.error.kind === "auth") {
        invalidateKeyOnAuthError({ text: opts.text ?? "", mode: "story" });
        return;
      }
      setError(
        result.error.kind === "rate_limit"
          ? "Your key hit a rate limit. You can retry with the same key or add a different one."
          : result.error.message
      );
      return;
    }

    setStory(result.data);
    if (result.data.type === "story") {
      const { subject, story_id: storyId } = result.data;
      setCurrentSubject(subject);
      setCurrentEpisode(Number(storyId.split("#").pop()));
      addShownStory(storyId);
    }
  }

  // A key just became available for a request made from this tab
  // (typed text or a preset chip) - replay it now.
  useEffect(() => {
    if (!runRequest || runRequest.nonce === lastHandledNonce.current) return;
    lastHandledNonce.current = runRequest.nonce;
    const { input } = runRequest;
    if (input.storyAction) {
      run(input.storyAction.requestType, { subject: input.storyAction.subject });
    } else {
      setTypedText(input.text);
      run("typed", { text: input.text });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runRequest]);

  function requestPreset(requestType: PresetType, subject?: string) {
    if (validatedKey) run(requestType, { subject });
    else setPendingInput({ text: "", mode: "story", storyAction: { requestType, subject } });
  }

  function submitTyped(e: FormEvent) {
    e.preventDefault();
    const t = typedText.trim();
    if (!t) return;
    if (validatedKey) run("typed", { text: t });
    else setPendingInput({ text: t, mode: "story" });
  }

  return (
    <div className="story-screen">
      <div className="story-picker">
        <form onSubmit={submitTyped}>
          <input
            type="text"
            value={typedText}
            onChange={(e) => setTypedText(e.target.value)}
            placeholder="Tell me a story about..."
          />
          <button type="submit" className="btn-primary" disabled={loading}>
            Go
          </button>
        </form>

        <div className="picker-section">
          <h3>Characters</h3>
          {FEATURED_CHARACTERS.map((name) => (
            <button key={name} type="button" onClick={() => requestPreset("character", name)}>
              {name}
            </button>
          ))}
        </div>

        <div className="picker-section">
          <h3>Parvas</h3>
          {PARVAS.map((name) => (
            <button key={name} type="button" onClick={() => requestPreset("parva", name)}>
              {displayParvaName(name)}
            </button>
          ))}
        </div>

        <button type="button" onClick={() => requestPreset("surprise")} disabled={loading}>
          Surprise me
        </button>
      </div>

      {loading && <p className="loading">Preparing the story...</p>}
      {error && (
        <div className="inline-error" role="alert">
          <p>{error}</p>
        </div>
      )}

      {story && <StoryView story={story} />}

      {story?.type === "story" && (
        <div className="story-choices">
          <button
            type="button"
            disabled={loading || story.complete}
            onClick={() =>
              run("continue", {
                subject: currentSubject!,
                episodeIndex: currentEpisode!,
                previousText: story.text,
              })
            }
          >
            Tell me more
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={() => run("another", { subject: currentSubject!, episodeIndex: currentEpisode! })}
          >
            I already know this one
          </button>
        </div>
      )}
    </div>
  );
}

function StoryView({ story }: { story: StoryResponse }) {
  if (story.type === "decline") return <p className="decline">{story.message}</p>;
  if (story.type === "no_story" || story.type === "no_other_story" || story.type === "complete") {
    return <p className="no-story">{story.message}</p>;
  }
  return (
    <div className="story">
      <p>{story.text}</p>
      <CitationList citations={story.citations} />
      {story.complete && <p className="story-complete">That's the whole story the text has on this.</p>}
    </div>
  );
}

function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;
  return (
    <ul className="citations">
      {citations.map((c, i) => (
        <li key={i}>
          <strong>{c.parva_name}</strong>, Section {c.section}: "{c.excerpt.slice(0, 140)}
          {c.excerpt.length > 140 ? "..." : ""}"
        </li>
      ))}
    </ul>
  );
}

function safeSessionToken(): string | undefined {
  try {
    return sessionStorage.getItem("session_token") ?? undefined;
  } catch {
    return undefined;
  }
}
