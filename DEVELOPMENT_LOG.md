# Development Log

## 2026-06-05

### Current Branch

- `production-prep`

### Product Name

- Product renamed to `Thesisflow`.
- Header brand now shows `Thesisflow`.
- Homepage slogan:
  - `在资本的长文里，读懂技术与市场的暗流。`

### Current Local Runtime

- Local server command:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- Local browser URL:

```text
http://127.0.0.1:8000
```

- Health check:

```text
http://127.0.0.1:8000/health
```

### Database State

- Storage has migrated from SQLite to Postgres.
- Local `.env` now contains `DATABASE_URL` for Neon Postgres.
- Old SQLite source file remains local:

```text
data/vc_blogs.sqlite3
```

- Imported from SQLite to Neon:
  - `44` articles
  - `8` weekly category insights

- Current production filters show fewer than total imported rows when articles do not meet eligibility rules.

### Important Commands Already Run

```bash
python scripts/migrate.py
python scripts/import_sqlite_to_postgres.py
```

Import result:

```text
Inserted articles: 44
Inserted weekly insights: 8
```

Verification result:

```text
/             200
/category/AI 200
/api/articles 200
```

### Production Prep Completed

- Replaced SQLite app storage with Postgres access via `DATABASE_URL`.
- Added migrations in `migrations/`.
- Added migration runner:

```text
scripts/migrate.py
```

- Added standalone ingestion worker:

```text
scripts/worker.py
```

- Added SQLite-to-Postgres importer:

```text
scripts/import_sqlite_to_postgres.py
```

- Removed public update endpoint:

```text
POST /api/update
```

- Removed web background scheduler.
- Added Vercel entrypoint:

```text
index.py
```

- Added Vercel config:

```text
vercel.json
```

- Added GitHub Actions worker:

```text
.github/workflows/daily-ingestion.yml
```

- Added deployment docs:

```text
DEPLOYMENT.md
ARCHITECTURE.md
```

### Next Deployment Steps

1. Push the `production-prep` branch to GitHub when ready.
2. Add GitHub repository secrets:

```text
DATABASE_URL
OPENAI_API_KEY
```

3. Add optional GitHub variables:

```text
OPENAI_MODEL
DAILY_ARTICLE_LIMIT
LONG_FORM_WORD_THRESHOLD
MIN_ARTICLE_DATE
MAX_ARTICLE_AGE_DAYS
TOP_READS_MAX_AGE_DAYS
```

4. Import the repo into Vercel.
5. Add Vercel environment variables from `DEPLOYMENT.md`.
6. Deploy web on Vercel.
7. Run GitHub Actions worker manually once.
8. Verify:

```text
/
/api/articles
/search?q=AI
/category/AI
```

### Notes

- Do not expose `OPENAI_API_KEY` in frontend/runtime unless a web route actually needs OpenAI.
- Web app should remain read-focused.
- Ingestion and summarization should stay in the worker.
- No cloud deployment has been performed from this environment.
