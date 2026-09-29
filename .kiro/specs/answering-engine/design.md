# Design Document: Answering Engine

## Overview

This design covers the shared machinery behind Q&A mode, story mode and the guardrails: preparing the Ganguli text, searching it, checking scope, classifying questions, writing answers and stories, building citations, and protecting the service. It is written to be read by a product owner. Technical choices are explained by what they mean for the product.

It sits behind the entry screen. The entry screen and key handling are covered in the entry-screen spec. Requirements are in three specs: Q&A mode, story mode, and source and guardrails.

**Revision note:** this design originally self-hosted an embedding model and a re-ranker model on the same server as the FastAPI app. Real measurement against the full corpus (5,578 passages, all 18 parvas) showed that configuration costs ~700MB of memory just to hold the models — over Render's free 512MB plan even before considering the re-ranker, and even after trying ONNX/int8 quantization (which only closed about 13% of the gap). Rather than pay for a bigger host or cut hybrid search from v1, this revision moves to an architecture with no ML model running on our own server at all: an external embeddings API plus a managed vector store. Everything below reflects that revision; the old self-hosted numbers are kept in `docs/hosting-notes.md` as a record of what was tried.

## Architecture

### The path of one request

1. **Scope check.** Is this about the Mahabharata (or a follow-up in a conversation)? If not, decline in one polite line. This happens before any search, so off-topic requests cost almost nothing.
2. **Rate-limit check.** Has this visitor made too many requests? If so, say how long to wait.
3. **Classify** (Q&A only). Factual, philosophical or ambiguous.
4. **Search** the prepared text: keyword search and meaning-based search together.
5. **Write** the answer or story in plain modern English, using the visitor's own key.
6. **Build citations from the passages**, not from what the model wrote.
7. **Reply.**

No request text is kept on the server after the reply.

### Search architecture

- **Keyword search** finds exact names and terms (for example "Shikhandi"), using a lightweight local BM25 index — small enough that it carries none of the memory cost that models do, so it stays self-hosted.
- **Meaning-based search** finds passages on the same idea in different words (for example "loyalty despite doubt"). It no longer runs a model on our server at all:
  1. The incoming question is embedded by calling an external embeddings API (Gemini's `gemini-embedding-001` or equivalent), using **our own server-side key**, not the visitor's.
  2. The resulting vector is compared against passage embeddings held in a managed vector store (Supabase, using its pgvector extension), which returns the closest passages by a SQL query — no model load, no local vector math over the full corpus.
  3. Passage embeddings themselves are computed once, the same way, at build time (Task 6), and written into Supabase — never recomputed live.
- The two result lists (keyword, meaning-based) are merged by rank.
- **A re-ranker is deferred, not just switched off.** The earlier design planned a self-hosted cross-encoder re-ranker with an on/off setting. Since any self-hosted transformer model carries the same large memory overhead that forced this whole revision, re-ranking is out of v1 entirely rather than "off by default" — bringing it back later needs its own hosting decision (an external re-ranking API, or a paid host), not just flipping a setting. See "Open items."

### Hosting reality

- **Render's free plan gives 512 MB of memory.** With no ML model loaded in the FastAPI process — the change this revision makes — the app's own memory footprint is just FastAPI, a small BM25 index, and Supabase/Gemini API client libraries, comfortably inside that budget. The corpus's own data was never the problem (all 5,578 real passage embeddings together are only ~8MB); it was always the model runtime overhead, and this revision removes that overhead by not running a model here at all.
- **What was tried before this revision, for the record** (full numbers in `docs/hosting-notes.md`): self-hosted PyTorch embedding + re-ranker models together cost ~643MB idle / ~669MB peak on a toy 10-passage test; ONNX+int8 quantization brought that to ~562MB/~597MB; embedding-only (no re-ranker) toy test was ~498MB/~515MB; the same embedding-only setup against the **real** 5,578-passage corpus came to ~590MB model-load / ~703MB with the full index and one search executed. All of these are over the 512MB cap; none of the self-hosting variants tried actually fit.
- **The first request after idle still takes about a minute** on Render's free plan (unrelated to the model question). The entry-screen design already accounts for this: the first request after idle waits up to ~75 seconds and shows "Waking up the server."
- **No self-pinging to stay awake.** Render may suspend services for abnormal self-generated traffic; warm the server by hand before a demo, or use a paid plan if this becomes a problem.

## Components and Interfaces

### Text preparation (done once, before launch)

- The text comes from one download: the parva-wise text files (mahatxt.zip) offered by sacred-texts.com. It is downloaded once by hand or by a single request, never by collecting pages one at a time. The site's terms allow one copy of one text per day for robots and forbid repeated high-speed access.
- Each parva is one file. Its header gives the book number, the parva name and a credit line. The parva label for every passage comes from this header. The credit line stays in the stored copy, as the site's terms ask, but is kept out of search and answers.
- **Two section-marker formats exist across the 18 files, confirmed by parsing the real files** (not assumed): 11 books (1–7, 12–15) mark sections with `SECTION <ROMAN NUMERAL>`; the other 7 (Karna, Shalya, Sauptika, Stri, Mausala, Mahaprasthanika, Svargarohanika parvas — books 8, 9, 10, 11, 16, 17, 18) use a bare arabic number alone on its own line instead. The ingestion script detects which style a file uses and parses accordingly.
- **Footnotes only exist in the 11 roman-style books.** The 7 arabic-style books have no "Footnotes" heading at all — confirmed genuine, not a parse miss. Where a Footnotes heading exists, everything from it onward is cut off and kept in the stored copy but not used for search or answers in v1. The `[1]`-style markers in the body text are removed from passages, so excerpts are word for word apart from those markers.
- The site's published errata (Book 1 sections 176/177, Book 2 section 67, Book 7 sections 54/55/189, Book 13's two 168s) are real, but **parsing the actual files turns up substantially more numbering gaps and duplicates than the site's own errata page documents** — full table in `docs/source-notes.md`. The completeness report (below) treats these as expected, logged findings, not build-stopping errors, since they're a property of the original translation/scan, not something a build step can fix.
- Each section is cut into passages of roughly a few hundred words. Every passage carries its parva, section number and passage number.
- A **completeness report** confirms no whole parva is missing (hard fail if so) and logs every numbering gap/duplicate found per book as an informational finding. It also flags any file that breaks the expected pattern entirely, for example an unrecognised section-marker style.
- **Citations name each parva as the source site spells it** (for example Santi, Anusasana, Aswamedha, Asramavasika — confirmed against the real file headers) and number sections the way the site's pages do, with corrections applied where documented. Common alternative spellings are recognised in incoming questions.
- **The About notice** links to sacred-texts.com and carries the credit line. The site's terms allow this use for non-commercial purposes; if the App were ever to charge, a licence would be needed first.
- A keyword (BM25) index is built locally from the passages. Passage embeddings are computed via the external embeddings API (using our own key, at build time) and written to Supabase.
- The downloaded text is kept out of git. The BM25 index is small enough to build at startup or ship alongside the app; passage embeddings live in Supabase, not in git.

