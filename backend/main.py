import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request

import guardrails
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


@app.get("/debug/search")
async def debug_search(request: Request, q: str, k: int = 8, has_context: bool = False):
    """Temporary manual-testing endpoint for Task 7's hybrid search,
    Task 8's scope check and Task 9's guardrails, ahead of the real Q&A
    endpoint (Task 13). Not part of the product surface - remove or gate
    this once Task 13 lands. has_context is a manual override for
    testing follow-up behavior; Task 19 (browser session context) will
    wire this up for real."""
    client_ip = rate_limit.get_client_ip(request)
    rate_ok, rate_message = rate_limit.check_rate_limit(client_ip)
    if not rate_ok:
        return {"query": q, "in_scope": False, "message": rate_message}

    guardrails_ok, guardrails_message = guardrails.check_guardrails(q)
    if not guardrails_ok:
        return {"query": q, "in_scope": False, "message": guardrails_message}

    in_scope, decline_message = scope.check_scope(q, has_context=has_context)
    if not in_scope:
        return {"query": q, "in_scope": False, "message": decline_message}

    results, degraded = search.hybrid_search(
        query=q,
        bm25_index=resources["bm25_index"],
        openai_client=resources["openai_client"],
        supabase_client=resources["supabase_client"],
        k=k,
    )
    return {
        "query": q,
        "in_scope": True,
        "meaning_search_degraded": degraded,
        "results": [
            {
                "parva_name": r["meta"]["parva_name"],
                "section": r["meta"]["section"],
                "passage_index": r["meta"]["passage_index"],
                "rrf_score": round(r["rrf_score"], 5),
                "sources": r["sources"],
                "text": r.get("text"),
            }
            for r in results
        ],
    }
