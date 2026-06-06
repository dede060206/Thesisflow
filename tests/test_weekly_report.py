from __future__ import annotations

from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.weekly_report import (
    generate_weekly_market_report,
    normalize_report,
    previous_week_range,
)


WEEKLY_REPORT = {
    "id": 1,
    "week_start": "2026-06-01",
    "week_end": "2026-06-07",
    "report": {
        "top_signals": [
            {
                "rank": 1,
                "title": "AI infrastructure spending rises",
                "summary": "Capital is moving into infrastructure.",
                "why_it_matters": "It changes application economics.",
                "investors": ["Andreessen Horowitz"],
                "citation_numbers": [1],
            }
        ],
        "rising_topics": [],
        "investor_consensus": [],
        "investor_disagreements": [],
        "emerging_themes": [],
    },
    "citations": [
        {
            "citation_number": 1,
            "article_id": 1,
            "title": "Infrastructure",
            "source": "Andreessen Horowitz",
            "url": "https://example.com/infra",
            "published_at": "2026-06-02",
            "category": "AI",
        }
    ],
    "source_article_ids": [1],
    "article_count": 12,
    "investor_count": 5,
    "model": "gpt-4.1-mini",
    "report_version": 1,
    "generated_at": "2026-06-08T08:00:00+00:00",
}


def test_previous_week_range_uses_complete_monday_to_sunday() -> None:
    assert previous_week_range(date(2026, 6, 8)) == (
        "2026-06-01",
        "2026-06-07",
    )
    assert previous_week_range(date(2026, 6, 10)) == (
        "2026-06-01",
        "2026-06-07",
    )


def test_weekly_generation_skips_non_monday() -> None:
    result = generate_weekly_market_report(
        force=False,
        reference_date=date(2026, 6, 6),
    )

    assert result == {"generated": 0, "skipped": "not_monday"}


def test_normalize_report_keeps_required_sections_and_valid_citations() -> None:
    report = normalize_report(
        {
            "top_signals": [
                {"title": "Signal", "citation_numbers": [2, 99, 2]}
            ]
        },
        citation_count=3,
    )

    assert set(report) == {
        "top_signals",
        "rising_topics",
        "investor_consensus",
        "investor_disagreements",
        "emerging_themes",
    }
    assert report["top_signals"][0]["rank"] == 1
    assert report["top_signals"][0]["citation_numbers"] == [2]


def test_weekly_page_renders_latest_report() -> None:
    with patch("app.main.get_latest_weekly_market_report", return_value=WEEKLY_REPORT):
        response = TestClient(app).get("/weekly")

    assert response.status_code == 200
    assert "Thesisflow 周度市场信号" in response.text
    assert "本周核心信号" in response.text
    assert "AI infrastructure spending rises" in response.text
    assert "Infrastructure" in response.text


def test_weekly_page_has_empty_state() -> None:
    with patch("app.main.get_latest_weekly_market_report", return_value=None):
        response = TestClient(app).get("/weekly")

    assert response.status_code == 200
    assert "周度市场报告尚未生成" in response.text
