import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request

import guardrails
import qna_endpoint
import rate_limit
import scope
import search

BACKEND_DIR = Path(__file__).parent

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
        "supabase_connected": "supabase_client" in resources,
    }


@app.post("/api/ask")
async def ask(request: Request, body: qna_endpoint.AskRequest):
    """Task 13: the real Q&A endpoint. See qna_endpoint.py for the full
    pipeline (rate limit -> guardrails -> scope -> search -> classify ->
    answer -> citations) and the header/error contract it follows."""
    return await qna_endpoint.handle_ask(request, body, resources)
