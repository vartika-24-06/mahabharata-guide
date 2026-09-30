import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

import entry_middleware
import guardrails
import ping_endpoint
import qna_endpoint
import rate_limit
import scope
import search
import session_token
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

# Order matters: Starlette applies middleware in reverse of add order, so
# ThrottleMiddleware (added second) runs first and can short-circuit a
# throttled request before HeaderRedactionMiddleware even looks at it.
app.add_middleware(entry_middleware.HeaderRedactionMiddleware)
app.add_middleware(entry_middleware.ThrottleMiddleware)

# Entry-screen design.md's CORS section - restricts the browser to the
# deployed frontend origin(s) only. Update ALLOWED_ORIGINS with the real
# Vercel URL once deployed (Task 22 / entry-screen deploy tasks).
ALLOWED_ORIGINS = [
    "http://localhost:5173",  # local Vite dev server
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["X-Provider-Key", "X-Session-Token", "Content-Type"],
    # entry-screen tasks.md amendment (Task 9): expose Retry-After so the
    # frontend can read it off a 429 response cross-origin.
    expose_headers=["Retry-After"],
)


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "bm25_loaded": "bm25_index" in resources,
        "catalogue_loaded": "catalogue" in resources,
        "supabase_connected": "supabase_client" in resources,
    }


@app.post("/api/session-token")
async def issue_session_token():
    return {"session_token": session_token.issue_session_token()}


@app.post("/api/ping")
async def ping(request: Request, body: ping_endpoint.PingRequest):
    """Entry-screen spec: validates a visitor's API key + model with a
    minimal real completion request. See ping_endpoint.py."""
    return await ping_endpoint.handle_ping(request, body)


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
