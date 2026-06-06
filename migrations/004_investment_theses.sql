CREATE TABLE IF NOT EXISTS investment_theses (
    id BIGSERIAL PRIMARY KEY,
    workspace_id UUID NOT NULL,
    title TEXT NOT NULL,
    core_claim TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'developed', 'memo_ready')),
    generated_sections JSONB NOT NULL DEFAULT '{}'::jsonb,
    investment_memo TEXT,
    analysis_model TEXT,
    memo_model TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_investment_theses_workspace_updated
ON investment_theses (workspace_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS thesis_evidence (
    id BIGSERIAL PRIMARY KEY,
    thesis_id BIGINT NOT NULL REFERENCES investment_theses(id) ON DELETE CASCADE,
    evidence_type TEXT NOT NULL
        CHECK (evidence_type IN ('article', 'chat', 'comparison', 'weekly_signal', 'manual')),
    article_id BIGINT REFERENCES articles(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    source TEXT,
    url TEXT,
    published_at TIMESTAMPTZ,
    excerpt TEXT NOT NULL,
    note TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_thesis_evidence_thesis
ON thesis_evidence (thesis_id, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_thesis_evidence_unique_article
ON thesis_evidence (thesis_id, article_id)
WHERE article_id IS NOT NULL;
