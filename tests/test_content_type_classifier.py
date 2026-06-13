from datetime import datetime, timezone

import pytest

from app.content_type_classifier import (
    COMPANY_ANALYSIS,
    FUNDING_NEWS,
    MARKET_MAP,
    OPINION,
    PODCAST_TRANSCRIPT,
    PRODUCT_LAUNCH,
    TECH_EXPLAINER,
    THESIS_ARTICLE,
    classify_content_type,
)
from app.fetcher import apply_ingestion_filters, enrich_article, log_page_decision


@pytest.mark.parametrize(
    ("title", "content", "expected"),
    [
        (
            "Our Investment Thesis for Vertical AI",
            "We believe this market thesis explains why now and the investment case.",
            THESIS_ARTICLE,
        ),
        (
            "The AI Infrastructure Market Map",
            "This market landscape provides a category breakdown and ecosystem map.",
            MARKET_MAP,
        ),
        (
            "How Transformer Inference Works",
            "A technical explanation of model architecture, APIs, and system design.",
            TECH_EXPLAINER,
        ),
        (
            "Acme Cloud Company Deep Dive",
            "Company analysis of its business model, unit economics, and go-to-market.",
            COMPANY_ANALYSIS,
        ),
        (
            "Acme Raises a Series B",
            "The startup raised a funding round led by new investors.",
            FUNDING_NEWS,
        ),
        (
            "Introducing the Acme Developer Platform",
            "The product launch includes a new feature and API release now available.",
            PRODUCT_LAUNCH,
        ),
        (
            "What I Learned Building a Startup",
            "A founder reflection and personal essay with lessons learned.",
            OPINION,
        ),
        (
            "Podcast Transcript: Building AI Companies",
            "Host: Welcome. Guest: This transcript records our conversation with a founder.",
            PODCAST_TRANSCRIPT,
        ),
    ],
)
def test_classifies_supported_content_types(title, content, expected):
    result = classify_content_type(title, content)

    assert result.content_type == expected
    assert result.reasoning


def high_quality_article_content() -> str:
    paragraph = (
        "Our research presents an investment thesis for AI infrastructure and explains why now. "
        "We believe Acme Cloud and Vector Labs have differentiated products, datasets, business "
        "models, gross margin, and go-to-market strategy in enterprise software markets. "
        "According to a cited market study, revenue rose 42% to $120 million while costs fell 3x. "
        "For example, this case study explains a technical trade-off for startup founders and "
        "venture investors. However, market structure and valuation remain important. "
    )
    return paragraph * 90


def test_pipeline_classifies_only_article_above_quality_threshold(capsys):
    article = enrich_article(
        {
            "source": "Example VC",
            "title": "Our Investment Thesis for AI Infrastructure",
            "url": "https://example.com/blog/ai-infrastructure-thesis",
            "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "content": high_quality_article_content(),
        }
    )

    apply_ingestion_filters(article)
    log_page_decision(article)

    assert article["quality_score"] >= 7
    assert article["content_type"] == THESIS_ARTICLE
    assert article["content_type_reasoning"]
    output = capsys.readouterr().out
    assert article["url"] in output
    assert "page_type=ARTICLE" in output
    assert f"quality_score={article['quality_score']}" in output
    assert "content_type=THESIS_ARTICLE" in output


def test_pipeline_does_not_classify_low_quality_article():
    article = enrich_article(
        {
            "source": "Example VC",
            "title": "A New Community Update",
            "url": "https://example.com/blog/community-update",
            "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "content": " ".join(["Join us, subscribe, and sign up for updates."] * 300),
        }
    )

    apply_ingestion_filters(article)

    assert article["quality_score"] < 7
    assert article["content_type"] is None
    assert article["content_type_reasoning"] is None
    assert article["skip_reason"].startswith("below_quality_threshold")


def test_strategic_positioning_article_is_not_product_launch():
    result = classify_content_type(
        "AI-Powered Isn't a Position",
        "This essay argues that AI product positioning requires differentiation, strategy, "
        "a clear point of view, and competitive advantage rather than generic claims.",
    )

    assert result.content_type == THESIS_ARTICLE


def test_vc_essay_with_funding_vocabulary_is_not_funding_news():
    result = classify_content_type(
        "Venture Capital Red Flag Checklist",
        "This investment thesis discusses funding rounds, seed round terms, business models, "
        "company strategy, market structure, and risks for venture investors.",
    )

    assert result.content_type in {THESIS_ARTICLE, OPINION, COMPANY_ANALYSIS}
