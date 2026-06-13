ALTER TABLE articles
ADD COLUMN IF NOT EXISTS quality_score SMALLINT;

ALTER TABLE articles
ADD COLUMN IF NOT EXISTS quality_reasoning TEXT;

ALTER TABLE articles
DROP CONSTRAINT IF EXISTS articles_quality_score_check;

ALTER TABLE articles
ADD CONSTRAINT articles_quality_score_check CHECK (
    quality_score IS NULL OR quality_score BETWEEN 1 AND 10
);

CREATE INDEX IF NOT EXISTS idx_articles_quality_score
ON articles (quality_score DESC);
