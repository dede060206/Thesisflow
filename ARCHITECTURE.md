# Thesisflow Architecture

## Overview

Thesisflow is split into three production concerns:

- Web frontend: FastAPI + Jinja templates, deployable to Vercel.
- Database: Postgres, intended for Neon.
- Worker: standalone Python process, intended for GitHub Actions daily ingestion.

The web server does not run background schedulers and does not expose a public
update endpoint.

## Components

### Web App

Entry points:

- `index.py`: Vercel-compatible ASGI entrypoint.
- `app/main.py`: FastAPI routes and Jinja rendering.

Responsibilities:

- Render homepage, article pages, category pages, search, daily page, and weekly insight pages.
- Read article and insight data from Postgres.
- Serve static CSS from `app/static`.

Non-responsibilities:

- No scraping.
- No OpenAI summarization.
- No migrations on startup.
- No scheduler thread.

### Database

Storage is Postgres via `DATABASE_URL`.

Database access lives in:

- `app/database.py`

Migrations live in:

- `migrations/001_initial_schema.sql`

Migration runner:

- `scripts/migrate.py`

Primary tables:

- `articles`
- `weekly_category_insights`
- `schema_migrations`

### Worker

Worker entrypoint:

- `scripts/worker.py`

Responsibilities:

- Run migrations.
- Fetch long-form articles.
- Insert new articles into Postgres.
- Summarize pending articles with OpenAI.
- Generate weekly category insights.

The worker is designed for GitHub Actions or another external scheduler.

### Configuration

Required production environment variables:

- `DATABASE_URL`
- `OPENAI_API_KEY`

Recommended environment variables:

- `APP_NAME`
- `OPENAI_MODEL`
- `CRON_SECRET`
- `DAILY_ARTICLE_LIMIT`
- `LONG_FORM_WORD_THRESHOLD`
- `MIN_ARTICLE_DATE`
- `MAX_ARTICLE_AGE_DAYS`
- `TOP_READS_MAX_AGE_DAYS`

## Data Flow

1. GitHub Actions runs `python scripts/worker.py` daily.
2. Worker runs migrations against Neon Postgres.
3. Worker fetches eligible long-form articles.
4. Worker upserts articles by unique `url`.
5. Worker summarizes pending articles through OpenAI.
6. Worker generates missing weekly category insights.
7. Vercel web app reads from Postgres and renders pages.

## Production Boundary

The web app is intentionally read-heavy and request-scoped. Long network-bound
work is isolated in the worker so Vercel request timeouts and cold starts do not
affect ingestion reliability.
