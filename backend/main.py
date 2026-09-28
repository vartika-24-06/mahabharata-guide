from contextlib import asynccontextmanager
from fastapi import FastAPI
from sentence_transformers import SentenceTransformer, CrossEncoder
from timing_utils import benchmark_search_pipeline, get_process_memory_mb

# Global model references
models = {}

DUMMY_PASSAGES = [
    "The Mahabharata is one of the two major Sanskrit epics of ancient India, narrated by the sage Vyasa. It details the struggle between two groups of cousins in the Kurukshetra War.",
    "Arjuna was the third of the five Pandava brothers, renowned for his unrivaled archery skills and commitment to righteousness. He played a central role in defeating the Kaurava army.",
    "Lord Krishna served as Arjuna's divine charioteer during the great Kurukshetra war and imparted the eternal spiritual wisdom of the Bhagavad Gita on the battlefield.",
    "Yudhishthira, the eldest Pandava prince, was famous for his strict adherence to truth and righteousness, earning him the title of Dharma-raja.",
    "Bhishma was the grand sire of both Pandavas and Kauravas, bound by a formidable vow of celibacy and lifetime loyalty to the throne of Hastinapura.",
    "Karna was a tragic hero and legendary archer known for his boundless generosity, loyalty to Duryodhana, and possession of divine armor.",
    "Draupadi was the common wife of the five Pandava brothers, born from a sacred altar fire, whose insult in the Kaurava court sparked the epic feud.",
    "Duryodhana was the crown prince of Hastinapura and the chief antagonist among the one hundred Kaurava brothers who fought fiercely against the Pandavas.",
    "The Kurukshetra War lasted eighteen days on the sacred field of Kurukshetra, resulting in immense carnage and the downfall of numerous ancient dynasties.",
    "Abhimanyu, the courageous son of Arjuna and Subhadra, heroically penetrated the complex Chakravyuha formation before being overwhelmed by enemy warriors."
]

SAMPLE_QUESTION = "What was Arjuna's role in the Kurukshetra war?"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load embedding model and re-ranker on startup
    print("Loading embedding model (sentence-transformers/all-MiniLM-L6-v2)...")
    models["embedder"] = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    print("Loading re-ranker model (cross-encoder/ms-marco-MiniLM-L-6-v2)...")
    models["reranker"] = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    models["idle_memory_mb"] = get_process_memory_mb()
    print(f"Models loaded successfully. Idle memory: {models['idle_memory_mb']:.2f} MB")
    yield
    models.clear()

app = FastAPI(title="Mahabharata Guide API", lifespan=lifespan)

@app.get("/health")
async def health_check():
    return {"status": "ok", "models_loaded": "embedder" in models and "reranker" in models}

# Temporary test endpoint disabled after recording feasibility benchmark metrics
FEASIBILITY_TEST_ENABLED = False

@app.get("/test-feasibility")
async def test_feasibility():
    if not FEASIBILITY_TEST_ENABLED:
        return {"error": "Feasibility test endpoint is disabled."}
    
    embedder = models.get("embedder")
    reranker = models.get("reranker")
    
    if not embedder or not reranker:
        return {"error": "Models not loaded."}
        
    results = benchmark_search_pipeline(
        embedder=embedder,
        reranker=reranker,
        passages=DUMMY_PASSAGES,
        question=SAMPLE_QUESTION,
        num_runs=5
    )
    return results
