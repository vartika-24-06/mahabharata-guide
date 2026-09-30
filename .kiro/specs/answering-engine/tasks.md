# Implementation Plan: Answering Engine

## Overview

This plan builds the shared engine behind Q&A mode, story mode and the guardrails, plus the Q&A and story screens. It runs after the entry-screen tasks. Each task should be small enough for one focused session and should end with a commit.

**Revision note:** Tasks 1–5 are done and are marked complete below — the real corpus (5,578 passages, all 18 books) is parsed and verified against the actual files, not assumed from secondhand documentation. Task 2's original goal (self-hosted embedding + re-ranker feasibility) is also done, and the answer was no: no self-hosted-model configuration fit Render's free 512MB, even after ONNX/int8 quantization. The remaining tasks below reflect the resulting architecture change — external embeddings API + Supabase (pgvector) instead of a self-hosted model — described in `answering-engine/design.md`.

## Tasks

### Group 1: Feasibility and source

- [x] 1. Confirm the source and terms
  - Checked the source site's terms on automated downloads, recorded in `docs/source-notes.md`
  - Confirmed all 18 parvas are present; real numbering gaps/duplicates documented (go beyond the site's own errata page)
- [x] 2. Feasibility check on self-hosting the search/re-ranker models
  - Tested PyTorch, then ONNX+int8, then embedding-only, first on a toy 10-passage set and then against the real 5,578-passage corpus
  - Result: none fit Render's free 512MB (real-corpus embedding-only alone was ~703MB) — recorded in `docs/hosting-notes.md`
  - Decision: move to external embeddings API + Supabase rather than self-host any model (see design.md's "Revision note")

### Group 2: Preparing the text

- [x] 3. Download the source file
  - Downloaded mahatxt.zip from sacred-texts.com once, recorded in `docs/source-notes.md`
- [x] 4. Parse and split
  - Real parser (`backend/ingest.py`) handles both section-marker formats found in the actual files (roman-numeral `SECTION <ROMAN>` in 11 books, bare arabic number in 7 books), extracts headers, cuts footnotes where present, strips `[1]`-style markers, and produces passages with parva/section/passage id
- [x] 5. Completeness report
  - Confirms all 18 parvas present; logs every numbering gap/duplicate found (table in `docs/source-notes.md`) as an informational finding rather than a build-stopping error; flags any file that breaks the expected pattern entirely
- [x] 6. Build indexes
  - Build the local keyword (BM25) index from the passages
  - Provision a Supabase project with the pgvector extension; create the passages table (`parva`, `section`, `passage_id`, `text`, `embedding`)
  - Using our own embeddings-API key (not the visitor's), embed every real passage once and write the rows to Supabase

### Group 3: Search and scope

- [x] 7. Hybrid search
  - Embed the incoming question via our own embeddings key; query Supabase (pgvector) for the closest passages; merge with the local BM25 keyword results by rank
  - If the embeddings API call fails or rate-limits, fall back to keyword-only results for that request rather than failing (design.md Property 8 / Error Handling)
- [x] 8. Scope check
  - Curated names, places, themes and spelling variants; follow-ups pass when there is conversation context; fixed one-line declines
- [x] 9. Rule-override, prompt-reveal and persona detection with fixed decline wording
- [x] 10. Request rate limit per visitor, with a polite wait message
  - This limit also bounds how often our own embeddings key gets called per visitor — no separate budget limit needed for v1, but worth a basic usage check (see design.md "Open items")

### Group 4: Answering

- [x] 11. Question classifier
  - Short call to the visitor's model; returns label and confidence; low confidence becomes ambiguous
- [x] 12. Answer writer and citation builder
  - Prompt rules from the design; citations built from passage ids; drop and recheck when an id does not exist
- [x] 13. Q&A endpoint
  - Short answers, ambiguous two-sentence format, Tell Me More, "no good answer" with related topics, follow-ups using context sent from the browser
- [x] 14. Story catalogue
  - Build the Featured Characters and parva catalogue from the passages and review it by hand
- [ ] 15. Story endpoint
  - Snippets of about 150 words, Tell Me More continues in order, "already know this one" picks another story, "Surprise me", shown stories sent from the browser

### Group 5: Screens

- [ ] 16. Q&A screen
  - Question input, answer with citations, Tell Me More, switch to story mode, error and loading states as in the spec
- [ ] 17. Story screen
  - Story picker (typed request, characters, parvas, Surprise me), snippet with citation, the three choices, switch to Q&A
- [ ] 18. Session context in the browser
  - Recent exchanges and shown stories kept in the tab, cleared on tab close

### Group 6: Evaluation and launch

- [ ] 19. Eval runner
  - Run all queries in `docs/qa-eval-set.md`, record the outcome, produce the confusion table
  - Include at least one deliberate run with the embeddings API call forced to fail, to confirm the keyword-only fallback works end to end
- [ ] 20. Citation check
  - Automatic test that every citation names a real parva and section and a verbatim excerpt
- [ ] 21. Redaction test for both keys
  - Confirm neither the visitor's key nor our own embeddings key appears in any log line, in both the normal and degraded (keyword-only) paths
- [ ] 22. Deploy
  - Deploy to Render's free plan (no self-hosted model, so this should now fit comfortably); confirm real memory usage in production matches expectations
  - Record the deployment outcome in `docs/decision-log.md`

## Task Dependency Graph

Tasks are grouped into waves. Everything in a wave can be started once every wave before it is done; tasks within the same wave don't depend on each other. Tasks 1–5 are already done (wave 0, shown for completeness).

```json
{
  "waves": [
    [1, 2, 3, 4, 5],
    [6, 10],
    [7, 8],
    [9],
    [11, 14],
    [12, 15],
    [13],
    [16, 17],
    [18],
    [19, 20, 21],
    [22]
  ]
}
```

Notes on the graph:
- Wave 0 (tasks 1–5) is done: source confirmed, real corpus parsed, self-hosting feasibility tested and rejected.
- 6 (build indexes: BM25 + Supabase/embeddings) and 10 (request rate limit) have no remaining dependencies and can start immediately.
- 7 (hybrid search, including the keyword-only fallback) needs the indexes (6); 8 (scope check) needs the source confirmed (already done) but not the built index, so it can run alongside 7.
- 9 (rule-override/persona detection) builds on 8's guardrail scaffolding.
- 11 (classifier) needs the scope check and rate limit in place (8, 10); 14 (story catalogue) only needs the built passages (already done in wave 0).
- 12 (answer writer/citations) needs hybrid search (7) and the classifier (11); 15 (story endpoint) needs the catalogue (14) and search (7).
- 13 (Q&A endpoint) needs the answer writer (12); 16 and 17 (screens) need their respective endpoints (13, 15).
- 18 (browser session context) needs both screens (16, 17) since it's wired into each.
- 19 to 21 (eval runner, citation check, redaction test) all need the full working pipeline (18) to test against.
- 22 (deploy) needs the eval/test results (19, 20, 21).

## Notes

- This plan runs after the entry-screen tasks; it assumes the key-handling, throttling and provider-adapter pieces from that spec already exist and are reused here rather than rebuilt.
- Task 6 introduces a second, server-side key (the embeddings key) alongside the visitor's own key from the entry-screen spec — keep the two conceptually and architecturally separate (design.md Property 4).
- Where a task depends on a judgment call (the scope-check word list in 8, the passage size in 4 — already decided at roughly a few hundred words per passage — the request-rate numbers in 10), the design doc's "Open items" section is the place to record the final choice once made.
- Re-ranking is deferred out of v1 entirely (design.md "Search architecture" and "Open items") — there is deliberately no re-ranker task in this plan.

## Task amendments (authoritative)

- Entry-screen client timeout: replace the 20-second limit on the first request after idle with about 75 seconds and a "Waking up the server" message (Render's free plan takes about a minute to wake).
- Do not use self-pinging to keep the free host awake.
- Tasks 2, 19 and 22 are launch-setting decisions; their results are recorded in `docs/decision-log.md`.
