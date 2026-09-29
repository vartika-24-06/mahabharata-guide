"""
Task 6 (part 2): embed every real passage via Gemini's embeddings API
(our own server-side key) and push them into Supabase (pgvector).

Run this ONCE, from your own machine, after:
1. Creating the Supabase project and enabling the "vector" extension.
2. Running supabase_schema.sql in the Supabase SQL Editor.
3. Setting these three environment variables (never commit them):
   GEMINI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY

Install first:
    pip install google-generativeai supabase

This calls the embeddings API ~5,578 times (once per passage), with a
short pause between batches to stay well under free-tier rate limits.
It will take a while - that's expected for a one-time build step.
"""
import json
import os
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
PASSAGES_PATH = BACKEND_DIR.parent / "data_processed" / "passages.jsonl"

# Load GEMINI_API_KEY / SUPABASE_URL / SUPABASE_SERVICE_KEY from a local
# backend/.env file if one exists (it's gitignored - never commit it).
# Falls back to real environment variables if no .env file is present.
try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / ".env")
except ImportError:
    pass

BATCH_SIZE = 20          # passages embedded per batch
PAUSE_BETWEEN_BATCHES = 2.0   # seconds - adjust down if your quota allows, up if you hit 429s
SUPABASE_INSERT_BATCH = 100   # rows per Supabase insert call


def get_embedding(genai_client, text: str) -> list[float]:
    """Wraps the embeddings call. If this errors, the exact method/model
    name may have changed since this was written - check
    https://ai.google.dev/gemini-api/docs/embeddings for the current API
    and adjust here; the rest of the script doesn't need to change."""
    # NOTE: gemini-embedding-001's free tier quota is currently showing as 0
    # for many developers (a known, acknowledged Google-side issue as of
    # late 2025/2026), even on fresh API keys. text-embedding-004 is the
    # confirmed-working free-tier alternative and outputs the same
    # 768-dimension vectors this schema expects.
    result = genai_client.embed_content(
        model="models/text-embedding-004",
        content=text,
    )
    return result["embedding"]


def main():
    gemini_key = os.environ.get("GEMINI_API_KEY")
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not all([gemini_key, supabase_url, supabase_key]):
        raise SystemExit(
            "Missing one of GEMINI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY "
            "environment variables. Set all three before running this."
        )

    import google.generativeai as genai
    from supabase import create_client

    genai.configure(api_key=gemini_key)
    supabase = create_client(supabase_url, supabase_key)

    print(f"Reading real passages from {PASSAGES_PATH} ...")
    passages = []
    with open(PASSAGES_PATH) as f:
        for line in f:
            passages.append(json.loads(line))
    print(f"Loaded {len(passages)} passages. Embedding and pushing to Supabase...")

    rows_buffer = []
    total_pushed = 0
    t_start = time.perf_counter()

    for i, p in enumerate(passages):
        embedding = get_embedding(genai, p["text"])
        rows_buffer.append({
            "parva_file": p["parva_file"],
            "book_number": p["book_number"],
            "parva_name": p["parva_name"],
            "section": p["section"],
            "passage_index": p["passage_index"],
            "text": p["text"],
            "embedding": embedding,
        })

        if len(rows_buffer) >= SUPABASE_INSERT_BATCH:
            supabase.table("passages").insert(rows_buffer).execute()
            total_pushed += len(rows_buffer)
            rows_buffer = []
            elapsed = time.perf_counter() - t_start
            print(f"  ...pushed {total_pushed}/{len(passages)} "
                  f"({elapsed:.0f}s elapsed)")

        if (i + 1) % BATCH_SIZE == 0:
            time.sleep(PAUSE_BETWEEN_BATCHES)

    if rows_buffer:
        supabase.table("passages").insert(rows_buffer).execute()
        total_pushed += len(rows_buffer)

    elapsed = time.perf_counter() - t_start
    print(f"\nDone. Pushed {total_pushed} passages to Supabase in {elapsed:.0f}s.")
    print("Next: run the ivfflat index-creation line in supabase_schema.sql "
          "(it's commented out there - uncomment and run it now that the "
          "table is populated).")


if __name__ == "__main__":
    main()
