import { useState } from "react";
import type { FormEvent } from "react";
import type { AskResponse, Citation } from "../api/client";
import { askQuestion } from "../api/client";
import { useValidationState } from "../state/ValidationStateContext";
import type { PendingInput } from "../state/ValidationStateContext";
import { useSessionContext } from "../state/SessionContextProvider";

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

/** Task 16: Q&A screen. Question input, answer with citations, Tell Me
 * More, error/loading states, switch to story mode (qna-mode
 * Requirements 1-11). */
export function QnAScreen({
  initialInput,
  onSwitchToStory,
}: {
  initialInput: PendingInput;
  onSwitchToStory: () => void;
}) {
  const { validatedKey, invalidateKeyOnAuthError } = useValidationState();
  // qna-mode Requirement 8.4: kept across a switch to story mode and
  // back, so this comes from the session-lasting context, not local
  // state that would reset every time this screen unmounts.
  const { recentExchanges, addExchange } = useSessionContext();
  const [question, setQuestion] = useState(initialInput.text);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [label, setLabel] = useState<string | undefined>(undefined);
  const [expanded, setExpanded] = useState<AskResponse | null>(null);
  const [expandLoading, setExpandLoading] = useState(false);
  const [askedOnMount, setAskedOnMount] = useState(false);

  const sessionToken = safeSessionToken();

  async function runAsk(q: string, opts: { expand?: boolean; useLabel?: string } = {}) {
    if (!validatedKey) return;
    if (opts.expand) setExpandLoading(true);
    else {
      setLoading(true);
      setAnswer(null);
      setExpanded(null);
    }
    setError(null);

    const result = await askQuestion(validatedKey, sessionToken, {
      question: q,
      expand: opts.expand,
      label: opts.useLabel,
      context: recentExchanges,
    });

    if (opts.expand) setExpandLoading(false);
    else setLoading(false);

    if (!result.ok) {
      if (result.error.kind === "auth") {
        invalidateKeyOnAuthError({ text: q, mode: "qna" });
        return;
      }
      setError(
        result.error.kind === "rate_limit"
          ? "Your key hit a rate limit. You can retry with the same key or add a different one."
          : result.error.message
      );
      return;
    }

    if (opts.expand) {
      setExpanded(result.data);
      return;
    }

    setAnswer(result.data);
    if (result.data.type === "factual" || result.data.type === "philosophical") {
      setLabel(result.data.type);
    } else if (result.data.type === "ambiguous") {
      setLabel("ambiguous");
    }
    addExchange({ question: q, type: result.data.type });
  }

  // qna-mode Requirement 1.1: a request handed off from the entry screen
  // answers immediately, without making the user resubmit.
  if (!askedOnMount && initialInput.text) {
    setAskedOnMount(true);
    runAsk(initialInput.text);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (question.trim()) runAsk(question.trim());
  }

  return (
    <div className="qna-screen">
      <div className="mode-switch">
        <button type="button" onClick={onSwitchToStory}>
          Hear a Story instead
        </button>
      </div>

      <form onSubmit={handleSubmit}>
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about the Mahabharata..."
        />
        <button type="submit" disabled={loading}>
          Ask
        </button>
      </form>

      {loading && <p className="loading">Thinking...</p>}
      {error && (
        <div className="inline-error" role="alert">
          <p>{error}</p>
          <button type="button" onClick={() => runAsk(question)}>
            Retry
          </button>
        </div>
      )}

      {answer && <AnswerView answer={answer} />}

      {answer && (answer.type === "factual" || answer.type === "philosophical") && !expanded && (
        <button
          type="button"
          disabled={expandLoading}
          onClick={() => runAsk(question, { expand: true, useLabel: label })}
        >
          {expandLoading ? "Loading..." : "Tell Me More"}
        </button>
      )}
      {answer && answer.type === "ambiguous" && !expanded && (
        <button
          type="button"
          disabled={expandLoading}
          onClick={() => runAsk(question, { expand: true, useLabel: "ambiguous" })}
        >
          {expandLoading ? "Loading..." : "Tell Me More"}
        </button>
      )}
      {expanded && <AnswerView answer={expanded} />}
    </div>
  );
}

function AnswerView({ answer }: { answer: AskResponse }) {
  if (answer.type === "decline") return <p className="decline">{answer.message}</p>;
  if (answer.type === "no_answer") {
    return (
      <div className="no-answer">
        <p>{answer.message}</p>
      </div>
    );
  }
  if (answer.type === "ambiguous") {
    return (
      <div className="answer ambiguous">
        <p>{answer.factual_sentence}</p>
        <CitationList citations={answer.factual_citations} />
        <p>{answer.philosophical_sentence}</p>
        <CitationList citations={answer.philosophical_citations} />
      </div>
    );
  }
  return (
    <div className="answer">
      <p>{answer.answer}</p>
      <CitationList citations={answer.citations} />
    </div>
  );
}

function safeSessionToken(): string | undefined {
  try {
    return sessionStorage.getItem("session_token") ?? undefined;
  } catch {
    return undefined;
  }
}
