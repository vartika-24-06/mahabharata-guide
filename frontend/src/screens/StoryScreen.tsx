import { useState } from "react";
import type { FormEvent } from "react";
import type { Citation, StoryResponse } from "../api/client";
import { requestStory } from "../api/client";
import { useValidationState } from "../state/ValidationStateContext";
import type { PendingInput } from "../state/ValidationStateContext";
import { useSessionContext } from "../state/SessionContextProvider";
import { FEATURED_CHARACTERS, PARVAS, displayParvaName } from "../storyCatalogue";

/** Task 17: Story screen. Picker (typed/characters/parvas/surprise),
 * snippet with citation, the three post-snippet choices, switch to Q&A
 * (story-mode Requirements 1-11). */
export function StoryScreen({
  initialInput,
  onSwitchToQnA,
}: {
  initialInput: PendingInput;
  onSwitchToQnA: () => void;
}) {
  const { validatedKey, invalidateKeyOnAuthError } = useValidationState();
  // story-mode Requirement 8.4: kept across a switch to Q&A mode and
  // back, so this comes from the session-lasting context, not local
  // state that would reset every time this screen unmounts.
  const { shownStories, addShownStory } = useSessionContext();
  const [typedText, setTypedText] = useState(initialInput.mode === "story" ? initialInput.text : "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [story, setStory] = useState<StoryResponse | null>(null);
  const [currentSubject, setCurrentSubject] = useState<string | null>(null);
  const [currentEpisode, setCurrentEpisode] = useState<number | null>(null);
  const [startedOnMount, setStartedOnMount] = useState(false);

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

  if (!startedOnMount && initialInput.mode === "story" && initialInput.text) {
    setStartedOnMount(true);
    run("typed", { text: initialInput.text });
  }

  function submitTyped(e: FormEvent) {
    e.preventDefault();
    if (typedText.trim()) run("typed", { text: typedText.trim() });
  }

  const showPicker = !story || story.type === "no_other_story" || story.type === "decline";

  return (
    <div className="story-screen">
      <div className="mode-switch">
        <button type="button" className="btn-ghost" onClick={onSwitchToQnA}>
          Ask a Question instead
        </button>
      </div>

      {showPicker && (
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
              <button key={name} type="button" onClick={() => run("character", { subject: name })}>
                {name}
              </button>
            ))}
          </div>

          <div className="picker-section">
            <h3>Parvas</h3>
            {PARVAS.map((name) => (
              <button key={name} type="button" onClick={() => run("parva", { subject: name })}>
                {displayParvaName(name)}
              </button>
            ))}
          </div>

          <button type="button" onClick={() => run("surprise")} disabled={loading}>
            Surprise me
          </button>
        </div>
      )}

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
          <button type="button" onClick={() => setStory(null)}>
            A new character or parva
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
