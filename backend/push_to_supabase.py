"""
Task 6 (part 2): embed every real passage via OpenAI's embeddings API
(our own server-side key) and push them into Supabase (pgvector).

Run this from your own machine, after:
1. Creating the Supabase project and enabling the "vector" extension.
2. Running supabase_schema.sql in the Supabase SQL Editor.
3. Setting these three values, either as real environment variables or
   in a backend/.env file (gitignored, never commit it):
   OPENAI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY

Install first:
    pip install openai supabase python-dotenv

Embeds in batches (one API call per BATCH_SIZE passages, not one call
per passage) to stay fast. Safe to interrupt and re-run: it checks how
many rows are already in Supabase and picks up from there instead of
starting over, as long as you don't change BATCH_SIZE or the passage
file between runs.

IMPORTANT: switched from Gemini to OpenAI for embeddings (see
docs/decision-log.md) because Gemini's free tier caps at 1,000
embedding requests/day and Google Cloud billing in some regions forces
a large minimum prepaid top-up, disproportionate to this corpus's real
cost (~$0.07 on OpenAI's text-embedding-3-small). Embeddings from
different models are NOT comparable in the same vector search, so if
any rows were already pushed using Gemini embeddings, truncate the
table first:
    truncate table passages;
(run that in the Supabase SQL Editor before running this script, so
every row in the table comes from the same embedding model.)
"""
import json
import os
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
PASSAGES_PATH = BACKEND_DIR.parent / "data_processed" / "passages.jsonl"

# Load OPENAI_API_KEY / SUPABASE_URL / SUPABASE_SERVICE_KEY from a local
# backend/.env file if one exists (it's gitignored - never commit it).
# Falls back to real environment variables if no .env file is present.
try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / ".env")
except ImportError:
    pass

BATCH_SIZE = 100              # passages embedded per API call (and per Supabase insert)
PAUSE_BETWEEN_BATCHES = 0.5   # seconds - adjust down if your quota allows, up if you hit 429s


def get_embeddings_batch(openai_client, texts: list[str]) -> list[list[float]]:
    """Embeds a whole batch of texts in a single API call. If this errors,
    the exact method/model name may have changed since this was written -
    check https://platform.openai.com/docs/guides/embeddings for the
    current API and adjust here; the rest of the script doesn't need to
    change.

    text-embedding-3-small supports a `dimensions` parameter to truncate
    its native embedding down to a smaller size - pinned to 768 here to
    match the schema in supabase_schema.sql.

    Retries with backoff on 429 (rate limit) errors instead of crashing."""
    import openai

    max_attempts = 6
    for attempt in range(1, max_attempts + 1):
        try:
            result = openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=texts,
                dimensions=768,
            )
            return [item.embedding for item in result.data]
        except openai.RateLimitError:
            if attempt == max_attempts:
                raise
            wait_s = 15 * attempt
            print(f"  ...rate-limited, waiting {wait_s}s before retrying "
                  f"(attempt {attempt}/{max_attempts})")
            time.sleep(wait_s)


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
    openai_key = os.environ.get("OPENAI_API_KEY")
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not all([openai_key, supabase_url, supabase_key]):
        raise SystemExit(
            "Missing one of OPENAI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY "
            "environment variables/.env values. Set all three before running this."
        )

    import openai
    from supabase import create_client

    openai_client = openai.OpenAI(api_key=openai_key)
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
        embeddings = get_embeddings_batch(openai_client, texts)

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
