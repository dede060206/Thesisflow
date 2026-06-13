ALTER TABLE articles
ADD COLUMN IF NOT EXISTS recency_score SMALLINT;

ALTER TABLE articles
ADD COLUMN IF NOT EXISTS trusted_source BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE articles
ADD COLUMN IF NOT EXISTS source_tier TEXT NOT NULL DEFAULT 'standard';

ALTER TABLE articles
ADD COLUMN IF NOT EXISTS extraction_failure_reason TEXT;

ALTER TABLE articles
DROP CONSTRAINT IF EXISTS articles_recency_score_check;

ALTER TABLE articles
ADD CONSTRAINT articles_recency_score_check CHECK (
    recency_score IS NULL OR recency_score BETWEEN 1 AND 10
);

ALTER TABLE articles
DROP CONSTRAINT IF EXISTS articles_source_tier_check;

ALTER TABLE articles
ADD CONSTRAINT articles_source_tier_check CHECK (
    source_tier IN ('trusted', 'standard')
);

CREATE INDEX IF NOT EXISTS idx_articles_recency_quality
ON articles (recency_score DESC, quality_score DESC);
