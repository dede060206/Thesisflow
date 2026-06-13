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

- Render homepage, article pages, category pages, search, daily, and weekly market report pages.
- Read article and insight data from Postgres.
- Retrieve article chunks and answer cited questions at `/api/chat`.
- Serve static CSS from `app/static`.

Non-responsibilities:

- No scraping.
- No OpenAI summarization.
- No article chunking or bulk embedding generation.
- No migrations on startup.
- No scheduler thread.

### Database

Storage is Postgres via `DATABASE_URL`.

Database access lives in:

- `app/database.py`

Migrations live in `migrations/`.

Migration runner:

- `scripts/migrate.py`

Primary tables:

- `articles`
- `article_chunks`
- `weekly_market_reports`
- `investment_theses`
- `thesis_evidence`
- `weekly_category_insights` (legacy historical data)
- `schema_migrations`

### Worker

Worker entrypoint:

- `scripts/worker.py`

Responsibilities:

- Run migrations.
- Fetch long-form articles.
- Insert new articles into Postgres.
- Summarize pending articles with OpenAI.
- Create overlapping article chunks and OpenAI embeddings.
- Generate one comprehensive weekly market report across all categories and investors.

The worker is designed for GitHub Actions or another external scheduler.

### Configuration

Required production environment variables:

- `DATABASE_URL`
- `OPENAI_API_KEY`

Recommended environment variables:

- `APP_NAME`
- `OPENAI_MODEL`
- `CHAT_MODEL`
- `WEEKLY_REPORT_MODEL`
- `WEEKLY_REPORT_BATCH_SIZE`
- `THESIS_MODEL`
- `THESIS_MAX_EVIDENCE`
- `THESIS_MAX_PER_WORKSPACE`
- `WORKSPACE_SECRET`
- `EMBEDDING_MODEL`
- `EMBEDDING_DIMENSIONS`
- `CHAT_TOP_K`
- `ARTICLE_CHUNK_WORDS`
- `ARTICLE_CHUNK_OVERLAP_WORDS`
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
4. Each extracted page is classified as ARTICLE, INDEX_PAGE, AUTHOR_PAGE,
   PODCAST_PAGE, NEWSLETTER_ARCHIVE, or LOW_VALUE_PAGE.
5. For INDEX_PAGE and NEWSLETTER_ARCHIVE pages, the worker scores internal links,
   fetches the top five candidates, and classifies them at recursion depth 1.
6. A run-level URL set prevents duplicate fetches and recursive loops.
7. Each fetched page receives a deterministic 1-10 content quality score covering
   originality, specificity, evidence density, venture relevance, and depth.
8. Trusted VC domains receive a small editorial-quality bonus and can qualify at
   500 words; standard sources normally require 800 words.
9. Recency is stored as a 2-10 ranking score instead of rejecting articles by age.
10. Worker stores classification, extraction diagnostics, quality reasoning, and
    skip reason by unique `url`.
11. Eligible ARTICLE records scoring at least 7 receive a content type classification
   before entering the existing summarization queue.
12. Only eligible ARTICLE records scoring at least 7 are summarized through OpenAI,
    using an adaptive template selected from their content type.
13. Worker chunks articles and stores embeddings in pgvector.
14. On Mondays, the worker generates the previous week's comprehensive market report.
15. Vercel web app reads from Postgres and renders pages.

## AI Chat Data Flow

1. The browser sends one research question to `POST /api/chat`.
2. The web app creates an embedding for the question.
3. Postgres retrieves related chunks with pgvector cosine distance.
4. PostgreSQL full-text search is used when vector retrieval is unavailable.
5. Only retrieved excerpts are sent to the chat model.
6. The response contains inline source numbers and structured citations.

Chat is stateless. Questions and conversation history are not stored.

## Investor Comparison

`/api/compare` reuses the article chunk index and citation format from AI Chat.
It creates one topic embedding, retrieves source-filtered chunks for each selected
fund, and sends the combined evidence to one model request. The response includes
each fund's thesis, arguments, agreements, disagreements, investment implications,
and citations. Comparisons are stateless and are not stored in Postgres.

## Weekly Market Report

The worker analyzes every eligible article from the previous complete
Monday-to-Sunday period. Articles are processed in batches so each article is
represented in candidate findings. A final synthesis produces Top Signals,
Rising Topics, Investor Consensus, Investor Disagreements, and Emerging Themes.

The structured report and its citation snapshot are stored in
`weekly_market_reports`. The web app only reads the latest report at `/weekly`;
it cannot trigger generation.

## Thesis Builder

Thesis Builder stores investment theses and evidence snapshots in Postgres.
Visitors receive a signed, HttpOnly anonymous workspace cookie. Every thesis and
evidence query is scoped by that workspace ID; numeric thesis IDs alone do not
grant access.

Evidence can come from articles, AI Chat, Investor Comparison, weekly reports,
or manual research. Imported research is treated as untrusted evidence in model
prompts. AI citations are filtered against real evidence IDs, and memo source
lists are constructed deterministically by the server.

The MVP limits each thesis to 20 evidence items and each workspace to 25 theses.
There is no cross-device synchronization or recovery after the signed workspace
cookie is deleted.

The Thesis Builder MVP uses `/thesis-builder` as its primary workspace while
retaining the legacy `/theses` routes. AI drafts contain nine independently
editable sections. Draft generation and section regeneration can cite only
evidence rows owned by the current anonymous workspace.

Evidence Research uses a provider interface. The current providers search
accepted article chunks, the latest weekly signal report, and company research
already saved in the current workspace. Each candidate is classified as
SUPPORTING, COUNTER, or CONTEXT and receives strength, source credibility, and
priority metadata. External web search is intentionally not registered as a
provider in this phase.

## Production Boundary

The web app is intentionally read-heavy and request-scoped. Long network-bound
work is isolated in the worker so Vercel request timeouts and cold starts do not
affect ingestion reliability.

## Controlled Daily Ingestion

`scripts/daily_ingestion.py` is the production daily orchestration entry point.
It discovers at most 80 structured candidates from configured RSS feeds, source
index pages, and optional `DAILY_MANUAL_SOURCE_URLS`. Discovery does not summarize.

Triage canonicalizes and deduplicates URLs, removes records already present in
Postgres, and cheaply ranks candidates using source tier, recency, title/topic
relevance, and article-like URL signals. Only the top 30 proceed to full fetching.

The final stage reuses the existing page classifier, quality scorer, content type
classifier, and adaptive summary templates. It summarizes at most eight articles,
with a maximum of three per source, and never fills a quota with low-quality pages.
`--dry-run` stops after triage and performs no article fetches, OpenAI calls, or
database writes. `--preview` runs classification and summaries without database
writes. GitHub Actions runs the normal mode daily and stores run status, metrics,
errors, and the full JSON report in `ingestion_runs`.

Transient page-fetch and OpenAI failures are retried up to three times with
exponential backoff. GitHub Actions exposes failures in the repository Actions
UI, retains each JSON report for 30 days, and can send failure notifications to
an optional `INGESTION_ALERT_WEBHOOK_URL` secret.
