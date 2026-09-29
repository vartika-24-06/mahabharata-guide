# Hosting Feasibility Notes: Search & Re-ranker Models

## 1. Overview
This document records empirical performance and memory benchmarks for loading and executing dense embedding search and cross-encoder re-ranking models within the FastAPI backend application.

## 2. Tested Models & Setup
* **Embedding Model**: `sentence-transformers/all-MiniLM-L6-v2`
* **Re-ranker Model**: `cross-encoder/ms-marco-MiniLM-L-6-v2`
* **Benchmark Scenario**:
  * 10 dummy passages (2-3 sentences each on Mahabharata themes)
  * Fixed query: `"What was Arjuna's role in the Kurukshetra war?"`
  * Execution averaged over 5 consecutive runs.

## 3. Empirical Benchmark Results

| Metric | Measurement |
| :--- | :--- |
| **Idle Memory (Models Loaded)** | **643.06 MB** |
| **Peak Memory (Execution)** | **669.40 MB** |
| **(a) Passage Embedding Generation (10 passages)** | **109.89 ms** |
| **(b) Search & Score (Re-ranker OFF)** | **13.18 ms** (avg over 5 runs) |
| **(c) Search & Score (Re-ranker ON)** | **125.54 ms** (avg over 5 runs) |

## 4. Render Free Plan & Hosting Analysis
* **Render Free Plan RAM Limit**: 512 MB RAM.
* **Feasibility Findings**:
  * The full PyTorch CPU runtime alongside both `all-MiniLM-L6-v2` and `ms-marco-MiniLM-L-6-v2` models loaded concurrently consumes ~643 MB RAM at idle and up to ~669 MB at peak execution.
  * **Memory Constraint**: Exceeds Render's 512 MB free tier RAM ceiling, risking Out-Of-Memory (OOM) process termination during application startup or request handling.
  * **Latency Performance**: Execution times are excellent (13.18 ms without re-ranker, 125.54 ms with re-ranker).

## 5. ONNX + INT8 Quantization (toy 10-passage benchmark)

| Metric | PyTorch Baseline | ONNX + INT8 Quantized | Delta |
| :--- | :--- | :--- | :--- |
| Idle Memory | 643.06 MB | 562.73 MB | -12.5% |
| Peak Memory | 669.40 MB | 597.16 MB | -10.8% |
| Passage embedding (10 passages) | 109.89 ms | 52.64 ms | 2.09x faster |
| Search & score (re-ranker OFF) | 13.18 ms | 4.91 ms | 2.68x faster |
| Search & score (re-ranker ON) | 125.54 ms | 67.64 ms | 1.86x faster |

Speed was never the constraint — both configurations are far faster than any threshold that would affect a user. Memory was the constraint, and quantization alone didn't close the gap.

## 6. Embedding model only, no re-ranker loaded (toy 10-passage benchmark, production launch config)

| Metric | PyTorch (both models) | ONNX+INT8 (both models) | ONNX+INT8 (embedding only) |
| :--- | :--- | :--- | :--- |
| Idle Memory | 643.06 MB | 562.73 MB | **497.76 MB** |
| Peak Memory | 669.40 MB | 597.16 MB | **514.77 MB** |

Idle just barely cleared 512MB on the toy test; peak did not. This was still a 10-passage toy corpus, not the real one.

## 7. Real corpus (production scale) — plain PyTorch, embedding model only

Ran against the actual parsed corpus (5,578 passages, all 18 books, via `backend/ingest.py` and `backend/build_real_index.py`), not a toy sample. ONNX could not be used for this run due to an `optimum`/`transformers` version conflict on the test machine (Python 3.14); this used the plain PyTorch backend instead.

| Metric | Value |
| :--- | :--- |
| Model load time | 6.37 s |
| Memory after model load | 590.22 MB |
| Embed all 5,578 passages | 347.52 s |
| Embeddings array size | 8.17 MB (confirms the corpus itself was never the memory problem) |
| Memory with full real index held | **702.72 MB** |
| Sample search over all 5,578 passages | 56.16 ms (confirms speed was never the problem either) |
| Final memory | 703.25 MB |

**This is the number that decided the architecture.** Real-corpus memory (703MB) is worse than any toy-test number, and even applying the ~13% reduction ONNX showed in the toy test would land around ~614MB — still over the 512MB cap. Self-hosting any variant of these models was not going to fit.

## 8. Resolution: no self-hosted model at all

Rather than pay for a bigger host (Render's Starter tier is $7/mo but still only 512MB RAM — it removes sleep and adds CPU, not memory; the first tier that actually adds RAM is Standard at $25/mo for 2GB) or cut hybrid search from v1, the design moved to:

- **Embeddings**: called via an external embeddings API (our own server-side key, e.g. Gemini's `gemini-embedding-001`), both at build time (once, for every passage) and at request time (once per question needing meaning-based search).
- **Vector storage/search**: Supabase with the pgvector extension, replacing a locally-held index. A SQL query returns the closest passages; no vector math or model held in our own process.
- **Keyword search**: stays local (BM25), since it carries none of the memory cost a model does.
- **Re-ranking**: deferred out of v1 entirely, not just switched off — any self-hosted transformer model reintroduces this same problem.

With no ML model loaded in the FastAPI process, Render's free 512MB plan should be comfortable. This should still be confirmed once deployed (tasks.md Task 22).

This pattern — external embeddings API + managed vector store, no self-hosted model — was confirmed against a real comparable public project (a Harry Potter RAG app: [github.com/aarzoobhatia11/fan-out-RAG-Harry-Potter](https://github.com/aarzoobhatia11/fan-out-RAG-Harry-Potter)), which uses the same combination (Gemini embeddings + Supabase/pgvector + BYOK for generation).

**New cost consideration this introduces:** the embeddings key is ours, not the visitor's, so its usage cost falls on us rather than being deflected by BYOK. It's bounded by the same per-visitor request-rate limit already planned for abuse protection, but is worth a basic usage/budget check regardless (see design.md "Open items").

## 9. BM25 keyword index — real corpus, confirms it stays self-hosted

Built and tested locally against the real 5,578-passage corpus (`backend/build_bm25_index.py`):

| Metric | Value |
| :--- | :--- |
| Build time | 1.27 s |
| Memory after build | 246.68 MB |
| Index size on disk | 11.63 MB |
| Sample search time | 14.06 ms |

246MB comfortably fits Render's free 512MB, with headroom for the rest of the FastAPI app — confirming the keyword side of search never needed to move off our own server, only the meaning-based/embedding side did.
