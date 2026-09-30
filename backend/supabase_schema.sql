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
-- AFTER push_to_supabase.py has inserted all passages, not before.
-- create index on passages using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- Example similarity query the backend will run at request time
-- (replace :query_embedding with the embedded incoming question):
-- select parva_name, section, text, 1 - (embedding <=> :query_embedding) as similarity
-- from passages
-- order by embedding <=> :query_embedding
-- limit 8;
