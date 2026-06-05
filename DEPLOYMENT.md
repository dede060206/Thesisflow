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
CRON_SECRET=replace_with_a_long_random_secret
DAILY_ARTICLE_LIMIT=20
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
- `weekly_category_insights`

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
OPENAI_MODEL=gpt-4.1-mini
DAILY_ARTICLE_LIMIT=20
LONG_FORM_WORD_THRESHOLD=1000
MIN_ARTICLE_DATE=2025-06-01
MAX_ARTICLE_AGE_DAYS=15
TOP_READS_MAX_AGE_DAYS=7
```

`OPENAI_API_KEY` is not required by the web app unless future web routes call
OpenAI directly. Keep it out of Vercel unless needed.

4. Deploy.
5. Verify:

```text
/
/api/articles
/search?q=AI
/category/AI
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
DAILY_ARTICLE_LIMIT
LONG_FORM_WORD_THRESHOLD
MIN_ARTICLE_DATE
MAX_ARTICLE_AGE_DAYS
TOP_READS_MAX_AGE_DAYS
```

The workflow is defined at:

```text
.github/workflows/daily-ingestion.yml
```

It runs daily at `08:00 UTC` and can also be run manually from GitHub Actions.

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
