# Design Document: Answering Engine

## Overview

This design covers the shared machinery behind Q&A mode, story mode and the guardrails: preparing the Ganguli text, searching it, checking scope, classifying questions, writing answers and stories, building citations, and protecting the service. It is written to be read by a product owner. Technical choices are explained by what they mean for the product.

It sits behind the entry screen. The entry screen and key handling are covered in the entry-screen spec. Requirements are in three specs: Q&A mode, story mode, and source and guardrails.

## Architecture

### The path of one request

1. **Scope check.** Is this about the Mahabharata (or a follow-up in a conversation)? If not, decline in one polite line. This happens before any search, so off-topic requests cost almost nothing.
2. **Rate-limit check.** Has this visitor made too many requests? If so, say how long to wait.
3. **Classify** (Q&A only). Factual, philosophical or ambiguous.
4. **Search** the prepared text: keyword search and meaning-based search together, then re-rank.
5. **Write** the answer or story in plain modern English, using the visitor's own key.
6. **Build citations from the passages**, not from what the model wrote.
7. **Reply.**

No request text is kept on the server after the reply.

### Search architecture

- **Keyword search** finds exact names and terms (for example "Shikhandi").
- **Meaning-based search** finds passages on the same idea in different words (for example "loyalty despite doubt").
- The two result lists are merged by rank.
- A **re-ranker** then reads the top candidates against the question and picks the best five to eight passages. This is the step that improves precision most, and it is the heaviest.
- **The re-ranker sits behind a setting.** It can be switched off without changing anything else. See "Hosting reality" below.

### Hosting reality (read this one)

- Render's free plan gives 512 MB of memory and a very small share of processor time (0.1 CPU). One review describes it as fine for light workloads but not for AI inference, and free services go to sleep after 15 minutes idle and take about a minute to wake.
- **Consequences for this design:**
  1. **The re-ranker and search models may be too slow on the free plan.** Small models exist (the search model is about 127 MB and the re-ranker roughly 130 to 210 MB by two listings I saw, unverified for our exact choice). Memory may fit, but at 0.1 CPU the search-and-re-rank step could take many seconds.
  2. **Launch decision: the re-ranker starts switched off.** Run the eval set with it off and record the confusion table and timings. Then switch it on, run the same eval set again, and compare accuracy and timing side by side. Keep it on only if the accuracy gain earns back the extra time and the search step still stays reasonably fast on the deployed plan; otherwise leave it off. This comparison, not a single pass/fail timing check, is what decides the launch setting (see "Testing Strategy").
  3. **The first request after idle takes about a minute.** The entry-screen design has a 20-second client timeout, which would fire during a wake-up. Change it: the first request after idle waits up to about 75 seconds and shows "Waking up the server".
  4. **No self-pinging to stay awake.** One source reports Render may suspend services for abnormal self-generated traffic. Warm the server by hand before a demo, or use a paid plan.

## Components and Interfaces

### Text preparation (done once, before launch)

- The text comes from one download: the parva-wise text files (mahatxt.zip) offered by sacred-texts.com. It is downloaded once by hand or by a single request, never by collecting pages one at a time. The site's terms allow one copy of one text per day for robots and forbid repeated high-speed access.
- Each parva is one file. Its header gives the book number, the parva name and a credit line. The parva label for every passage comes from this header. The credit line stays in the stored copy, as the site's terms ask, but is kept out of search and answers.
- Each file is split at its "Section" markers. Roman numerals become plain numbers, and the site's published corrections are applied: Book 1 has two sections swapped (176 and 177), Book 2 has a misplaced section (67), Book 7 lacks the breaks for sections 54, 55 and 189, and Book 13 has two sections numbered 168 (the first is 163).
- The footnotes sit together at the end of each parva's file, under a "Footnotes" heading. Everything from that heading onward is cut off and kept in the stored copy but not used for search or answers in v1. The `[1]`-style markers in the body text are removed from the passages, so excerpts are word for word apart from those markers.
- Each section is cut into passages of roughly a few hundred words. Every passage carries its parva, section number and passage number.
- A **completeness report** counts sections per parva and lists any parva with gaps. The build stops if any of the 18 parvas is missing. It expects the site's known errors listed above, and it flags any file that breaks the pattern, for example a file with no "Footnotes" heading or a section marker that does not convert to a number.
- **Citations name each parva as the source site spells it** (for example Santi, Anusasana, Aswamedha, Asramavasika), and number sections the way the site's pages do, with the corrections above applied. Common alternative spellings are recognised in incoming questions.
- **The About notice** links to sacred-texts.com and carries the credit line. The site's terms allow this use for non-commercial purposes; if the App were ever to charge, a licence would be needed first.
- A keyword index and a meaning-based index are built from the passages. The meaning-based index uses a small open-source model that runs on our own server, so it does not depend on the visitor's key (not every provider offers this service).
- The downloaded text and the built index are kept out of git. Where the built index lives so that the live server can load it is an open item (see below).

