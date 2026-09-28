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
* **Recommended Next Steps for Production Hosting**:
  1. **ONNX / Quantized Models**: Export models to ONNX int8 format to reduce memory footprint below 250 MB.
  2. **Lazy Loading / External Vector DB**: Offload embeddings to a vector DB service (e.g., Qdrant / Pinecone) or external inference API.
  3. **Tier Upgrade**: Upgrade Render instance to Starter tier (1 GB RAM) or utilize HuggingFace Inference Endpoints / Modal for model hosting.
