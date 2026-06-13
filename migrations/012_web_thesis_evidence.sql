ALTER TABLE thesis_evidence
    DROP CONSTRAINT IF EXISTS thesis_evidence_evidence_type_check;

ALTER TABLE thesis_evidence
    ADD CONSTRAINT thesis_evidence_evidence_type_check
    CHECK (evidence_type IN (
        'article', 'chat', 'comparison', 'weekly_signal',
        'company_research', 'manual', 'web'
    ));