### Meaning-based search (external embeddings + managed vector store)

- **Our own server-side embeddings key** (not the visitor's) calls the embeddings API to embed: (a) every passage, once, at build time, and (b) the incoming question, on every Q&A/story request that needs meaning-based search.
- This key is never sent to the browser and never logged — same handling as the entry-screen design already applies to provider keys, just for a key we hold rather than one the visitor supplies.
- **Supabase (pgvector)** stores one row per passage: `parva`, `section`, `passage_id`, `text`, `embedding`. A similarity query against the incoming question's embedding returns the closest passages directly from the database — no vector math or model held in our own process.
- **Cost and abuse exposure:** because this key is ours, its usage cost is bounded by the same per-visitor request-rate limit that already exists for abuse protection (see "Protecting the service") — every embedding call happens inside an already-rate-limited request path, so this doesn't need a second, separate limit, but it does mean that limit is now also protecting our own budget, not just service health.
- **If the embeddings API call fails or rate-limits** (our own key, not the visitor's), the request falls back to keyword-only search for that one request rather than failing outright — see "Error Handling."

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

- **Request limit:** a per-visitor limit on answer and story requests, based on the visitor's network address, separate from the key-validation limit. The numbers are set at build time (open item). This limit now also caps how often our own embeddings key can be called per visitor, not just abuse of the visitor-facing endpoints.
- **Logs** contain counts and error types only. No question text, no keys (ours or the visitor's), no passage text.

## Data Models

### Passage (stored in Supabase)

- `parva` — the site's spelling of the parva name (for example "Santi").
- `section` — the plain, corrected section number.
- `passage_id` — unique id within the parva/section.
- `text` — the passage text, `[1]`-style footnote markers removed, word for word from the source otherwise.
- `embedding` — the vector produced by the embeddings API at build time, stored via pgvector.

### Citation

- `parva`, `section`, `excerpt` — all copied directly from a stored Passage by `passage_id`, never generated by the model.

### Catalogue entry (story mode)

- `subject` — a Featured Character or a Parva.
- `section_refs` — the sections that support stories about the subject.

### Session context (browser-held, never stored server-side)

- `recent_exchanges` — the last three question/answer pairs, this tab only.
- `shown_stories` — story subjects already presented this session.
- `provider_key`, `provider`, `model` — as defined in the entry-screen spec. Distinct from our own server-side embeddings key below.

### Server-side embeddings key (ours, not the visitor's)

- Held server-side only (environment variable / secret store), never sent to the browser, never logged.
- Used only for embedding calls (build-time passage embeddings, live-time question embeddings) — never for generation, classification, or anything the visitor's own key already covers.

## Correctness Properties

### Property 1: Citations are derived, not generated

Every citation's `parva`, `section` and `excerpt` come from a stored Passage; no citation field is ever model-generated text.

**Validates: Requirements 6.1, 6.2, 6.3** (qa-mode Citations; story-mode 6.4 Citation with every Snippet; source-and-guardrails 2 Coverage and Citable Structure)

### Property 2: A missing passage id never reaches the reply

If the model references a `passage_id` that does not exist in the index, that citation is dropped and the answer is rechecked before reply — it is never shown as-is.

**Validates: Requirements 6.1, 6.2, 6.3** (qa-mode Citations; source-and-guardrails 2 Coverage and Citable Structure)

### Property 3: The build fails closed on structure, not on known irregularities

The build stops only if a whole parva is missing or a file breaks the expected ingestion pattern — never on the documented numbering gaps/duplicates found in the real files, which are logged instead.

**Validates: Requirements 2.1, 2.2** (source-and-guardrails Coverage and Citable Structure — all 18 parvas)

### Property 4: Our embeddings key is isolated from the visitor's key

The server-side embeddings key is never sent to the browser, never logged, and never used for anything other than embedding calls; the visitor's own key is never used for embeddings.

**Validates: Requirements 10.1, 10.2** (source-and-guardrails Privacy of Requests) and the entry-screen design's key-handling guarantees, extended to a second, server-held key.

### Property 5: Scope check precedes cost

The scope check runs before any search or model call, so an out-of-scope request never reaches the search or writing steps — and, since this revision, never reaches our own embeddings key either.

**Validates: Requirements 5.1, 5.2, 5.3, 9.1** (source-and-guardrails Scope and Request Rate Limiting)

### Property 6: Logs carry no sensitive content

No request text, no keys (ours or the visitor's), and no passage text appear in logs — only counts and error types.

**Validates: Requirements 10.1, 10.2** (source-and-guardrails Privacy of Requests)

### Property 7: Session context never leaves the browser

Session context (recent exchanges, shown stories, visitor's key) lives only in the browser tab and is never persisted or logged server-side.

**Validates: Requirements 8.1, 8.2, 8.3, 10.1, 10.2** (qa-mode 8.1–8.3 Follow-Up Questions/Session Context; story-mode 8.1–8.4 Shown Stories Memory; source-and-guardrails 10.1–10.2 Privacy of Requests)

### Property 8: A meaning-based search failure degrades, it doesn't break the request

If the embeddings API call fails or is rate-limited, the request continues on keyword search alone rather than failing outright.

**Validates: Requirements 11.1, 10.1** (qa-mode 11.1, story-mode 10.1, both Loading and Failure States) — a partial, degraded answer path is preferable to no answer.

## Error Handling

- **Passage id not found:** drop the citation, recheck the answer against the remaining valid citations before replying.
- **Low-confidence classification:** treated as ambiguous rather than guessed as factual or philosophical.
- **No matching story or Q&A answer in the source text:** say so plainly and suggest two or three related topics/stories, rather than inventing content.
- **Our embeddings API call fails or rate-limits:** fall back to keyword-only search for that request; log the failure type (not the request content); the visitor still gets an answer, just from a narrower search.
- **Provider auth error during a real request (visitor's key):** follow the entry-screen handling — invalidate the key, reopen the key window, keep the pending request.
- **Provider rate-limit error during a real request (visitor's key):** follow the entry-screen handling — inline message, Retry with the same key, Add/change key.
- **Any other failure while answering or telling a story:** inline error, offer Retry, keep the pending request.
- **Source file breaks the expected ingestion pattern** (unrecognised section-marker style, or a roman-style file with no "Footnotes" heading): flagged by the completeness report rather than silently ingested.

## Testing Strategy

- Run every query in the eval set and record the result: classification, decline or answer, and whether a verdict was given (rows 21, 22, 35).
- Build a table of expected against actual and count the confusions.
- Spot-check 20 answers against their cited sections: does the retelling say what the excerpt supports?
- Check that every citation points to a real section (an automatic test).
- Test the degraded path deliberately: simulate an embeddings-API failure and confirm the request still completes on keyword search alone.
- Confirm neither key (ours or the visitor's) ever appears in a log line, across both the normal and degraded paths.

## Open items

- Provisioning Supabase (project setup, pgvector extension, connection credentials as a server-side secret) and our own embeddings-API key.
- A basic budget/usage check on our own embeddings key so a traffic spike is noticed before it becomes a real cost, even though the per-visitor rate limit already bounds it structurally.
- Passage size and the number of passages given to the model.
- The scope-check word list and its strictness.
- The request-rate numbers.
- The accuracy bar for classification.
- **Re-ranking is deferred out of v1 entirely** (see "Search architecture"). If revisited, it needs its own hosting decision — an external re-ranking API, or a paid host — not a simple on/off setting, since any self-hosted transformer model reintroduces the memory problem this revision solved.
- Exact embeddings model/API choice and the list of Featured Characters.
