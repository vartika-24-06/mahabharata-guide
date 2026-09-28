import os
import sys
import time
import numpy as np
import torch
import psutil

# Add backend directory to path
sys.path.insert(0, os.path.dirname(__file__))

from transformers import AutoTokenizer
from optimum.onnxruntime import ORTModelForFeatureExtraction, ORTModelForSequenceClassification, ORTQuantizer
from optimum.onnxruntime.configuration import AutoQuantizationConfig
from timing_utils import cosine_similarity, get_process_memory_mb
from main import DUMMY_PASSAGES, SAMPLE_QUESTION

ONNX_DIR = os.path.join(os.path.dirname(__file__), "onnx_models")
EMBED_EXPORT_PATH = os.path.join(ONNX_DIR, "embed_fp32")
EMBED_QUANT_PATH = os.path.join(ONNX_DIR, "embed_int8")
RERANK_EXPORT_PATH = os.path.join(ONNX_DIR, "rerank_fp32")
RERANK_QUANT_PATH = os.path.join(ONNX_DIR, "rerank_int8")

def export_and_quantize_models():
    os.makedirs(ONNX_DIR, exist_ok=True)
    
    # 1. Export & Quantize Embedding Model
    if not os.path.exists(os.path.join(EMBED_QUANT_PATH, "model_quantized.onnx")):
        print("Exporting & Quantizing Embedding Model (all-MiniLM-L6-v2)...")
        tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
        model = ORTModelForFeatureExtraction.from_pretrained("sentence-transformers/all-MiniLM-L6-v2", export=True)
        model.save_pretrained(EMBED_EXPORT_PATH)
        tokenizer.save_pretrained(EMBED_EXPORT_PATH)
        tokenizer.save_pretrained(EMBED_QUANT_PATH)
        
        quantizer = ORTQuantizer.from_pretrained(model)
        qconfig = AutoQuantizationConfig.avx2(is_static=False)
        quantizer.quantize(save_dir=EMBED_QUANT_PATH, quantization_config=qconfig)
        print("Embedding model quantized successfully.")

    # 2. Export & Quantize Re-ranker Model
    if not os.path.exists(os.path.join(RERANK_QUANT_PATH, "model_quantized.onnx")):
        print("Exporting & Quantizing Re-ranker Model (ms-marco-MiniLM-L-6-v2)...")
        tokenizer = AutoTokenizer.from_pretrained("cross-encoder/ms-marco-MiniLM-L-6-v2")
        model = ORTModelForSequenceClassification.from_pretrained("cross-encoder/ms-marco-MiniLM-L-6-v2", export=True)
        model.save_pretrained(RERANK_EXPORT_PATH)
        tokenizer.save_pretrained(RERANK_EXPORT_PATH)
        tokenizer.save_pretrained(RERANK_QUANT_PATH)
        
        quantizer = ORTQuantizer.from_pretrained(model)
        qconfig = AutoQuantizationConfig.avx2(is_static=False)
        quantizer.quantize(save_dir=RERANK_QUANT_PATH, quantization_config=qconfig)
        print("Re-ranker model quantized successfully.")

def encode_onnx(model, tokenizer, texts: list[str]) -> np.ndarray:
    inputs = tokenizer(texts, padding=True, truncation=True, return_tensors="pt")
    outputs = model(**inputs)
    token_embeddings = outputs.last_hidden_state
    attention_mask = inputs["attention_mask"].unsqueeze(-1)
    sum_embeddings = torch.sum(token_embeddings * attention_mask, dim=1)
    sum_mask = torch.clamp(attention_mask.sum(dim=1), min=1e-9)
    embeddings = (sum_embeddings / sum_mask).detach().numpy()
    norm = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norm[norm == 0] = 1e-10
    return embeddings / norm

def predict_rerank_onnx(model, tokenizer, question: str, passages: list[str]) -> np.ndarray:
    inputs = tokenizer([question] * len(passages), passages, padding=True, truncation=True, return_tensors="pt")
    outputs = model(**inputs)
    return outputs.logits.squeeze(-1).detach().numpy()

