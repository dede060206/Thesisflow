# Thesisflow Deployment Plan

This document describes how to deploy Thesisflow. Do not run these steps until
deployment is approved.

## Target Architecture

- Web: Vercel Python runtime serving FastAPI from `index.py`.
- Database: Neon Postgres.
- Worker: GitHub Actions scheduled workflow running `scripts/worker.py`.

## 1. Create Neon Postgres

1. Create a Neon project.
2. Create a production database.
3. Copy the pooled Postgres connection string.
4. Use the pooled URL for serverless/web traffic when available.

Expected format:

```text
postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
```

## 2. Configure Local Environment

Create `.env` from `.env.example`:

```bash
cp .env.example .env
```

Set:

```bash
APP_NAME=Thesisflow
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4.1-mini
CHAT_MODEL=gpt-4.1-mini
WEEKLY_REPORT_MODEL=gpt-4.1-mini
WEEKLY_REPORT_BATCH_SIZE=12
THESIS_MODEL=gpt-4.1-mini
THESIS_MAX_EVIDENCE=20
THESIS_MAX_PER_WORKSPACE=25
WORKSPACE_SECRET=replace_with_a_long_random_secret
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
CHAT_TOP_K=6
ARTICLE_CHUNK_WORDS=450
ARTICLE_CHUNK_OVERLAP_WORDS=60
CRON_SECRET=replace_with_a_long_random_secret
DAILY_ARTICLE_LIMIT=8
DAILY_MAX_CANDIDATE_LINKS=80
DAILY_MAX_PAGES_FETCHED=30
DAILY_MAX_ARTICLES_SUMMARIZED=8
DAILY_MIN_QUALITY_SCORE=7
DAILY_MAX_PER_SOURCE=3
DAILY_MAX_RECURSION_DEPTH=1
DAILY_RETRY_ATTEMPTS=3
DAILY_RETRY_BASE_SECONDS=2
LONG_FORM_WORD_THRESHOLD=1000
MIN_ARTICLE_DATE=2025-06-01
MAX_ARTICLE_AGE_DAYS=15
TOP_READS_MAX_AGE_DAYS=7
```

## 3. Run Migrations

```bash
python scripts/migrate.py
```

This creates:

- `schema_migrations`
- `articles`
- `article_chunks`
- `weekly_category_insights`
- `weekly_market_reports`
- `investment_theses`
- `thesis_evidence`
- `ingestion_runs`

Migration `002_article_chunks.sql` enables Neon's `vector` extension.

## 4. Run One Manual Worker Pass

If you want to preserve old local MVP data, import SQLite first:

```bash
python scripts/import_sqlite_to_postgres.py --dry-run
python scripts/import_sqlite_to_postgres.py
```

The import script reads `data/vc_blogs.sqlite3`, runs Postgres migrations, and
uses unique keys to skip duplicate article URLs and duplicate weekly insights.

Then run one worker pass:

```bash
python scripts/worker.py
```

For an existing database, index previously imported articles:

```bash
python scripts/backfill_embeddings.py --limit 500
```

Use this once before enabling scheduled ingestion to verify:

- article fetching works
- OpenAI summarization works
- rows are written to Neon
- the web app can read articles

## 5. Deploy Web to Vercel

1. Import the repository into Vercel.
2. Use the Python runtime configuration in `vercel.json`.
3. Set Vercel environment variables:

```bash
APP_NAME=Thesisflow
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4.1-mini
CHAT_MODEL=gpt-4.1-mini
WEEKLY_REPORT_MODEL=gpt-4.1-mini
WEEKLY_REPORT_BATCH_SIZE=12
THESIS_MODEL=gpt-4.1-mini
THESIS_MAX_EVIDENCE=20
THESIS_MAX_PER_WORKSPACE=25
WORKSPACE_SECRET=replace_with_a_long_random_secret
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
CHAT_TOP_K=6
DAILY_ARTICLE_LIMIT=8
LONG_FORM_WORD_THRESHOLD=1000
MIN_ARTICLE_DATE=2025-06-01
MAX_ARTICLE_AGE_DAYS=15
TOP_READS_MAX_AGE_DAYS=7
```

`OPENAI_API_KEY` is required by AI Chat, Investor Comparison, and Thesis Builder.
Store it as a Vercel secret; it is used only by the server-side Python function
and is never sent to the browser.
`WORKSPACE_SECRET` must be a strong Vercel secret. Changing it invalidates all
existing anonymous Thesis Builder workspace cookies.

4. Deploy.
5. Verify:

```text
/
/api/articles
/search?q=AI
/category/AI
/chat
/compare
/weekly
/theses
/theses/new
```

## 6. Configure GitHub Actions Worker

Add repository secrets:

```text
DATABASE_URL
OPENAI_API_KEY
```

Optional repository variables:

```text
OPENAI_MODEL
WEEKLY_REPORT_MODEL
WEEKLY_REPORT_BATCH_SIZE
EMBEDDING_MODEL
EMBEDDING_DIMENSIONS
ARTICLE_CHUNK_WORDS
ARTICLE_CHUNK_OVERLAP_WORDS
DAILY_ARTICLE_LIMIT
LONG_FORM_WORD_THRESHOLD
MIN_ARTICLE_DATE
MAX_ARTICLE_AGE_DAYS
TOP_READS_MAX_AGE_DAYS
```

Optional repository secret for Slack-, Discord-, or webhook-compatible failure
notifications:

```text
INGESTION_ALERT_WEBHOOK_URL
```

The daily production limits are fixed in the workflow and do not depend on
repository variables:

```text
max_candidate_links=80
max_pages_fetched=30
max_articles_summarized=8
max_per_source=3
```

The workflow is defined at:

```text
.github/workflows/daily-ingestion.yml
```

It runs daily at `08:00 UTC` and can also be run manually from GitHub Actions.
Each run applies pending migrations, writes accepted articles and summaries to
the configured `DATABASE_URL`, stores a structured row in `ingestion_runs`, and
uploads the JSON run report as a GitHub Actions artifact retained for 30 days.
Transient fetch and OpenAI failures are retried three times with exponential
backoff. A fatal failure marks the database run as failed, fails the Actions job,
and sends the optional webhook notification.
On Mondays it generates the previous complete week's comprehensive market report.
It no longer generates per-category weekly summaries.

Backfill a specific report period with:

```bash
python scripts/generate_weekly_report.py --week-start 2026-06-01 --week-end 2026-06-07
```

## 7. Rollback

If web deployment fails:

1. Revert the Vercel deployment to the previous production deployment.
2. Disable the GitHub Actions schedule.
3. Keep the Neon database intact.

If worker ingestion fails:

1. Disable the workflow schedule.
2. Check GitHub Actions logs.
3. Run locally with the same environment variables:

```bash
python scripts/worker.py
```

## Notes

- The web app has no public update endpoint.
- The web app does not run migrations on startup.
- The web app does not start background threads.
- The worker owns all ingestion and summarization work.
