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

---

## 3. Baseline PyTorch CPU Benchmarks

| Metric | Measurement |
| :--- | :--- |
| **Idle Memory (Models Loaded)** | **643.06 MB** |
| **Peak Memory (Execution)** | **669.40 MB** |
| **(a) Passage Embedding Generation (10 passages)** | **109.89 ms** |
| **(b) Search & Score (Re-ranker OFF)** | **13.18 ms** (avg over 5 runs) |
| **(c) Search & Score (Re-ranker ON)** | **125.54 ms** (avg over 5 runs) |

---

## 4. ONNX Runtime + INT8 Dynamic Quantization Benchmarks

Models were exported to ONNX format and INT8 dynamic quantization was applied using HuggingFace Optimum (`optimum[onnxruntime]`).

| Metric | PyTorch Baseline | ONNX + INT8 Quantized | Delta / Improvement |
| :--- | :--- | :--- | :--- |
| **Idle Memory (Models Loaded)** | 643.06 MB | **562.73 MB** | **-80.33 MB (-12.5%)** |
| **Peak Memory (Execution)** | 669.40 MB | **597.16 MB** | **-72.24 MB (-10.8%)** |
| **(a) Passage Embedding Generation (10 passages)** | 109.89 ms | **52.64 ms** | **2.09x faster (-52.1%)** |
| **(b) Search & Score (Re-ranker OFF)** | 13.18 ms | **4.91 ms** | **2.68x faster (-62.7%)** |
| **(c) Search & Score (Re-ranker ON)** | 125.54 ms | **67.64 ms** | **1.86x faster (-46.1%)** |

---

## 5. Render Free Plan & Hosting Analysis Side-by-Side

* **Render Free Plan RAM Limit**: 512 MB RAM.
* **Findings**:
  * **PyTorch Baseline**: Consumes 643.06 MB idle / 669.40 MB peak memory, exceeding Render's 512 MB free tier ceiling.
  * **ONNX + INT8 Quantization**: Reduces memory footprint to 562.73 MB idle / 597.16 MB peak while boosting search & re-ranking speed by ~1.86x (67.64 ms vs 125.54 ms).
  * **Feasibility Conclusion**: While ONNX + INT8 dynamic quantization significantly reduces memory usage and nearly doubles throughput, hosting both models concurrently in Python in the same process remains close to or slightly above the strict 512 MB free tier ceiling.
* **Recommended Hosting Architecture**:
  1. **Lazy Model Loading / Unloading**: Load re-ranker on-demand or separate embedding vs re-ranking endpoints.
  2. **External Vector Database**: Store pre-computed passage embeddings in Qdrant/Pinecone free tier to eliminate in-process passage embedding computation.
  3. **Render Starter / HuggingFace Spaces**: Deploy to a 1 GB RAM instance (Render Starter or HF Spaces) for zero-OOM headroom with sub-70ms search & re-rank performance.
