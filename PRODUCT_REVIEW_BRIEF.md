# Thesisflow Product Review Brief

## Purpose

Use this document to ask ChatGPT or another product reviewer what Thesisflow is
missing before the next deployment. Today's Phase 1-4 changes are local and are
not available at the existing public Vercel URL.

## Product Positioning

Thesisflow is an AI investment research workspace built on long-form writing from
leading venture firms. It helps investors move from source discovery to cited
research, market synthesis, and a written investment thesis.

Target users:

- Venture capital investors
- Angel investors
- Startup founders researching market narratives
- Strategy and corporate development teams

## Current Product Workflow

1. Ingestion worker fetches recent long-form articles from selected VC sources.
2. OpenAI generates structured article summaries.
3. Articles are chunked and embedded in Neon Postgres with pgvector.
4. Users ask cited questions in AI Chat.
5. Users compare how selected VC firms think about one topic.
6. A comprehensive weekly market signal report is generated automatically.
7. Users save articles and generated research into Thesis Builder.
8. Thesis Builder develops the claim and exports an investment memo.

## Current Features

### Article Research

- Long-form article ingestion and filtering
- Eight investment categories
- Article search and source aliases
- Structured bilingual summaries
- Original article quotes
- Daily article view and Top 5 reads

### AI Chat with Sources

- Semantic retrieval with pgvector
- PostgreSQL full-text fallback
- Chinese or English answers based on question language
- Structured answers with highlighted insights
- Inline citations and clickable article sources

### Investor View Comparison

- Compare 2-4 investors on one topic
- Source-filtered retrieval for each firm
- Core thesis and key arguments by firm
- Agreements, disagreements, and investment implications
- Cited source list

### Weekly Market Signals

- One comprehensive report across all categories and investors
- Top signals, rising topics, consensus, disagreements, and emerging themes
- Stored report history in Postgres
- Article-level citations

### Thesis Builder

- Create and edit saved investment theses
- Add article evidence
- Save Chat, Compare, and Weekly research snapshots
- Generate supporting evidence, counterarguments, questions, and implications
- Generate and export an investment memo
- Verified evidence IDs and deterministic source list

## Current Technical Architecture

- Web: FastAPI + Jinja templates on Vercel Python runtime
- Database: Neon Postgres + pgvector
- Worker: GitHub Actions daily ingestion
- AI: OpenAI Responses and Embeddings APIs
- Frontend: server-rendered HTML, CSS, and small vanilla JavaScript modules
- Authentication: none
- Thesis ownership: signed anonymous browser workspace cookie

## Known Constraints

- No user accounts or cross-device synchronization
- Anonymous theses cannot be recovered after cookie deletion
- No team sharing, comments, or permissions
- No saved Chat or Compare history unless manually saved into a thesis
- No explicit rate limiter for public AI endpoints yet
- No usage analytics, feedback capture, or model quality evaluation dashboard
- No email, Slack, or notification delivery for weekly reports
- No PDF or DOCX memo export
- No portfolio/company entity model
- No private document upload or user-provided data source
- No thesis version history or change comparison
- No admin interface for ingestion failures and source health
- Source coverage is limited to the configured VC publishers
- Existing public Vercel deployment is behind the local code in this brief

## Product Review Questions

Please review Thesisflow as an AI investment research product and answer:

1. What are the five most important missing capabilities before inviting external users?
2. Which current features are likely confusing, redundant, or insufficiently connected?
3. What should the primary user journey and homepage call-to-action be?
4. What trust, citation, data quality, or AI safety features are missing?
5. What should be added before charging investors for this product?
6. Which feature should be built next: authentication, research history, private uploads,
   company tracking, notifications, collaboration, or something else?
7. What metrics should be instrumented to determine whether the product is useful?
8. Identify UX problems that are likely from the route and workflow descriptions.
9. Suggest a focused 30-day roadmap, ordered by impact and implementation effort.
10. State which features should explicitly not be built yet.

## Suggested Review Prompt

```text
Act as a senior product manager and investment research software expert.

Review the attached Thesisflow Product Review Brief and Development Log.
Thesisflow is currently an MVP, so prioritize a coherent user workflow, source
trust, retention, and cost control over broad feature expansion.

Return:
1. Critical product gaps
2. UX and workflow problems
3. Trust and data-quality risks
4. Recommended next feature
5. A prioritized 30-day roadmap
6. Features to postpone

Be specific and challenge weak assumptions. Separate must-have changes from
nice-to-have ideas.
```

## Files Useful for a Technical Review

Upload these files together with this brief if the reviewer can inspect code:

```text
ARCHITECTURE.md
DEVELOPMENT_LOG.md
DEPLOYMENT.md
README.md
app/main.py
app/chat.py
app/compare.py
app/weekly_report.py
app/theses.py
app/thesis_routes.py
app/database.py
```

For visual feedback, also attach screenshots of:

```text
/
/chat
/compare
/weekly
/theses
/theses/new
```
