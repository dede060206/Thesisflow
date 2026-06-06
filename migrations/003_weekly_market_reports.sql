CREATE TABLE IF NOT EXISTS weekly_market_reports (
    id BIGSERIAL PRIMARY KEY,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    report JSONB NOT NULL,
    citations JSONB NOT NULL,
    source_article_ids BIGINT[] NOT NULL DEFAULT '{}',
    article_count INTEGER NOT NULL,
    investor_count INTEGER NOT NULL,
    model TEXT,
    report_version INTEGER NOT NULL DEFAULT 1,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (week_start)
);

CREATE INDEX IF NOT EXISTS idx_weekly_market_reports_week_start
ON weekly_market_reports (week_start DESC);
