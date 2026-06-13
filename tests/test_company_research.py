from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.company_research import extract_external_sources, research_company
from app.main import app


COMPANY_RESULT = {
    "company": "Anthropic",
    "report": {
        "company_snapshot": {"name": "Anthropic", "one_liner": "AI safety company"},
        "what_they_do": "Builds AI models.",
        "problem_solved": "Reliable enterprise AI.",
        "market": {},
        "business_model": {},
        "funding_history": [],
        "competitive_landscape": {},
        "bull_case": [],
        "bear_case": [],
        "open_questions": [],
        "related_signals": [],
    },
    "related_articles": [],
    "weekly_signal_sources": [],
    "external_sources": [],
    "retrieval_mode": "vector",
    "model": "gpt-4.1-mini",
}


def test_company_page_renders() -> None:
    response = TestClient(app).get("/company")

    assert response.status_code == 200
    assert "生成一份投资人视角的公司报告" in response.text
    assert "保存到 Thesis Builder" in response.text
    assert "/api/company-research" in response.text


def test_company_api_returns_report() -> None:
    with patch("app.main.research_company", return_value=COMPANY_RESULT):
        response = TestClient(app).post(
            "/api/company-research", json={"company_name": "Anthropic"}
        )

    assert response.status_code == 200
    assert response.json() == COMPANY_RESULT


def test_company_api_rejects_blank_name() -> None:
    response = TestClient(app).post(
        "/api/company-research", json={"company_name": "   "}
    )

    assert response.status_code == 400


def test_extract_external_sources_deduplicates_urls() -> None:
    response = SimpleNamespace(
        model_dump=lambda: {
            "output": [
                {
                    "type": "web_search_call",
                    "action": {
                        "sources": [
                            {"title": "Anthropic", "url": "https://anthropic.com"},
                            {"title": "Duplicate", "url": "https://anthropic.com"},
                        ]
                    },
                }
            ]
        }
    )

    assert extract_external_sources(response) == [
        {"title": "Anthropic", "url": "https://anthropic.com"}
    ]


def test_research_company_reuses_internal_retrieval_and_web_search() -> None:
    generated = {key: [] for key in (
        "funding_history", "bull_case", "bear_case", "open_questions", "related_signals"
    )}
    generated.update(
        {
            "company_snapshot": {"name": "Acme"},
            "what_they_do": "Builds software.",
            "problem_solved": "Automation.",
            "market": {},
            "business_model": {},
            "competitive_landscape": {},
        }
    )
    response = SimpleNamespace(
        output_text=json.dumps(generated),
        model_dump=lambda: {"output": []},
    )
    client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: response))

    with (
        patch("app.company_research.OPENAI_API_KEY", "test-key"),
        patch("app.company_research.retrieve_chunks", return_value=([], "full_text")),
        patch("app.company_research.search_articles", return_value=[]),
        patch("app.company_research.get_latest_weekly_market_report", return_value=None),
        patch("app.company_research.OpenAI", return_value=client),
    ):
        result = research_company("Acme")

    assert result["company"] == "Acme"
    call = client.responses.create
    assert result["report"]["what_they_do"] == "Builds software."
