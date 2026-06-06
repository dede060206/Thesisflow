from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from openai import OpenAI

from app.chat import serialize_date
from app.compare import parse_json_response
from app.config import (
    OPENAI_API_KEY,
    WEEKLY_REPORT_BATCH_SIZE,
    WEEKLY_REPORT_MODEL,
)
from app.database import (
    get_weekly_market_report,
    list_articles_for_weekly_report,
    save_weekly_market_report,
)


REPORT_KEYS = (
    "top_signals",
    "rising_topics",
    "investor_consensus",
    "investor_disagreements",
    "emerging_themes",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def previous_week_range(reference_date: date | None = None) -> tuple[str, str]:
    today = reference_date or date.today()
    current_monday = today - timedelta(days=today.weekday())
    week_start = current_monday - timedelta(days=7)
    week_end = week_start + timedelta(days=6)
    return week_start.isoformat(), week_end.isoformat()


def empty_report() -> dict[str, list]:
    return {key: [] for key in REPORT_KEYS}


def article_citations(articles: list[dict]) -> list[dict[str, Any]]:
    return [
        {
            "citation_number": index,
            "article_id": article["id"],
            "title": article["title"],
            "source": article["source"],
            "url": article["url"],
            "published_at": serialize_date(
                article.get("published_at") or article.get("fetched_at")
            ),
            "category": article.get("category"),
        }
        for index, article in enumerate(articles, start=1)
    ]


def article_context(article: dict, citation_number: int) -> str:
    evidence = article.get("summary") or article.get("content") or ""
    return "\n".join(
        [
            f"SOURCE [{citation_number}]",
            f"Title: {article['title']}",
            f"Investor: {article['source']}",
            f"Category: {article.get('category') or 'Uncategorized'}",
            f"Date: {serialize_date(article.get('published_at') or article.get('fetched_at'))}",
            f"Evidence: {evidence[:2200]}",
        ]
    )


def chunked(values: list[dict], size: int) -> list[list[dict]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def extract_batch_signals(
    client: OpenAI,
    batch: list[dict],
    citation_numbers: dict[int, int],
) -> dict[str, Any]:
    context = "\n\n".join(
        article_context(article, citation_numbers[article["id"]])
        for article in batch
    )
    response = client.responses.create(
        model=WEEKLY_REPORT_MODEL,
        input=[
            {
                "role": "system",
                "content": (
                    "You are a rigorous venture market analyst. Extract candidate "
                    "weekly market signals from every supplied article. Use only the "
                    "evidence provided. Return valid JSON only. Write analysis in "
                    "Chinese, keep investor names unchanged, and retain source numbers."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Articles:\n{context}\n\n"
                    "Return a JSON object with these arrays: top_signals, rising_topics, "
                    "investor_positions, emerging_themes. Each item must include a concise "
                    "statement and citation_numbers. investor_positions must also include "
                    "investor. Cover every article at least once."
                ),
            },
        ],
    )
    return parse_json_response(response.output_text)


def synthesize_report(
    client: OpenAI,
    candidates: list[dict[str, Any]],
    citations: list[dict[str, Any]],
) -> dict[str, Any]:
    source_catalog = [
        {
            "citation_number": item["citation_number"],
            "source": item["source"],
            "title": item["title"],
            "category": item["category"],
        }
        for item in citations
    ]
    response = client.responses.create(
        model=WEEKLY_REPORT_MODEL,
        input=[
            {
                "role": "system",
                "content": (
                    "You produce Thesisflow's comprehensive weekly venture market report. "
                    "Use only the supplied candidate findings and source catalog. Return "
                    "valid JSON only. Write concise Chinese. Do not create category summaries. "
                    "Merge duplicates, distinguish consensus from disagreement, and never "
                    "invent citations."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Candidate findings:\n{json.dumps(candidates, ensure_ascii=False)}\n\n"
                    f"Source catalog:\n{json.dumps(source_catalog, ensure_ascii=False)}\n\n"
                    "Return exactly this JSON shape:\n"
                    "{\n"
                    '  "top_signals": [{"rank": 1, "title": "", "summary": "", '
                    '"why_it_matters": "", "investors": [], "citation_numbers": []}],\n'
                    '  "rising_topics": [{"topic": "", "momentum": "high or medium", '
                    '"evidence": "", "citation_numbers": []}],\n'
                    '  "investor_consensus": [{"statement": "", "investors": [], '
                    '"citation_numbers": []}],\n'
                    '  "investor_disagreements": [{"issue": "", '
                    '"positions": [{"investor": "", "view": ""}], '
                    '"citation_numbers": []}],\n'
                    '  "emerging_themes": [{"theme": "", "early_signal": "", '
                    '"what_to_watch": "", "citation_numbers": []}]\n'
                    "}\n"
                    "Return at most 5 top signals and at most 4 items in each other section."
                ),
            },
        ],
    )
    return normalize_report(parse_json_response(response.output_text), len(citations))


def normalize_citation_numbers(value: Any, maximum: int) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        if isinstance(item, int) and 1 <= item <= maximum and item not in result:
            result.append(item)
    return result


def normalize_report(value: dict[str, Any], citation_count: int) -> dict[str, list]:
    report = empty_report()
    for key in REPORT_KEYS:
        items = value.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            normalized = dict(item)
            normalized["citation_numbers"] = normalize_citation_numbers(
                normalized.get("citation_numbers"), citation_count
            )
            report[key].append(normalized)
    for index, item in enumerate(report["top_signals"], start=1):
        item["rank"] = index
    return report


def referenced_citation_numbers(report: dict[str, list]) -> set[int]:
    numbers: set[int] = set()
    for items in report.values():
        for item in items:
            numbers.update(item.get("citation_numbers") or [])
            for match in re.findall(r"\[(\d+)\]", json.dumps(item, ensure_ascii=False)):
                numbers.add(int(match))
    return numbers


def generate_weekly_market_report(
    *,
    force: bool = False,
    reference_date: date | None = None,
    week_start: str | None = None,
    week_end: str | None = None,
) -> dict[str, Any]:
    today = reference_date or date.today()
    if not force and today.weekday() != 0:
        return {"generated": 0, "skipped": "not_monday"}
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required for weekly market reports.")

    if not week_start or not week_end:
        week_start, week_end = previous_week_range(today)
    if not force and get_weekly_market_report(week_start):
        return {"generated": 0, "skipped": "already_exists"}

    articles = list_articles_for_weekly_report(week_start, week_end)
    citations = article_citations(articles)
    if not articles:
        report = empty_report()
    else:
        client = OpenAI(api_key=OPENAI_API_KEY)
        citation_numbers = {
            article["id"]: index for index, article in enumerate(articles, start=1)
        }
        candidates = [
            extract_batch_signals(client, batch, citation_numbers)
            for batch in chunked(articles, WEEKLY_REPORT_BATCH_SIZE)
        ]
        report = synthesize_report(client, candidates, citations)

    referenced = referenced_citation_numbers(report)
    stored_citations = [
        citation
        for citation in citations
        if not referenced or citation["citation_number"] in referenced
    ]
    save_weekly_market_report(
        week_start=week_start,
        week_end=week_end,
        report=report,
        citations=stored_citations,
        source_article_ids=[article["id"] for article in articles],
        article_count=len(articles),
        investor_count=len({article["source"] for article in articles}),
        model=WEEKLY_REPORT_MODEL,
        generated_at=utc_now(),
    )
    return {
        "generated": 1,
        "week_start": week_start,
        "week_end": week_end,
        "articles": len(articles),
        "investors": len({article["source"] for article in articles}),
    }
