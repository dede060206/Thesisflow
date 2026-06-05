# Thesisflow

Thesisflow turns long-form venture writing into structured Chinese research briefs.

It aggregates selected English-language articles from Andreessen Horowitz, Sequoia,
Benchmark, Lightspeed, Y Combinator, NFX, Redpoint, and Bessemer, stores them in
Postgres, generates OpenAI summaries, and serves a FastAPI/Jinja web frontend.

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

Run the web app:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run the ingestion worker:

```bash
python scripts/worker.py
```

## Routes

- `/`: homepage
- `/search?q=AI`: search articles
- `/category/{category}`: category page
- `/article/{id}`: article detail
- `/daily`: articles fetched today
- `/insight/{id}`: weekly category insight detail
- `/api/articles`: JSON article API

There is intentionally no public update endpoint. Ingestion runs through
`scripts/worker.py`.
