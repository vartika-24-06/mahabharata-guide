"""
Task 6 (part 1): local BM25 keyword index.

Builds a keyword index over the real passages using BM25 - cheap enough
(no model, no framework overhead) to stay self-hosted, unlike the
meaning-based side which moved to an external embeddings API + Supabase
(see build_supabase_index.py and answering-engine/design.md's "Revision
note").

The index is saved as a pickle the live server loads at startup. It is
small: BM25's state is just token statistics over the corpus, not a
learned model, so it carries none of the memory overhead that forced
the embedding model off this server.
"""
import json
import os
import pickle
import re
import time
import psutil
from pathlib import Path
from rank_bm25 import BM25Okapi

BACKEND_DIR = Path(__file__).parent
PASSAGES_PATH = BACKEND_DIR.parent / "data_processed" / "passages.jsonl"
OUT_PATH = BACKEND_DIR.parent / "data_processed" / "bm25_index.pkl"

TOKEN_RE = re.compile(r"[a-zA-Z']+")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def mem_mb() -> float:
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)


def main():
    print(f"Baseline memory: {mem_mb():.2f} MB")

    print(f"Reading real passages from {PASSAGES_PATH} ...")
    passages = []
    with open(PASSAGES_PATH) as f:
        for line in f:
            passages.append(json.loads(line))
    print(f"Loaded {len(passages)} passages.")

    print("Tokenizing and building BM25 index...")
    t0 = time.perf_counter()
    tokenized_corpus = [tokenize(p["text"]) for p in passages]
    bm25 = BM25Okapi(tokenized_corpus)
    build_time = time.perf_counter() - t0
    mem_after_build = mem_mb()

    print(f"Built in {build_time:.2f}s. Memory after build: {mem_after_build:.2f} MB")

    # Save index + minimal metadata needed to map a result back to a passage
    with open(OUT_PATH, "wb") as f:
        pickle.dump({
            "bm25": bm25,
            "meta": [
                {k: p[k] for k in ("parva_file", "book_number", "parva_name", "section", "passage_index")}
                for p in passages
            ],
        }, f)

    index_size_mb = OUT_PATH.stat().st_size / (1024 * 1024)
    print(f"Saved index to {OUT_PATH} ({index_size_mb:.2f} MB on disk)")

    # Sanity-check search
    sample_question = "What was Arjuna's role in the Kurukshetra war?"
    t0 = time.perf_counter()
    scores = bm25.get_scores(tokenize(sample_question))
    top5_idx = scores.argsort()[::-1][:5]
    search_time = (time.perf_counter() - t0) * 1000
    mem_final = mem_mb()

    print(f"\nSample search took {search_time:.2f} ms")
    print("Top 5 BM25 matches:")
    for idx in top5_idx:
        p = passages[idx]
        print(f"  Book {p['book_number']} ({p['parva_name']}), Section {p['section']}: "
              f"{p['text'][:100]}...  (score {scores[idx]:.3f})")

    print(f"\nFinal memory: {mem_final:.2f} MB")

    summary = {
        "passage_count": len(passages),
        "build_time_s": round(build_time, 2),
        "memory_after_build_mb": round(mem_after_build, 2),
        "index_size_on_disk_mb": round(index_size_mb, 2),
        "sample_search_time_ms": round(search_time, 2),
        "memory_final_mb": round(mem_final, 2),
    }
    with open(BACKEND_DIR.parent / "data_processed" / "bm25_report.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary: {json.dumps(summary, indent=2)}")
    return summary


if __name__ == "__main__":
    main()
