ALTER TABLE investment_theses
    ADD COLUMN IF NOT EXISTS domain TEXT,
    ADD COLUMN IF NOT EXISTS research_question TEXT,
    ADD COLUMN IF NOT EXISTS initial_view TEXT;

ALTER TABLE thesis_evidence
    DROP CONSTRAINT IF EXISTS thesis_evidence_evidence_type_check;

ALTER TABLE thesis_evidence
    ADD CONSTRAINT thesis_evidence_evidence_type_check
    CHECK (evidence_type IN (
        'article', 'chat', 'comparison', 'weekly_signal',
        'company_research', 'manual'
    ));

ALTER TABLE thesis_evidence
    ADD COLUMN IF NOT EXISTS classification TEXT NOT NULL DEFAULT 'CONTEXT'
        CHECK (classification IN ('SUPPORTING', 'COUNTER', 'CONTEXT')),
    ADD COLUMN IF NOT EXISTS strength TEXT NOT NULL DEFAULT 'medium'
        CHECK (strength IN ('high', 'medium', 'low')),
    ADD COLUMN IF NOT EXISTS source_credibility TEXT NOT NULL DEFAULT 'medium'
        CHECK (source_credibility IN ('high', 'medium', 'low')),
    ADD COLUMN IF NOT EXISTS ai_recommendation TEXT NOT NULL DEFAULT 'consider'
        CHECK (ai_recommendation IN ('prioritise', 'consider', 'low_priority')),
    ADD COLUMN IF NOT EXISTS evidence_state TEXT NOT NULL DEFAULT 'added'
        CHECK (evidence_state IN ('added', 'saved_for_later'));

CREATE INDEX IF NOT EXISTS idx_thesis_evidence_state
ON thesis_evidence (thesis_id, evidence_state, created_at);
