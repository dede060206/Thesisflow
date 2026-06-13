from __future__ import annotations

from unittest.mock import patch

from app.fetcher import apply_ingestion_filters, enrich_article
from app.page_classifier import (
    ARTICLE,
    AUTHOR_PAGE,
    INDEX_PAGE,
    LOW_VALUE_PAGE,
    NEWSLETTER_ARCHIVE,
    PODCAST_PAGE,
    classify_page,
)
from app.summarizer import summarize_pending


LONG_CONTENT = " ".join(["market"] * 1600)
HIGH_QUALITY_SHORT_CONTENT = " ".join(
    [
        "Our research analysis thesis framework compares Acme Cloud and Vector Labs. "
        "Their AI infrastructure products, datasets, business model, revenue, gross margin, "
        "and go-to-market strategy matter to startup founders and venture investors. "
        "According to a market study, revenue rose 42% to $120 million and costs fell 3x. "
        "For example, this case study explains the technical trade-off."
    ]
    * 8
)


def test_classifier_accepts_standalone_article() -> None:
    result = classify_page(
        url="https://example.com/blog/ai-market-shifts",
        title="AI Market Shifts",
        content=LONG_CONTENT,
        published_at="2026-06-10T10:00:00+00:00",
    )

    assert result.page_type == ARTICLE


def test_classifier_detects_index_page() -> None:
    result = classify_page(
        url="https://example.com/ai/",
        title="AI",
        content=LONG_CONTENT,
    )

    assert result.page_type == INDEX_PAGE


def test_classifier_detects_author_page() -> None:
    result = classify_page(
        url="https://example.com/authors/jane-doe",
        title="Jane Doe",
        content=LONG_CONTENT,
    )

    assert result.page_type == AUTHOR_PAGE


def test_classifier_detects_podcast_page() -> None:
    result = classify_page(
        url="https://example.com/podcast/episode-42",
        title="Episode 42",
        content=LONG_CONTENT,
    )

    assert result.page_type == PODCAST_PAGE


def test_classifier_detects_newsletter_archive() -> None:
    result = classify_page(
        url="https://example.com/newsletters/archive",
        title="Past Issues",
        content=LONG_CONTENT,
    )

    assert result.page_type == NEWSLETTER_ARCHIVE


def test_classifier_detects_low_value_page() -> None:
    result = classify_page(
        url="https://example.com/careers",
        title="Careers",
        content=LONG_CONTENT,
    )

    assert result.page_type == LOW_VALUE_PAGE


def test_ingestion_filters_store_page_type_and_skip_reason() -> None:
    page = enrich_article(
        {
            "source": "Example VC",
            "title": "AI Resource Hub",
            "url": "https://example.com/resources",
            "published_at": None,
            "content": LONG_CONTENT,
        }
    )
    apply_ingestion_filters(page)

    assert page["page_type"] == INDEX_PAGE
    assert "page_type=INDEX_PAGE" in page["skip_reason"]


def test_short_article_keeps_article_type_but_is_skipped() -> None:
    page = enrich_article(
        {
            "source": "Example VC",
            "title": "A Short Market Note",
            "url": "https://example.com/blog/short-market-note",
            "published_at": "2026-06-10T10:00:00+00:00",
            "content": HIGH_QUALITY_SHORT_CONTENT,
        }
    )
    apply_ingestion_filters(page)

    assert page["page_type"] == ARTICLE
    assert page["skip_reason"].startswith("below_source_aware_depth_threshold")


def test_summarizer_defensively_skips_non_article_pages() -> None:
    rows = [
        {
            "id": 1,
            "title": "Resource Hub",
            "url": "https://example.com/resources",
            "content": LONG_CONTENT,
            "page_type": INDEX_PAGE,
            "skip_reason": "page_type=INDEX_PAGE: resource hub",
            "quality_score": 3,
        },
        {
            "id": 2,
            "title": "Standalone Article",
            "url": "https://example.com/blog/article",
            "content": LONG_CONTENT,
            "page_type": ARTICLE,
            "skip_reason": None,
            "quality_score": 9,
            "content_type": "THESIS_ARTICLE",
            "category": "Market Analysis",
            "published_at": "2026-06-10T10:00:00+00:00",
        },
    ]
    with (
        patch("app.summarizer.list_unsummarized_articles", return_value=rows),
        patch(
            "app.summarizer.summarize_text",
            return_value=("Summary", "adaptive_v3:THESIS_ARTICLE"),
        ) as summarize,
        patch("app.summarizer.save_summary") as save,
    ):
        result = summarize_pending(limit=10)

    assert result == {"found": 2, "summarized": 1, "skipped": 1}
    summarize.assert_called_once_with(rows[1])
    save.assert_called_once()
    assert save.call_args.args[4] == "adaptive_v3:THESIS_ARTICLE"
