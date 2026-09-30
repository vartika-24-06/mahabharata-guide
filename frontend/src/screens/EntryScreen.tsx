import { useState } from "react";
import type { FormEvent } from "react";
import { useValidationState } from "../state/ValidationStateContext";

/** story-mode/qna-mode Requirement 1: entering a mode with no request
 * yet still lets the user in - the picker/input just opens empty on the
 * other side. */
export function EntryScreen() {
  const { setPendingInput } = useValidationState();
  const [text, setText] = useState("");

  function submit(mode: "qna" | "story", e?: FormEvent) {
    e?.preventDefault();
    setPendingInput({ text: text.trim(), mode });
  }

  return (
    <div className="entry-screen">
      <h1>The Mahabharata Guide</h1>
      <p>Ask a question about the epic, or hear a story from it.</p>

      <form onSubmit={(e) => submit(text.trim() ? "qna" : "qna", e)}>
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Type a question or a story request..."
        />
      </form>

      <div className="path-selector">
        <button type="button" onClick={() => submit("qna")}>
          Ask a Question
        </button>
        <button type="button" onClick={() => submit("story")}>
          Hear a Story
        </button>
      </div>
    </div>
  );
}
