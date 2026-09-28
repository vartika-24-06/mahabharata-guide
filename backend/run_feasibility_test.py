import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.dirname(__file__))

from sentence_transformers import SentenceTransformer, CrossEncoder
from timing_utils import benchmark_search_pipeline, get_process_memory_mb
from main import DUMMY_PASSAGES, SAMPLE_QUESTION

def run_test():
    print("--- Starting Hosting Feasibility Test ---")
    mem_before_models = get_process_memory_mb()
    print(f"Initial process memory: {mem_before_models:.2f} MB")

    print("Loading embedding model (sentence-transformers/all-MiniLM-L6-v2)...")
    embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    print("Loading re-ranker model (cross-encoder/ms-marco-MiniLM-L-6-v2)...")
    reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

    idle_memory_mb = get_process_memory_mb()
    print(f"Idle memory (models loaded): {idle_memory_mb:.2f} MB")

    print("\nRunning benchmark (5 runs)...")
    benchmark_results = benchmark_search_pipeline(
        embedder=embedder,
        reranker=reranker,
        passages=DUMMY_PASSAGES,
        question=SAMPLE_QUESTION,
        num_runs=5
    )

    print("\n--- Benchmark Results ---")
    print(f"Idle Memory: {benchmark_results['idle_memory_mb']} MB")
    print(f"Peak Memory: {benchmark_results['peak_memory_mb']} MB")
    print(f"(a) Generating passage embeddings avg time: {benchmark_results['timing_a_passage_embeddings_avg_ms']} ms")
    print(f"(b) Search & score with re-ranker OFF avg time: {benchmark_results['timing_b_reranker_off_avg_ms']} ms")
    print(f"(c) Search & score with re-ranker ON avg time: {benchmark_results['timing_c_reranker_on_avg_ms']} ms")

    return benchmark_results

if __name__ == "__main__":
    run_test()
