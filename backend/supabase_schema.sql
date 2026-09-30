-- Task 6 (part 2): Supabase schema for meaning-based search.
-- Run this once in the Supabase SQL Editor, after enabling the "vector"
-- extension (Database -> Extensions -> search "vector" -> enable).

create table if not exists passages (
    id bigint generated always as identity primary key,
    parva_file text not null,
    book_number int not null,
    parva_name text not null,
    section int not null,
    passage_index int not null,
    text text not null,
    -- text-embedding-3-small (OpenAI), truncated to 768 dimensions via
    -- the `dimensions` parameter in push_to_supabase.py; adjust this
    -- number if a different embeddings model/dimension is used.
    embedding vector(768)
);

-- Speeds up similarity search once the table is populated.
-- ivfflat needs at least a few hundred rows to build well, so run this
-- AFTER push_to_supabase.py has inserted all passages, not before. If
-- this errors with "memory required is X MB, maintenance_work_mem is
-- 32MB", run `SET maintenance_work_mem = '64MB';` first (session-only,
-- doesn't change anything permanently).
-- create index on passages using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- Task 7: the backend calls this function (via supabase-py's .rpc(),
-- see backend/search.py's vector_search()) rather than running a raw
-- SQL query - PostgREST (what supabase-py talks to) doesn't support
-- ordering by an arbitrary operator expression like `<=>` directly, so
-- the query lives here as a stored function instead. Run this once,
-- after the table exists (order relative to the ivfflat index above
-- doesn't matter).
create or replace function match_passages(
    query_embedding vector(768),
    match_count int default 8
)
returns table (
    id bigint,
    parva_file text,
    book_number int,
    parva_name text,
    section int,
    passage_index int,
    text text,
    similarity float
)
language sql stable
as $$
    select
        id, parva_file, book_number, parva_name, section, passage_index, text,
        1 - (embedding <=> query_embedding) as similarity
    from passages
    order by embedding <=> query_embedding
    limit match_count;
$$;
