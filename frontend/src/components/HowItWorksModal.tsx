/** UX item 2: "how this works" slide-over, same modal pattern as
 * KeyModal. This app doubles as a spec-driven-development case study,
 * so the audience for this modal isn't only a curious visitor - it's
 * also a PM hiring manager sizing up technical fluency, which is why
 * the actual technique names (RAG, BM25, RRF, pgvector) are named here
 * rather than only described in plain English underneath them. */
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
        <p className="how-it-works-intro">
          A retrieval-augmented generation (RAG) pipeline over the real text, not a model
          reciting the Mahabharata from memory - three stages per question.
        </p>

        <div className="how-it-works-steps">
          <section>
            <h3>1. Classify</h3>
            <p>
              An LLM call (your own API key) labels the question <strong>factual</strong>,{" "}
              <strong>philosophical</strong>, or <strong>ambiguous</strong>, with a confidence
              score - low confidence is deliberately downgraded to ambiguous rather than risking a
              shaky one-sided answer. The label decides the response shape: ambiguous questions
              get two short readings side by side, each independently cited, instead of one
              blended answer.
            </p>
          </section>

          <section>
            <h3>2. Retrieve</h3>
            <p>
              The source text (Ganguli's 19th-century English prose translation, ~18 books) is
              chunked into passages and searched two ways at once: <strong>BM25</strong> keyword
              search over the raw text, and a <strong>vector similarity search</strong> (OpenAI
              embeddings, cosine distance via <strong>pgvector</strong> in Supabase) over every
              passage's meaning. The two ranked lists are merged with{" "}
              <strong>Reciprocal Rank Fusion</strong> rather than averaged - BM25 scores and
              cosine similarities aren't on the same scale, so RRF combines them by rank order
              alone. On a no-citation result, one retry reruns retrieval with LLM-generated
              period-vocabulary keywords (e.g. "siblings" → "brothers and sisters"), closing a
              modern-phrasing-vs-archaic-translation recall gap BM25 can't bridge on its own.
            </p>
          </section>

          <section>
            <h3>3. Answer, grounded in citations</h3>
            <p>
              The model writes its answer from only the retrieved passages and reports which ones
              it used by number. Citations are then built entirely in code from those numbers,
              never from anything the model wrote - a citation can't name a passage that wasn't
              actually retrieved, and its excerpt is always a verbatim slice of the real text. An
              answer that ends up with zero valid citations is shown as "the text doesn't cover
              this" rather than displayed as-is.
            </p>
          </section>
        </div>

        <p className="disclosure">
          <em>
            Answers run on whichever API key you've added, so quality and occasional mistakes vary
            by provider.
          </em>
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
