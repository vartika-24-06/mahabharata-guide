/** UX item 2: "how this works" slide-over, same modal pattern as
 * KeyModal. Explains the three-stage pipeline in plain terms - not the
 * implementation, the shape of it - so a visitor can tell why an answer
 * looks the way it does (a short answer vs. two readings side by side)
 * and where its citations actually come from. */
export function HowItWorksModal({ onClose }: { onClose: () => void }) {
  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="How this works"
      onClick={onClose}
    >
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <h2>How this works</h2>

        <div className="how-it-works-steps">
          <section>
            <h3>1. Classify the question</h3>
            <p>
              Your question is sent to the model behind your own API key and sorted into one of
              three kinds: <strong>factual</strong> (what happened, who did what),{" "}
              <strong>philosophical</strong> (what the epic has to say about duty, meaning, or
              consequence), or <strong>ambiguous</strong> (genuinely both at once). The label
              decides the shape of the answer you get - ambiguous questions come back as two
              short readings side by side, each with its own citations, instead of one blended
              answer.
            </p>
          </section>

          <section>
            <h3>2. Retrieve the passages</h3>
            <p>
              The text (Kisari Mohan Ganguli's 19th-century English prose translation) is split
              into passages and searched two ways at once: a keyword search over the raw text,
              and a meaning-based search over embeddings of every passage, stored in Supabase.
              The two result lists are merged by rank, so a passage that matches well either way
              - or both - surfaces to the top.
            </p>
          </section>

          <section>
            <h3>3. Answer, grounded in what was retrieved</h3>
            <p>
              The model writes its answer using only the retrieved passages, and every claim is
              tied back to a specific passage shown underneath as a citation. If nothing retrieved
              actually answers the question, it says so rather than guessing from general
              knowledge of the epic.
            </p>
          </section>
        </div>

        <p className="disclosure">
          Answers run on whichever API key you've added, so quality and occasional mistakes vary
          by provider.
        </p>

        <div className="modal-actions">
          <button type="button" className="btn-primary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