### Scope check and guardrails

- A curated list of epic names, places, theme words and common spelling variants (for example "Yudisthir", "Arjun") is used for the check. A request passes if it matches the list or is a follow-up in an ongoing conversation.
- The list, and how strict the check is, are tuned against the eval set. Rows 15, 24, 25 and 29 to 31 are the hard cases.
- Requests to reveal instructions, override rules or speak as a character are recognised and declined in one line. The model is also told never to reveal its instructions.
- Declines use fixed wording, not model-written text, so they are always one short polite line.

### Classification (Q&A)

- One short call to the visitor's model returns a label (factual, philosophical or ambiguous) and a confidence. Low confidence becomes ambiguous.
- The eval set measures this. The accuracy bar and which mistakes matter most are your decisions.

### Writing answers and stories

- The model is given the chosen passages as reference material, plus rules: plain modern English, third person for stories, no verdicts in its own voice, no events that are not in the passages, difficult scenes told plainly at the level of the source.
- The model returns its text and the ids of the passages it used.
- **Citations are built by our code from those passage ids.** The parva, section and the excerpt are taken word for word from the stored passage. This means a citation cannot name a section that does not exist, and an excerpt is always genuine.
- If a passage id returned by the model does not exist, the citation is dropped and the answer is checked again.
- **Ambiguous questions:** the first reply is two sentences, one per reading, each cited. "Tell me more" runs a second, wider search and writes the fuller content.
- **Tell me more (other answers):** same second search, fuller answer.

### Story mode

- A **catalogue file** lists the Featured Characters and the 18 parvas. Each entry points to the sections that support stories about it. It is built with the ingestion script and reviewed by hand, so no story is offered that the text cannot support.
- A story request retrieves the matching passages and writes a snippet of about 150 words.
- "Tell me more" continues with the next passages in order. "I already know this one" picks a different story cluster on the same subject.
- "Surprise me" picks from the catalogue, skipping stories already shown in this session.

### Conversation memory (in the browser only)

- The recent exchanges (the last three, to start) and the list of shown stories are kept in the visitor's browser tab, as with the key. They are sent with each request and used only to answer that request.
- Closing the tab clears them. The server keeps nothing, which satisfies the privacy requirement.

### Protecting the service

- **Request limit:** a per-visitor limit on answer and story requests, based on the visitor's network address, separate from the key-validation limit. The numbers are set at build time (open item).
- **Logs** contain counts and error types only. No question text, no keys, no passage text.

## Data Models

### Passage

- `parva` — the site's spelling of the parva name (for example "Santi").
- `section` — the plain, corrected section number.
- `passage_id` — unique id within the parva/section.
- `text` — the passage text, `[1]`-style footnote markers removed, word for word from the source otherwise.

### Citation

- `parva`, `section`, `excerpt` — all copied directly from a stored Passage by `passage_id`, never generated by the model.

### Catalogue entry (story mode)

- `subject` — a Featured Character or a Parva.
- `section_refs` — the sections that support stories about the subject.

### Session context (browser-held, never stored server-side)

