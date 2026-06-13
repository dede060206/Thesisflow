CREATE TABLE IF NOT EXISTS ingestion_runs (
    id BIGSERIAL PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    dry_run BOOLEAN NOT NULL DEFAULT FALSE,
    preview BOOLEAN NOT NULL DEFAULT FALSE,
    limits JSONB NOT NULL DEFAULT '{}'::jsonb,
    report JSONB,
    error_message TEXT,
    workflow_run_url TEXT
);

CREATE INDEX IF NOT EXISTS ingestion_runs_started_at_idx
    ON ingestion_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS ingestion_runs_status_idx
    ON ingestion_runs (status, started_at DESC);