def run_onnx_benchmark(num_runs: int = 5):
    print("--- Starting ONNX Runtime + INT8 Quantization Feasibility Test ---")
    export_and_quantize_models()

    mem_before_load = get_process_memory_mb()
    print(f"Memory before model loading: {mem_before_load:.2f} MB")

    print("Loading quantized ONNX embedding model...")
    embed_tokenizer = AutoTokenizer.from_pretrained(EMBED_QUANT_PATH)
    embed_model = ORTModelForFeatureExtraction.from_pretrained(EMBED_QUANT_PATH, file_name="model_quantized.onnx")

    print("Loading quantized ONNX re-ranker model...")
    rerank_tokenizer = AutoTokenizer.from_pretrained(RERANK_QUANT_PATH)
    rerank_model = ORTModelForSequenceClassification.from_pretrained(RERANK_QUANT_PATH, file_name="model_quantized.onnx")

    idle_memory_mb = get_process_memory_mb()
    peak_memory_mb = idle_memory_mb
    print(f"Idle memory (ONNX INT8 models loaded): {idle_memory_mb:.2f} MB")

    timings_a = []
    timings_b = []
    timings_c = []

    print(f"\nRunning ONNX benchmark ({num_runs} runs)...")
    for _ in range(num_runs):
        peak_memory_mb = max(peak_memory_mb, get_process_memory_mb())

        # (a) Generating passage embeddings
        t0 = time.perf_counter()
        passage_embeddings = encode_onnx(embed_model, embed_tokenizer, DUMMY_PASSAGES)
        t1 = time.perf_counter()
        timings_a.append((t1 - t0) * 1000.0)

        peak_memory_mb = max(peak_memory_mb, get_process_memory_mb())

        # (b) Search & score with re-ranker OFF
        t0 = time.perf_counter()
        q_embedding = encode_onnx(embed_model, embed_tokenizer, [SAMPLE_QUESTION])
        scores_b = cosine_similarity(q_embedding, passage_embeddings)[0]
        ranked_b = sorted(zip(DUMMY_PASSAGES, scores_b), key=lambda x: x[1], reverse=True)
        t1 = time.perf_counter()
        timings_b.append((t1 - t0) * 1000.0)

        peak_memory_mb = max(peak_memory_mb, get_process_memory_mb())

        # (c) Search & score with re-ranker ON
        t0 = time.perf_counter()
        q_embedding = encode_onnx(embed_model, embed_tokenizer, [SAMPLE_QUESTION])
        scores_dense = cosine_similarity(q_embedding, passage_embeddings)[0]
        top_candidates = [DUMMY_PASSAGES[i] for i in np.argsort(scores_dense)[::-1]]
        rerank_scores = predict_rerank_onnx(rerank_model, rerank_tokenizer, SAMPLE_QUESTION, top_candidates)
        ranked_c = sorted(zip(top_candidates, rerank_scores), key=lambda x: x[1], reverse=True)
        t1 = time.perf_counter()
        timings_c.append((t1 - t0) * 1000.0)

        peak_memory_mb = max(peak_memory_mb, get_process_memory_mb())

    results = {
        "runs": num_runs,
        "idle_memory_mb": round(idle_memory_mb, 2),
        "peak_memory_mb": round(peak_memory_mb, 2),
        "timing_a_passage_embeddings_avg_ms": round(float(np.mean(timings_a)), 2),
        "timing_b_reranker_off_avg_ms": round(float(np.mean(timings_b)), 2),
        "timing_c_reranker_on_avg_ms": round(float(np.mean(timings_c)), 2),
    }

    print("\n--- ONNX + INT8 Quantization Benchmark Results ---")
    print(f"Idle Memory: {results['idle_memory_mb']} MB")
    print(f"Peak Memory: {results['peak_memory_mb']} MB")
    print(f"(a) Passage Embeddings avg time: {results['timing_a_passage_embeddings_avg_ms']} ms")
    print(f"(b) Search & score (Re-ranker OFF) avg time: {results['timing_b_reranker_off_avg_ms']} ms")
    print(f"(c) Search & score (Re-ranker ON) avg time: {results['timing_c_reranker_on_avg_ms']} ms")

    return results

if __name__ == "__main__":
    run_onnx_benchmark()