- `recent_exchanges` — the last three question/answer pairs, this tab only.
- `shown_stories` — story subjects already presented this session.
- `provider_key`, `provider`, `model` — as defined in the entry-screen spec.

## Correctness Properties

### Property 1: Citations are derived, not generated

Every citation's `parva`, `section` and `excerpt` come from a stored Passage; no citation field is ever model-generated text.

**Validates: Requirements 6.1, 6.2, 6.3** (qa-mode Citations; story-mode 6.4 Citation with every Snippet; source-and-guardrails 2 Coverage and Citable Structure)

### Property 2: A missing passage id never reaches the reply

If the model references a `passage_id` that does not exist in the index, that citation is dropped and the answer is rechecked before reply — it is never shown as-is.

**Validates: Requirements 6.1, 6.2, 6.3** (qa-mode Citations; source-and-guardrails 2 Coverage and Citable Structure)

### Property 3: The build fails closed

If any of the 18 parvas is missing from the completeness report, the build stops rather than shipping a partial index.

**Validates: Requirements 2.1, 2.2** (source-and-guardrails Coverage and Citable Structure — all 18 parvas)

### Property 4: The re-ranker setting is isolated

Switching the re-ranker setting changes only the search step's output ordering; it changes no other component's behaviour.

**Validates: Requirements 11.1, 10.1** (qa-mode 11.1 and story-mode 10.1, both Loading and Failure States — toggling this setting must not change these behaviours)

### Property 5: Scope check precedes cost

The scope check runs before any search or model call, so an out-of-scope request never reaches the search or writing steps.

**Validates: Requirements 5.1, 5.2, 5.3, 9.1** (source-and-guardrails Scope and Request Rate Limiting)

### Property 6: Logs carry no sensitive content

No request text, key, or passage text appears in logs — only counts and error types.

**Validates: Requirements 10.1, 10.2** (source-and-guardrails Privacy of Requests)

### Property 7: Session context never leaves the browser

Session context (recent exchanges, shown stories, key) lives only in the browser tab and is never persisted or logged server-side.

**Validates: Requirements 8.1, 8.2, 8.3, 10.1, 10.2** (qa-mode 8.1–8.3 Follow-Up Questions/Session Context; story-mode 8.1–8.4 Shown Stories Memory; source-and-guardrails 10.1–10.2 Privacy of Requests)

## Error Handling

- **Passage id not found:** drop the citation, recheck the answer against the remaining valid citations before replying.
- **Low-confidence classification:** treated as ambiguous rather than guessed as factual or philosophical.
- **No matching story or Q&A answer in the source text:** say so plainly and suggest two or three related topics/stories, rather than inventing content.
- **Provider auth error during a real request:** follow the entry-screen handling — invalidate the key, reopen the key window, keep the pending request.
- **Provider rate-limit error during a real request:** follow the entry-screen handling — inline message, Retry with the same key, Add/change key.
- **Any other failure while answering or telling a story:** inline error, offer Retry, keep the pending request.
- **Source file breaks the expected ingestion pattern** (no "Footnotes" heading, an unconvertible section marker): flagged by the completeness report rather than silently ingested.

## Testing Strategy

- Run every query in the eval set with the re-ranker off and record the result: classification, decline or answer, whether a verdict was given (rows 21, 22, 35), and the timing of the search step.
- Run every query again with the re-ranker on and record the same things.
- Build a table of expected against actual for each pass and count the confusions.
- Compare the two passes side by side: does the re-ranker change enough answers to be worth its extra time? This comparison decides the launch setting, recorded in `docs/decision-log.md`.
- Spot-check 20 answers against their cited sections: does the retelling say what the excerpt supports?
- Check that every citation points to a real section (an automatic test).

## Open items

- Where the built index lives so the live server can load it (a release file downloaded at build time is one option).
- Passage size and the number of passages given to the model.
- The scope-check word list and its strictness.
- The request-rate numbers.
- The accuracy bar for classification.
- Whether the re-ranker stays on for launch, decided by the off-vs-on comparison above.
- Exact model choices for search, re-ranking and the list of Featured Characters.
