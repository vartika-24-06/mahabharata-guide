# Implementation Plan: Answering Engine

## Overview

This plan builds the shared engine behind Q&A mode, story mode and the guardrails, plus the Q&A and story screens. It runs after the entry-screen tasks. Each task should be small enough for one focused session and should end with a commit.

## Tasks

### Group 1: Feasibility and source

- [ ] 1. Confirm the source and terms
  - Check the source site's terms on automated downloads and record the result in `docs/source-notes.md`
  - Confirm all 18 parvas are present and sections are numbered
- [ ] 2. Feasibility check on the free host
  - Deploy a tiny test that loads the chosen search model and re-ranker on Render's free plan
  - Record memory used and time taken, with the re-ranker off and with it on, in `docs/hosting-notes.md`
  - This is input to the off-vs-on comparison in task 23, not the final decision by itself

### Group 2: Preparing the text

- [ ] 3. Download the source file
  - Download mahatxt.zip from sacred-texts.com once (by hand or a single request), into a folder that is not committed
  - Record the download date and the terms checked in `docs/source-notes.md`
- [ ] 4. Parse and split
  - Read the book number, parva name and credit line from each file's header; split at "Section" markers, converting Roman numerals to plain numbers; apply the known site corrections (Book 1 sections 176/177 swapped, Book 2 section 67, Book 7 missing breaks at 54/55/189, Book 13's two 168s); cut off everything from the "Footnotes" heading onward and store it separately; strip `[1]`-style markers from body passages; keep parva, section and passage id on each passage
- [ ] 5. Completeness report
  - Count sections per parva and stop the build if any parva is missing or a count looks wrong, allowing for the known corrections above; flag any file that breaks the expected pattern (no "Footnotes" heading, a section marker that does not convert)
- [ ] 6. Build indexes
  - Build the keyword index and the meaning-based index from the passages; decide where the built index is stored so the live server can load it

### Group 3: Search and scope

- [ ] 7. Hybrid search
  - Merge keyword and meaning-based results by rank
- [ ] 8. Re-ranker with an on/off setting
  - Add the re-ranker, controlled by a setting that defaults to off, and log timing without logging any question text
- [ ] 9. Scope check
  - Curated names, places, themes and spelling variants; follow-ups pass when there is conversation context; fixed one-line declines
- [ ] 10. Rule-override, prompt-reveal and persona detection with fixed decline wording
- [ ] 11. Request rate limit per visitor, with a polite wait message

### Group 4: Answering

- [ ] 12. Question classifier
  - Short call to the visitor's model; returns label and confidence; low confidence becomes ambiguous
- [ ] 13. Answer writer and citation builder
  - Prompt rules from the design; citations built from passage ids; drop and recheck when an id does not exist
- [ ] 14. Q&A endpoint
  - Short answers, ambiguous two-sentence format, Tell Me More, "no good answer" with related topics, follow-ups using context sent from the browser
- [ ] 15. Story catalogue
  - Build the Featured Characters and parva catalogue from the passages and review it by hand
- [ ] 16. Story endpoint
  - Snippets of about 150 words, Tell Me More continues in order, "already know this one" picks another story, "Surprise me", shown stories sent from the browser

### Group 5: Screens

- [ ] 17. Q&A screen
  - Question input, answer with citations, Tell Me More, switch to story mode, error and loading states as in the spec
- [ ] 18. Story screen
  - Story picker (typed request, characters, parvas, Surprise me), snippet with citation, the three choices, switch to Q&A
- [ ] 19. Session context in the browser
  - Recent exchanges and shown stories kept in the tab, cleared on tab close

### Group 6: Evaluation and launch

- [ ] 20. Eval runner
  - Run all queries in `docs/qa-eval-set.md` with the re-ranker off, record the outcome and timing, produce the confusion table
  - Run the same queries with the re-ranker on, record the outcome and timing, produce a second confusion table
- [ ] 21. Citation check
  - Automatic test that every citation names a real parva and section and a verbatim excerpt
- [ ] 22. Redaction test for question text
  - Confirm no question text appears in any log
- [ ] 23. Deploy and decide the re-ranker setting
  - Deploy, compare the two eval runs from task 20 side by side (accuracy gained vs. time cost), and decide whether the re-ranker stays on for launch
  - Record the decision and the comparison in `docs/decision-log.md`

## Task Dependency Graph

Tasks are grouped into waves. Everything in a wave can be started once every wave before it is done; tasks within the same wave don't depend on each other.

```json
{
  "waves": [
    [1, 2, 11],
    [3, 9],
    [4, 10],
    [5, 12],
    [6],
    [7, 15],
    [8],
    [13, 16],
    [14],
    [17, 18],
    [19],
    [20, 21, 22],
    [23]
  ]
}
```

Notes on the graph:
- 1 (confirm source/terms) and 2 (host feasibility) have no dependencies and can start immediately, alongside 11 (request rate limit), which is self-contained infra.
- The text-preparation chain (3 → 4 → 5 → 6) is strictly sequential: each step needs the previous step's output.
- 9 (scope check) needs the source confirmed (1) but not the built index; 10 (rule-override/persona detection) builds on 9's guardrail scaffolding.
- 7 (hybrid search) needs the built indexes (6); 8 (re-ranker) needs hybrid search (7) and the hosting feasibility numbers (2) to size it correctly.
- 12 (classifier) needs the scope check and rate limit in place (9, 11) since it sits right after them in the request path; 15 (story catalogue) only needs the built passages (6).
- 13 (answer writer/citations) needs the re-ranker (8) and the classifier (12); 16 (story endpoint) needs the catalogue (15) and search (8).
- 14 (Q&A endpoint) needs the answer writer (13); 17 and 18 (screens) need their respective endpoints (14, 16).
- 19 (browser session context) needs both screens (17, 18) since it's wired into each.
- 20 to 22 (eval runner, citation check, redaction test) all need the full working pipeline (19) to test against.
- 23 (deploy and decide the re-ranker setting) needs the eval results (20, 21, 22) and the hosting feasibility numbers (2).

## Notes

- This plan runs after the entry-screen tasks; it assumes the key-handling, throttling and provider-adapter pieces from that spec already exist and are reused here rather than rebuilt.
- Tasks 2, 13, 20 and 23 are the ones that fix a launch setting rather than just build something; their decisions and reasoning belong in `docs/decision-log.md`, not just in code comments, so the case study can cite them later.
- Where a task depends on a judgment call (the scope-check word list in 9, the passage size in 4, the request-rate numbers in 11), the design doc's "Open items" section is the place to record the final choice once made.

## Task amendments (authoritative)

- Entry-screen client timeout: replace the 20-second limit on the first request after idle with about 75 seconds and a "Waking up the server" message (Render's free plan takes about a minute to wake).
- Do not use self-pinging to keep the free host awake.
- Tasks 2, 13, 20 and 23 decide launch settings; record their results in `docs/decision-log.md`.
