# Thesisflow

Thesisflow turns long-form venture writing into structured Chinese research briefs.

It aggregates selected English-language articles from Andreessen Horowitz, Sequoia,
Benchmark, Lightspeed, Y Combinator, NFX, Redpoint, and Bessemer, stores them in
Postgres, generates OpenAI summaries, and serves a FastAPI/Jinja web frontend.
It also supports stateless AI research chat grounded in article excerpts, with
clickable citations to original publications.

## Local Setup

```bash
cd /Users/taoyucheng/Desktop/econometrics/vc_blog_mvp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set:

```bash
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
OPENAI_API_KEY=your_openai_api_key
```

Run migrations:

```bash
python scripts/migrate.py
```

Import the old local SQLite data into Postgres after `DATABASE_URL` is set:

```bash
python scripts/import_sqlite_to_postgres.py --dry-run
python scripts/import_sqlite_to_postgres.py
```

Run the web app:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run the ingestion worker:

```bash
python scripts/worker.py
```

Test the controlled daily policy without fetching article pages, calling OpenAI,
or writing database rows:

```bash
python scripts/daily_ingestion.py --dry-run
```

Run it manually after reviewing the dry-run candidate report:

```bash
python scripts/daily_ingestion.py
```

The controlled policy is connected to the scheduled GitHub Actions worker. It
runs with fixed production limits of 80 discovered candidates, 30 fetched pages,
and 8 generated summaries, with at most 3 summaries per source.

The worker generates one comprehensive report every Monday for the previous
Monday-to-Sunday period. Backfill a specific period with:

```bash
python scripts/generate_weekly_report.py --week-start 2026-06-01 --week-end 2026-06-07
```

Index existing articles after applying the pgvector migration:

```bash
python scripts/backfill_embeddings.py --limit 500
```

## Routes

- `/`: homepage
- `/search?q=AI`: search articles
- `/category/{category}`: category page
- `/article/{id}`: article detail
- `/daily`: articles fetched today
- `/insight/{id}`: weekly category insight detail
- `/chat`: AI research chat with sources
- `/api/chat`: cited chat API
- `/compare`: compare investor views on one topic
- `/api/compare`: structured investor comparison API
- `/weekly`: latest comprehensive weekly market report
- `/theses`: saved investment theses for the current anonymous workspace
- `/theses/new`: create a thesis from a core claim
- `/api/articles`: JSON article API

Thesis Builder uses a signed anonymous browser cookie instead of user accounts.
Clearing browser cookies removes access to that browser's saved thesis workspace.

There is intentionally no public update endpoint. Ingestion runs through
`scripts/worker.py`.
