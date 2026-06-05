CREATE TABLE IF NOT EXISTS articles (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    author TEXT,
    published_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ NOT NULL,
    content TEXT,
    category TEXT,
    word_count INTEGER,
    is_long_form BOOLEAN NOT NULL DEFAULT FALSE,
    summary TEXT,
    summary_model TEXT,
    summarized_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_articles_published_at
ON articles (published_at DESC);

CREATE INDEX IF NOT EXISTS idx_articles_fetched_at
ON articles (fetched_at DESC);

CREATE INDEX IF NOT EXISTS idx_articles_category
ON articles (category);

CREATE TABLE IF NOT EXISTS weekly_category_insights (
    id BIGSERIAL PRIMARY KEY,
    category TEXT NOT NULL,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    insight TEXT NOT NULL,
    summary_model TEXT,
    generated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (category, week_start)
);

CREATE INDEX IF NOT EXISTS idx_weekly_category_insights_week_start
ON weekly_category_insights (week_start DESC);
