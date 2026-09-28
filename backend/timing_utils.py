import time
import os
import numpy as np
import psutil

def get_process_memory_mb() -> float:
    """Returns current RSS memory usage of the process in Megabytes."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between matrix a (N, D) and matrix b (M, D)."""
    norm_a = np.linalg.norm(a, axis=1, keepdims=True)
    norm_b = np.linalg.norm(b, axis=1, keepdims=True)
    norm_a[norm_a == 0] = 1e-10
    norm_b[norm_b == 0] = 1e-10
    return np.dot(a / norm_a, (b / norm_b).T)

def benchmark_search_pipeline(
    embedder,
    reranker,
    passages: list[str],
    question: str,
    num_runs: int = 5
) -> dict:
    """
    Executes feasibility benchmark over `num_runs` runs and measures:
    (a) Generating embeddings for passages
    (b) Search & score step with re-ranker OFF (dense embedding retrieval + similarity score)
    (c) Search & score step with re-ranker ON (dense embedding + cross-encoder re-ranking)
    Also tracks idle and peak memory usage.
    """
    idle_memory_mb = get_process_memory_mb()
    peak_memory_mb = idle_memory_mb

    timings_a = []
    timings_b = []
    timings_c = []

    for _ in range(num_runs):
        # Peak memory tracking helper
        peak_memory_mb = max(peak_memory_mb, get_process_memory_mb())

        # (a) Generating passage embeddings
        t0 = time.perf_counter()
        passage_embeddings = embedder.encode(passages, convert_to_numpy=True)
        t1 = time.perf_counter()
        timings_a.append((t1 - t0) * 1000.0)

        peak_memory_mb = max(peak_memory_mb, get_process_memory_mb())

        # (b) Search & score with re-ranker OFF
        t0 = time.perf_counter()
        q_embedding = embedder.encode([question], convert_to_numpy=True)
        scores_b = cosine_similarity(q_embedding, passage_embeddings)[0]
        ranked_b = sorted(zip(passages, scores_b), key=lambda x: x[1], reverse=True)
        t1 = time.perf_counter()
        timings_b.append((t1 - t0) * 1000.0)

        peak_memory_mb = max(peak_memory_mb, get_process_memory_mb())

        # (c) Search & score with re-ranker ON
        t0 = time.perf_counter()
        # Dense stage
        q_embedding = embedder.encode([question], convert_to_numpy=True)
        scores_dense = cosine_similarity(q_embedding, passage_embeddings)[0]
        top_candidates = [passages[i] for i in np.argsort(scores_dense)[::-1]]
        # Re-ranker stage
        pairs = [[question, p] for p in top_candidates]
        rerank_scores = reranker.predict(pairs)
        ranked_c = sorted(zip(top_candidates, rerank_scores), key=lambda x: x[1], reverse=True)
        t1 = time.perf_counter()
        timings_c.append((t1 - t0) * 1000.0)

        peak_memory_mb = max(peak_memory_mb, get_process_memory_mb())

    return {
        "runs": num_runs,
        "idle_memory_mb": round(idle_memory_mb, 2),
        "peak_memory_mb": round(peak_memory_mb, 2),
        "timing_a_passage_embeddings_avg_ms": round(float(np.mean(timings_a)), 2),
        "timing_b_reranker_off_avg_ms": round(float(np.mean(timings_b)), 2),
        "timing_c_reranker_on_avg_ms": round(float(np.mean(timings_c)), 2),
    }
