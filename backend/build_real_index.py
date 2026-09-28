"""
Task 6 (build indexes) + production-scale memory measurement.

Loads the ONNX+INT8-quantized embedding model (matching the "production
launch config" from the earlier toy benchmark: embedding model only, no
re-ranker loaded), embeds every real passage from data_processed/passages.jsonl,
and measures memory before/after the model loads and before/after the full
real index is held in memory - the number the free-tier hosting decision
actually depends on.
"""
import json
import os
import time
import psutil
import numpy as np
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
PASSAGES_PATH = BACKEND_DIR.parent / "data_processed" / "passages.jsonl"


def mem_mb() -> float:
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)


def main():
    print(f"Baseline process memory (Python + libs imported): {mem_mb():.2f} MB")

    from sentence_transformers import SentenceTransformer

    print("\nLoading sentence-transformers/all-MiniLM-L6-v2 with ONNX backend + int8 quantization...")
    t0 = time.perf_counter()
    model = SentenceTransformer(
        "sentence-transformers/all-MiniLM-L6-v2",
        backend="onnx",
        model_kwargs={"file_name": "onnx/model_qint8_avx512.onnx"},
    )
    load_time = time.perf_counter() - t0
    mem_after_model = mem_mb()
    print(f"Model loaded in {load_time:.2f}s. Memory after model load: {mem_after_model:.2f} MB")

    print(f"\nReading real passages from {PASSAGES_PATH} ...")
    passages = []
    with open(PASSAGES_PATH) as f:
        for line in f:
            passages.append(json.loads(line))
    texts = [p["text"] for p in passages]
    print(f"Loaded {len(texts)} real passages, {sum(len(t.split()) for t in texts)} words total.")

    print("\nEmbedding all real passages (this is the actual build-time index step)...")
    t0 = time.perf_counter()
    batch_size = 64
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        emb = model.encode(batch, convert_to_numpy=True, show_progress_bar=False)
        all_embeddings.append(emb)
        if i % (batch_size * 20) == 0:
            print(f"  ...{i}/{len(texts)} passages embedded, memory now {mem_mb():.2f} MB")
    embeddings = np.vstack(all_embeddings)
    embed_time = time.perf_counter() - t0
    mem_after_index = mem_mb()

    print(f"\nEmbedded {len(texts)} passages in {embed_time:.2f}s ({embed_time/len(texts)*1000:.2f} ms/passage)")
    print(f"Embeddings array shape: {embeddings.shape}, dtype: {embeddings.dtype}, "
          f"raw size: {embeddings.nbytes / (1024*1024):.2f} MB")
    print(f"Memory with model + full real index held in memory: {mem_after_index:.2f} MB")

    # Save the index for reuse (and so this doesn't need re-running)
    out_dir = BACKEND_DIR.parent / "data_processed"
    np.save(out_dir / "embeddings.npy", embeddings)
    with open(out_dir / "passage_meta.jsonl", "w") as f:
        for p in passages:
            f.write(json.dumps({k: p[k] for k in ("parva_file", "book_number", "parva_name", "section", "passage_index")}) + "\n")

    # Sample search to confirm the index works and to time a real query
    sample_question = "What was Arjuna's role in the Kurukshetra war?"
    t0 = time.perf_counter()
    q_emb = model.encode([sample_question], convert_to_numpy=True)
    norms_p = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms_p[norms_p == 0] = 1e-10
    norm_q = np.linalg.norm(q_emb, axis=1, keepdims=True)
    sims = (embeddings / norms_p) @ (q_emb / norm_q).T
    top5_idx = np.argsort(sims[:, 0])[::-1][:5]
    search_time = (time.perf_counter() - t0) * 1000
    mem_final = mem_mb()

    print(f"\nSample search over all {len(texts)} real passages took {search_time:.2f} ms")
    print("Top 5 matches:")
    for idx in top5_idx:
        p = passages[idx]
        print(f"  Book {p['book_number']} ({p['parva_name']}), Section {p['section']}: "
              f"{p['text'][:100]}...  (score {sims[idx][0]:.3f})")

    print(f"\nFinal memory (model + real index + one search executed): {mem_final:.2f} MB")

    summary = {
        "passage_count": len(texts),
        "total_words": sum(len(t.split()) for t in texts),
        "model_load_time_s": round(load_time, 2),
        "memory_after_model_load_mb": round(mem_after_model, 2),
        "embed_all_passages_time_s": round(embed_time, 2),
        "embeddings_array_mb": round(embeddings.nbytes / (1024 * 1024), 2),
        "memory_after_full_index_mb": round(mem_after_index, 2),
        "sample_search_time_ms": round(search_time, 2),
        "memory_final_mb": round(mem_final, 2),
    }
    with open(out_dir / "production_scale_memory_report.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nWrote {out_dir / 'production_scale_memory_report.json'}")
    return summary


if __name__ == "__main__":
    main()
