from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


ARTICLE = {
    "id": 1,
    "source": "Y Combinator",
    "title": "YC x Coinbase RFS: Build Onchain",
    "url": "https://www.ycombinator.com/blog/example",
    "author": None,
    "published_at": "2026-06-01T20:32:11+00:00",
    "fetched_at": "2026-06-05T08:00:00+00:00",
    "content": "Long form article content",
    "category": "AI",
    "word_count": 1339,
    "is_long_form": True,
    "summary": (
        "## 中文导读标题\n"
        "AI 基础设施正在重写创业规则\n\n"
        "## Original Title\n"
        "YC x Coinbase RFS: Build Onchain\n\n"
        "## Core Thesis\n"
        "测试摘要。\n\n"
        "## Important Quotes\n"
        "- 原文引用。"
    ),
    "summary_model": "gpt-4.1-mini",
    "summary_template": "adaptive_v3:THESIS_ARTICLE",
    "summarized_at": "2026-06-05T08:10:00+00:00",
    "page_type": "ARTICLE",
    "skip_reason": None,
    "quality_score": 9,
    "quality_reasoning": "Substantive investment analysis with evidence.",
    "content_type": "THESIS_ARTICLE",
    "content_type_reasoning": "Strong investment thesis signals.",
}

INSIGHT = {
    "id": 1,
    "category": "AI",
    "week_start": "2026-06-01",
    "week_end": "2026-06-07",
    "insight": "## Weekly Trend\nAI 趋势。",
    "summary_model": "gpt-4.1-mini",
    "generated_at": "2026-06-05T08:20:00+00:00",
}


def test_homepage_renders_thesisflow() -> None:
    client = TestClient(app)
    with (
        patch("app.main.list_articles", return_value=[ARTICLE]),
        patch("app.main.list_top_reads_today", return_value=[ARTICLE]),
        patch("app.main.get_latest_weekly_market_report", return_value=None),
    ):
        response = client.get("/")

    assert response.status_code == 200
    assert "Thesisflow" in response.text
    assert "在资本的长文里" in response.text


def test_health_route_does_not_require_database() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "app": "Thesisflow"}


def test_category_route_renders_articles() -> None:
    client = TestClient(app)
    with (
        patch("app.main.list_articles_by_category", return_value=[ARTICLE]),
        patch("app.main.get_latest_weekly_market_report", return_value=None),
    ):
        response = client.get("/category/AI")

    assert response.status_code == 200
    assert "YC x Coinbase" in response.text
    assert "AI 基础设施正在重写创业规则" in response.text


def test_update_endpoint_removed() -> None:
    client = TestClient(app)
    response = client.post("/api/update")
    assert response.status_code == 404
