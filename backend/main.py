import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request

import guardrails
import qna_endpoint
import rate_limit
import scope
import search
import story_endpoint

BACKEND_DIR = Path(__file__).parent
CATALOGUE_PATH = BACKEND_DIR.parent / "data_processed" / "catalogue.json"

try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / ".env")
except ImportError:
    pass

resources = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Loading BM25 keyword index...")
    resources["bm25_index"] = search.load_bm25_index()

    print("Loading story catalogue...")
    if not CATALOGUE_PATH.exists():
        raise SystemExit(
            f"Story catalogue not found at {CATALOGUE_PATH}. Run "
            "'python build_catalogue.py' from backend/ first (it reads "
            "data_processed/passages.jsonl, same as build_bm25_index.py)."
        )
    with open(CATALOGUE_PATH) as f:
        resources["catalogue"] = json.load(f)

    print("Connecting to Supabase and OpenAI (our own embeddings key)...")
    import openai
    from supabase import create_client

    resources["openai_client"] = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resources["supabase_client"] = create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    )
    print("Startup complete - no ML model loaded in this process "
          "(see docs/hosting-notes.md for why).")
    yield
    resources.clear()


app = FastAPI(title="Mahabharata Guide API", lifespan=lifespan)


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "bm25_loaded": "bm25_index" in resources,
        "catalogue_loaded": "catalogue" in resources,
        "supabase_connected": "supabase_client" in resources,
    }


@app.post("/api/ask")
async def ask(request: Request, body: qna_endpoint.AskRequest):
    """Task 13: the real Q&A endpoint. See qna_endpoint.py for the full
    pipeline (rate limit -> guardrails -> scope -> search -> classify ->
    answer -> citations) and the header/error contract it follows."""
    return await qna_endpoint.handle_ask(request, body, resources)


@app.post("/api/story")
async def tell_story(request: Request, body: story_endpoint.StoryRequest):
    """Task 15: the real Story endpoint. See story_endpoint.py for the
    request_type branches (typed/character/parva/surprise/continue/
    another) and the episode model it uses."""
    return await story_endpoint.handle_story(request, body, resources)
