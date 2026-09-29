"""
Task 6 (part 2): embed every real passage via Gemini's embeddings API
(our own server-side key) and push them into Supabase (pgvector).

Run this from your own machine, after:
1. Creating the Supabase project and enabling the "vector" extension.
2. Running supabase_schema.sql in the Supabase SQL Editor.
3. Setting these three values, either as real environment variables or
   in a backend/.env file (gitignored, never commit it):
   GEMINI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY

Install first:
    pip install google-generativeai supabase python-dotenv

Embeds in batches (one API call per BATCH_SIZE passages, not one call
per passage) to stay fast. Safe to interrupt and re-run: it checks how
many rows are already in Supabase and picks up from there instead of
starting over, as long as you don't change BATCH_SIZE or the passage
file between runs.
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

BATCH_SIZE = 20               # passages embedded per API call (and per Supabase insert)
PAUSE_BETWEEN_BATCHES = 3.0   # seconds - adjust down if your quota allows, up if you hit 429s


def get_embeddings_batch(genai_client, texts: list[str]) -> list[list[float]]:
    """Embeds a whole batch of texts in a single API call. If this errors,
    the exact method/model name may have changed since this was written -
    check https://ai.google.dev/gemini-api/docs/embeddings for the current
    API and adjust here; the rest of the script doesn't need to change.

    NOTE: gemini-embedding-001's free tier quota is currently showing as 0
    for many developers (a known, acknowledged Google-side issue as of
    late 2025/2026), even on fresh API keys. text-embedding-004 has been
    fully retired and isn't available at all. gemini-embedding-2 is the
    newer model that still works on the free tier. It defaults to a
    larger vector size, so output_dimensionality is pinned to 768 to
    match the schema in supabase_schema.sql.

    Retries with backoff on 429 (rate limit) errors instead of crashing -
    free-tier per-minute limits are tight on this model, but they reset
    quickly, so waiting it out is normal and expected here."""
    from google.api_core.exceptions import ResourceExhausted

    max_attempts = 6
    for attempt in range(1, max_attempts + 1):
        try:
            result = genai_client.embed_content(
                model="models/gemini-embedding-2",
                content=texts,
                output_dimensionality=768,
            )
            break
        except ResourceExhausted:
            if attempt == max_attempts:
                raise
            wait_s = 15 * attempt
            print(f"  ...rate-limited, waiting {wait_s}s before retrying "
                  f"(attempt {attempt}/{max_attempts})")
            time.sleep(wait_s)
    embedding = result["embedding"]
    # Some SDK versions return a single flat list when content has only
    # one item instead of a list-of-lists - normalize that case.
    if texts and len(texts) == 1 and embedding and isinstance(embedding[0], float):
        return [embedding]
    return embedding


def insert_with_retry(supabase, rows, max_attempts=4):
    """Inserts a batch of rows, retrying on transient network drops
    (connection resets, timeouts) instead of losing the whole run."""
    for attempt in range(1, max_attempts + 1):
        try:
            supabase.table("passages").insert(rows).execute()
            return
        except Exception as exc:
            if attempt == max_attempts:
                raise
            wait_s = 10 * attempt
            print(f"  ...insert failed ({exc.__class__.__name__}), retrying "
                  f"in {wait_s}s (attempt {attempt}/{max_attempts})")
            time.sleep(wait_s)


def main():
    gemini_key = os.environ.get("GEMINI_API_KEY")
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not all([gemini_key, supabase_url, supabase_key]):
        raise SystemExit(
            "Missing one of GEMINI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY "
            "environment variables/.env values. Set all three before running this."
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
    print(f"Loaded {len(passages)} passages.")

    # Resume support: count rows already pushed and skip that many, since
    # passages are always inserted in file order.
    existing = supabase.table("passages").select("id", count="exact").execute()
    already_pushed = existing.count or 0
    if already_pushed:
        print(f"Found {already_pushed} rows already in Supabase - resuming from there.")
    remaining = passages[already_pushed:]
    if not remaining:
        print("Nothing left to push - all passages are already in Supabase.")
        return

    print(f"Embedding and pushing {len(remaining)} remaining passages...")
    total_pushed = already_pushed
    t_start = time.perf_counter()

    for batch_start in range(0, len(remaining), BATCH_SIZE):
        batch = remaining[batch_start:batch_start + BATCH_SIZE]
        texts = [p["text"] for p in batch]
        embeddings = get_embeddings_batch(genai, texts)

        rows = [
            {
                "parva_file": p["parva_file"],
                "book_number": p["book_number"],
                "parva_name": p["parva_name"],
                "section": p["section"],
                "passage_index": p["passage_index"],
                "text": p["text"],
                "embedding": emb,
            }
            for p, emb in zip(batch, embeddings)
        ]
        insert_with_retry(supabase, rows)
        total_pushed += len(rows)

        elapsed = time.perf_counter() - t_start
        print(f"  ...pushed {total_pushed}/{len(passages)} "
              f"({elapsed:.0f}s elapsed this run)")

        time.sleep(PAUSE_BETWEEN_BATCHES)

    elapsed = time.perf_counter() - t_start
    print(f"\nDone. {total_pushed}/{len(passages)} passages now in Supabase "
          f"({elapsed:.0f}s this run).")
    print("Next: run the ivfflat index-creation line in supabase_schema.sql "
          "(it's commented out there - uncomment and run it now that the "
          "table is populated).")


if __name__ == "__main__":
    main()
