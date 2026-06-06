CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS article_chunks (
    id BIGSERIAL PRIMARY KEY,
    article_id BIGINT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    word_count INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    embedding vector(1536),
    embedding_model TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (article_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_article_chunks_article_id
ON article_chunks (article_id);

CREATE INDEX IF NOT EXISTS idx_article_chunks_content_fts
ON article_chunks
USING GIN (to_tsvector('english', content));
