from __future__ import annotations

import html
import logging
import re
from collections.abc import Callable
from typing import TypeVar

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.chat import answer_question
from app.compare import compare_investors
from app.config import APP_NAME, CATEGORIES, DATABASE_URL, INVESTORS
from app.database import (
    get_latest_weekly_market_report,
    get_weekly_insight_by_id,
    get_article,
    list_articles,
    list_articles_by_category,
    list_daily_articles,
    list_top_reads_today,
    search_articles,
)
from app.thesis_routes import router as thesis_router


app = FastAPI(title=APP_NAME)
app.include_router(thesis_router)
templates = Jinja2Templates(directory="app/templates")
templates.env.cache = None
app.mount("/static", StaticFiles(directory="app/static"), name="static")
logger = logging.getLogger(__name__)
T = TypeVar("T")


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1500)
    top_k: int = Field(default=6, ge=3, le=10)


class CompareRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    investors: list[str]


SUMMARY_HEADING_LABELS = {
    "core thesis": "Core Thesis / 核心论点",
    "key insights": "Key Insights / 关键洞察",
    "actionable takeaways": "Actionable Takeaways / 行动启发",
    "important quotes": "原文引用",
    "原文引用": "原文引用",
}

SECTION_ALIASES = {
    "Important Quotes": ["Important Quotes", "原文引用"],
    "原文引用": ["原文引用", "Important Quotes"],
}


def display_heading(value: str) -> str:
    return SUMMARY_HEADING_LABELS.get(value.strip().lower(), value)


def render_summary(value: str | None) -> str:
    if not value:
        return "<p>摘要尚未生成。</p>"

    escaped = html.escape(value)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    lines = escaped.splitlines()
    rendered: list[str] = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                rendered.append("</ul>")
                in_list = False
            continue
        if stripped.startswith("## "):
            if in_list:
                rendered.append("</ul>")
                in_list = False
            rendered.append(f"<h3>{display_heading(stripped[3:])}</h3>")
        elif stripped.startswith("- "):
            if not in_list:
                rendered.append("<ul>")
                in_list = True
            rendered.append(f"<li>{stripped[2:]}</li>")
        else:
            if in_list:
                rendered.append("</ul>")
                in_list = False
            rendered.append(f"<p>{stripped}</p>")

    if in_list:
        rendered.append("</ul>")

    return "\n".join(rendered)


def summary_section(value: str | None, section_name: str) -> str:
    if not value:
        return ""
    names = SECTION_ALIASES.get(section_name, [section_name])
    lines = value.splitlines()
    section_lines: list[str] = []
    in_section = False
    for line in lines:
        if re.match(r"^##\s+", line):
            if in_section:
                break
            heading = line.strip()[3:].strip()
            in_section = any(
                heading.lower() == name.lower() for name in names
            )
            continue
        if in_section:
            section_lines.append(line)
    return "\n".join(section_lines).strip()


def summary_without_section(value: str | None, section_name: str) -> str:
    if not value:
        return ""
    names = SECTION_ALIASES.get(section_name, [section_name])
    lines = value.splitlines()
    kept: list[str] = []
    skipping = False
    for line in lines:
        if re.match(r"^##\s+", line):
            heading = line.strip()[3:].strip()
            skipping = any(
                heading.lower() == name.lower() for name in names
            )
            if skipping:
                continue
        if not skipping:
            kept.append(line)
    return "\n".join(kept).strip()


def db_or_default(fn: Callable[[], T], default: T) -> T:
    try:
        return fn()
    except RuntimeError as exc:
        logger.warning("Database unavailable: %s", exc)
        return default


templates.env.filters["summary_html"] = render_summary
templates.env.filters["summary_section"] = summary_section
templates.env.filters["summary_without_section"] = summary_without_section


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": APP_NAME}


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "articles": db_or_default(list_articles, []),
            "top_articles": db_or_default(list_top_reads_today, []),
            "weekly_report": db_or_default(get_latest_weekly_market_report, None),
            "query": "",
            "categories": CATEGORIES,
            "database_unavailable": not bool(DATABASE_URL),
        },
    )


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = "") -> HTMLResponse:
    articles = (
        db_or_default(lambda: search_articles(q.strip()), []) if q.strip() else []
    )
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "articles": articles,
            "top_articles": [],
            "weekly_report": db_or_default(get_latest_weekly_market_report, None),
            "query": q,
            "is_search": True,
            "categories": CATEGORIES,
        },
    )


@app.get("/category/{category}", response_class=HTMLResponse)
def category_page(request: Request, category: str) -> HTMLResponse:
    selected = next(
        (item for item in CATEGORIES if item.lower() == category.lower()),
        category,
    )
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "articles": db_or_default(lambda: list_articles_by_category(selected), []),
            "top_articles": [],
            "weekly_report": db_or_default(get_latest_weekly_market_report, None),
            "query": "",
            "is_category": True,
            "selected_category": selected,
            "categories": CATEGORIES,
        },
    )


@app.get("/insight/{insight_id}", response_class=HTMLResponse)
def weekly_insight_detail(request: Request, insight_id: int) -> HTMLResponse:
    insight = db_or_default(lambda: get_weekly_insight_by_id(insight_id), None)
    return templates.TemplateResponse(
        request,
        "insight.html",
        {"insight": insight},
        status_code=200 if insight else 404,
    )


@app.get("/daily", response_class=HTMLResponse)
def daily(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "daily.html",
        {"articles": db_or_default(list_daily_articles, [])},
    )


@app.get("/weekly", response_class=HTMLResponse)
def weekly_dashboard(request: Request) -> HTMLResponse:
    report = db_or_default(get_latest_weekly_market_report, None)
    citation_article_ids = (
        [item["article_id"] for item in report["citations"][:10]] if report else []
    )
    return templates.TemplateResponse(
        request,
        "weekly.html",
        {
            "weekly_report": report,
            "weekly_citation_article_ids": citation_article_ids,
        },
        status_code=200,
    )


@app.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "chat.html", {})


@app.post("/api/chat")
def api_chat(payload: ChatRequest) -> dict:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    try:
        return answer_question(question, top_k=payload.top_k)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Chat request failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to answer the question right now.",
        ) from exc


@app.get("/compare", response_class=HTMLResponse)
def compare_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "compare.html",
        {"investors": INVESTORS},
    )


@app.post("/api/compare")
def api_compare(payload: CompareRequest) -> dict:
    topic = payload.topic.strip()
    investor_keys = list(dict.fromkeys(payload.investors))
    if not topic:
        raise HTTPException(status_code=400, detail="Topic cannot be empty.")
    if not 2 <= len(investor_keys) <= 4:
        raise HTTPException(
            status_code=400,
            detail="Select between 2 and 4 investors.",
        )
    invalid = [key for key in investor_keys if key not in INVESTORS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown investors: {', '.join(invalid)}",
        )
    try:
        return compare_investors(topic, investor_keys)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Investor comparison failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to compare investor views right now.",
        ) from exc


@app.get("/article/{article_id}", response_class=HTMLResponse)
def article_detail(request: Request, article_id: int) -> HTMLResponse:
    article = db_or_default(lambda: get_article(article_id), None)
    return templates.TemplateResponse(
        request,
        "article.html",
        {"article": article},
        status_code=200 if article else 404,
    )


@app.get("/api/articles")
def api_articles() -> list[dict]:
    return [dict(article) for article in db_or_default(list_articles, [])]
