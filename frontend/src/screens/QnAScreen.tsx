import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { AskResponse, Citation, FeedbackRating, ValidatedKeyLike } from "../api/client";
import { askQuestion, submitFeedback } from "../api/client";
import { useValidationState } from "../state/ValidationStateContext";
import type { RunRequest } from "../state/ValidationStateContext";
import { useSessionContext } from "../state/SessionContextProvider";

// Pulled from docs/qna-eval-set's unflagged Philosophical rows, and
// checked locally against the BM25 index, not just the eval set's
// classification label - row 13 ("What does the Mahabharata say about
// duty?") looked like an equally safe pick on paper but turned out to
// have zero keyword-search recall for the Gita passages that actually
// answer it (found via a live no_answer on this exact prompt), so it's
// swapped for row 16 here instead.
const EXAMPLE_PROMPTS = [
  "What does Krishna teach Arjuna about action and its results?",
  "What does Vidura say about greed?",
  "Why did Karna suffer so much?",
];

/** UX item 7: thumbs up/down on a finished answer. Fires once per
 * answer (a question's `key` on the parent resets this component when
 * a new question runs), logs the full Q&A to Supabase via
 * /api/feedback, and shows a quiet "Thanks" in place of the buttons -
 * nothing automated happens with the result, it's just a log for
 * Vartika to review later. */
function FeedbackButtons({
  question,
  answer,
  validatedKey,
}: {
  question: string;
  answer: AskResponse;
  validatedKey: ValidatedKeyLike | null;
}) {
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");

  if (answer.type === "decline" || answer.type === "no_answer") return null;

  const { answerText, citations } =
    answer.type === "ambiguous"
      ? {
          answerText: `${answer.factual_sentence} ${answer.philosophical_sentence}`,
          citations: [...answer.factual_citations, ...answer.philosophical_citations],
        }
      : { answerText: answer.answer, citations: answer.citations };

  async function handleRate(rating: FeedbackRating) {
    setState("sending");
    const result = await submitFeedback({
      question,
      answerType: answer.type,
      answerText,
      citations,
      rating,
      provider: validatedKey?.provider,
      model: validatedKey?.model,
    });
    setState(result.ok ? "sent" : "error");
  }

  if (state === "sent") {
    return <p className="feedback-thanks">Thanks for the feedback.</p>;
  }

  return (
    <div className="feedback-buttons">
      <span className="feedback-label">Was this helpful?</span>
      <button
        type="button"
        aria-label="Helpful"
        disabled={state === "sending"}
        onClick={() => handleRate("up")}
      >
        👍
      </button>
      <button
        type="button"
        aria-label="Not helpful"
        disabled={state === "sending"}
        onClick={() => handleRate("down")}
      >
        👎
      </button>
      {state === "error" && <span className="inline-error">Couldn't save that - try again?</span>}
    </div>
  );
}

function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;
  // The backend already picks a short, relevant snippet of the cited
  // passage (answer.py's _select_excerpt, UX item 8) rather than
  // always the passage's first N characters - a plain head-truncation
  // here could cut that snippet right back down to an arbitrary prefix
  // and reintroduce the same bug, so it's shown as-is.
  return (
    <ul className="citations">
      {citations.map((c, i) => (
        <li key={i}>
          <strong>{c.parva_name}</strong>, Section {c.section}: "{c.excerpt}"
        </li>
      ))}
    </ul>
  );
}

/** Task 16: Q&A screen - the whole app. Question input, answer with
 * citations, Tell Me More, error/loading states (qna-mode Requirements
 * 1-11). */
export function QnAScreen({ runRequest }: { runRequest: RunRequest | null }) {
  const { validatedKey, invalidateKeyOnAuthError, setPendingInput } = useValidationState();
  // qna-mode Requirement 8.4: kept across a switch to story mode and
  // back, so this comes from the session-lasting context, not local
  // state that would reset every time this screen unmounts.
  const { recentExchanges, addExchange } = useSessionContext();
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [label, setLabel] = useState<string | undefined>(undefined);
  const [expanded, setExpanded] = useState<AskResponse | null>(null);
  const [expandLoading, setExpandLoading] = useState(false);
  const lastHandledNonce = useRef<number | null>(null);

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
        invalidateKeyOnAuthError({ text: q });
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

  // A key just became available for a request made from this tab
  // (either it was already validated and this fires immediately, or
  // the Key Modal just succeeded) - run it now.
  useEffect(() => {
    if (!runRequest || runRequest.nonce === lastHandledNonce.current) return;
    lastHandledNonce.current = runRequest.nonce;
    setQuestion(runRequest.input.text);
    runAsk(runRequest.input.text);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runRequest]);

  function submitQuestion(text: string) {
    const q = text.trim();
    if (!q) return;
    setQuestion(q);
    if (validatedKey) runAsk(q);
    else setPendingInput({ text: q });
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    submitQuestion(question);
  }

  const showExamplePrompts = !loading && !answer && !question.trim();

  return (
    <div className="qna-screen">
      <form onSubmit={handleSubmit}>
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about the Mahabharata..."
        />
        <button type="submit" className="btn-primary" disabled={loading}>
          Ask
        </button>
      </form>

      {showExamplePrompts && (
        <div className="example-prompts">
          <p className="example-prompts-label">Try asking:</p>
          {EXAMPLE_PROMPTS.map((prompt) => (
            <button key={prompt} type="button" onClick={() => submitQuestion(prompt)}>
              {prompt}
            </button>
          ))}
        </div>
      )}

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
      {answer && (
        <FeedbackButtons key={question} question={question} answer={answer} validatedKey={validatedKey} />
      )}

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
