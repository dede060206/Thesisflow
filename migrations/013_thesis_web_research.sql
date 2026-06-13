ALTER TABLE thesis_evidence
    ADD COLUMN IF NOT EXISTS canonical_url TEXT,
    ADD COLUMN IF NOT EXISTS full_content TEXT,
    ADD COLUMN IF NOT EXISTS content_word_count INTEGER,
    ADD COLUMN IF NOT EXISTS extraction_status TEXT,
    ADD COLUMN IF NOT EXISTS fetched_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_thesis_evidence_canonical_url
ON thesis_evidence (thesis_id, canonical_url)
WHERE canonical_url IS NOT NULL;
