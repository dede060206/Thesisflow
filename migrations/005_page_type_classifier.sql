ALTER TABLE articles
ADD COLUMN IF NOT EXISTS page_type TEXT NOT NULL DEFAULT 'ARTICLE';

ALTER TABLE articles
ADD COLUMN IF NOT EXISTS skip_reason TEXT;

ALTER TABLE articles
DROP CONSTRAINT IF EXISTS articles_page_type_check;

ALTER TABLE articles
ADD CONSTRAINT articles_page_type_check CHECK (
    page_type IN (
        'ARTICLE',
        'INDEX_PAGE',
        'AUTHOR_PAGE',
        'PODCAST_PAGE',
        'NEWSLETTER_ARCHIVE',
        'LOW_VALUE_PAGE'
    )
);

CREATE INDEX IF NOT EXISTS idx_articles_page_type
ON articles (page_type);
