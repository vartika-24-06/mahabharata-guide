"""
Task 7: hybrid search.

Combines two independent retrieval paths and merges them by rank:
  - BM25 keyword search, self-hosted (see build_bm25_index.py) - no model,
    no external call, always available.
  - Meaning-based search: embed the question via our own OpenAI key, then
    query Supabase (pgvector) for the closest passages by cosine distance.

If the embeddings call fails or rate-limits, this falls back to
keyword-only results for that request rather than failing outright
(design.md Property 8 / Error Handling).
"""
import os
import pickle
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
BM25_INDEX_PATH = BACKEND_DIR.parent / "data_processed" / "bm25_index.pkl"

TOKEN_RE = re.compile(r"[a-zA-Z']+")
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 768


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def load_bm25_index() -> dict:
    """Loads the prebuilt BM25 index + passage metadata from disk. Call
    this once at startup (see main.py's lifespan) - it's small enough to
    hold in memory for the life of the process."""
    with open(BM25_INDEX_PATH, "rb") as f:
        return pickle.load(f)


def bm25_search(bm25_index: dict, query: str, k: int = 8) -> list[dict]:
    """Returns up to k passages ranked by BM25 score, each as
    {"meta": {...}, "rank": int, "score": float}."""
    bm25 = bm25_index["bm25"]
    meta = bm25_index["meta"]
    scores = bm25.get_scores(tokenize(query))
    top_idx = scores.argsort()[::-1][:k]
    return [
        {"meta": meta[i], "rank": rank, "score": float(scores[i])}
        for rank, i in enumerate(top_idx, start=1)
    ]


def embed_question(openai_client, question: str) -> list[float]:
    """Embeds one question using our own server-side OpenAI key - never
    the visitor's key. Same model/dimensions used at build time
    (push_to_supabase.py), since embeddings from different models or
    dimensions are not comparable."""
    result = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[question],
        dimensions=EMBEDDING_DIMENSIONS,
    )
    return result.data[0].embedding


def vector_search(supabase_client, embedding: list[float], k: int = 8) -> list[dict]:
    """Queries Supabase's match_passages() function (see
    supabase_schema.sql) for the k closest passages by cosine similarity.
    Returns them as {"meta": {...}, "rank": int, "score": float}."""
    response = supabase_client.rpc(
        "match_passages",
        {"query_embedding": embedding, "match_count": k},
    ).execute()
    return [
        {
            "meta": {
                "parva_file": row["parva_file"],
                "book_number": row["book_number"],
                "parva_name": row["parva_name"],
                "section": row["section"],
                "passage_index": row["passage_index"],
            },
            "text": row["text"],
            "rank": rank,
            "score": row["similarity"],
        }
        for rank, row in enumerate(response.data, start=1)
    ]


def _passage_key(meta: dict) -> tuple:
    """Identifies a passage uniquely across both result lists, so the
    same passage found by both searches merges into one entry instead of
    appearing twice."""
    return (meta["parva_file"], meta["section"], meta["passage_index"])


def merge_by_rank(
    bm25_results: list[dict],
    vector_results: list[dict],
    k: int = 8,
    rrf_constant: int = 60,
) -> list[dict]:
    """Merges two ranked result lists using Reciprocal Rank Fusion (RRF):
    each passage's combined score is the sum of 1/(rrf_constant + rank)
    across whichever list(s) it appears in. This only needs each list's
    rank order, not its raw scores, which is what makes it a sane way to
    combine BM25 scores (unbounded, corpus-dependent) with cosine
    similarities (bounded 0-1) - the two are not on the same scale and
    should never be averaged directly."""
    combined: dict[tuple, dict] = {}

    for result in bm25_results:
        key = _passage_key(result["meta"])
        combined.setdefault(key, {"meta": result["meta"], "rrf_score": 0.0, "sources": []})
        combined[key]["rrf_score"] += 1.0 / (rrf_constant + result["rank"])
        combined[key]["sources"].append("keyword")

    for result in vector_results:
        key = _passage_key(result["meta"])
        combined.setdefault(key, {"meta": result["meta"], "rrf_score": 0.0, "sources": []})
        combined[key]["rrf_score"] += 1.0 / (rrf_constant + result["rank"])
        combined[key]["sources"].append("meaning")
        # vector_search returns passage text directly (no separate lookup
        # needed); bm25 results only carry metadata, so prefer this copy.
        combined[key]["text"] = result["text"]

    merged = sorted(combined.values(), key=lambda r: -r["rrf_score"])
    return merged[:k]


def fill_missing_text(supabase_client, results: list[dict]) -> None:
    """A result that only came from BM25 (or every result, when the
    meaning-based search degraded) has no passage text yet - BM25's own
    index deliberately doesn't store it (see build_bm25_index.py). Looks
    each one up from Supabase, which holds every passage's text
    regardless of embedding status. Mutates results in place; leaves
    text as None (rather than raising) for anything that can't be
    fetched, so one missing passage doesn't fail the whole request."""
    for result in results:
        if "text" in result:
            continue
        meta = result["meta"]
        try:
            response = (
                supabase_client.table("passages")
                .select("text")
                .eq("parva_file", meta["parva_file"])
                .eq("section", meta["section"])
                .eq("passage_index", meta["passage_index"])
                .limit(1)
                .execute()
            )
            result["text"] = response.data[0]["text"] if response.data else None
        except Exception as exc:
            print(f"Could not fetch text for passage {meta} ({exc.__class__.__name__}); "
                  f"leaving it as None.")
            result["text"] = None


def hybrid_search(
    query: str,
    bm25_index: dict,
    openai_client,
    supabase_client,
    k: int = 20,
) -> tuple[list[dict], bool]:
    """Runs both search paths and merges them by rank. Returns
    (results, meaning_search_degraded) - the second value is True when
    the embeddings call failed/rate-limited and results are keyword-only
    for this request (design.md Property 8 / Error Handling)."""
    bm25_results = bm25_search(bm25_index, query, k=k)

    try:
        embedding = embed_question(openai_client, query)
        vector_results = vector_search(supabase_client, embedding, k=k)
        degraded = False
    except Exception as exc:
        print(f"Meaning-based search failed ({exc.__class__.__name__}: {exc}); "
              f"falling back to keyword-only search for this request.")
        vector_results = []
        degraded = True

    merged = merge_by_rank(bm25_results, vector_results, k=k)
    fill_missing_text(supabase_client, merged)

    return merged, degraded
