ALTER TABLE articles
ADD COLUMN IF NOT EXISTS content_type TEXT;

ALTER TABLE articles
ADD COLUMN IF NOT EXISTS content_type_reasoning TEXT;

ALTER TABLE articles
DROP CONSTRAINT IF EXISTS articles_content_type_check;

ALTER TABLE articles
ADD CONSTRAINT articles_content_type_check CHECK (
    content_type IS NULL OR content_type IN (
        'THESIS_ARTICLE',
        'MARKET_MAP',
        'TECH_EXPLAINER',
        'COMPANY_ANALYSIS',
        'FUNDING_NEWS',
        'PRODUCT_LAUNCH',
        'OPINION',
        'PODCAST_TRANSCRIPT'
    )
);

CREATE INDEX IF NOT EXISTS idx_articles_content_type
ON articles (content_type);
