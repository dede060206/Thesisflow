from app.content_quality import score_content_quality
from app.fetcher import apply_ingestion_filters, enrich_article


def substantive_content(repetitions: int = 90) -> str:
    paragraph = (
        "Our research presents an investment thesis and framework for AI infrastructure. "
        "The analysis compares Acme Cloud and Vector Labs, their products, business models, "
        "go-to-market strategy, gross margin, datasets, and enterprise software markets. "
        "According to a cited market study, revenue increased 42% to $120 million while "
        "inference costs fell 3x. For example, the case study explains the technical trade-off. "
        "However, founders and venture investors should consider market structure and valuation. "
    )
    return paragraph * repetitions


def test_substantive_investment_analysis_scores_at_least_seven():
    assessment = score_content_quality(
        "The Investment Case for AI Infrastructure",
        substantive_content(),
    )

    assert assessment.score >= 7
    assert assessment.components["evidence"] == 2
    assert assessment.components["venture_relevance"] == 2
    assert "specificity signals" in assessment.reasoning


def test_generic_promotional_content_scores_below_seven():
    content = " ".join(
        ["We are excited to announce. Join us, sign up, subscribe, and apply now."] * 220
    )

    assessment = score_content_quality("A New Opportunity", content)

    assert assessment.score < 7
    assert assessment.components["originality"] == 0
    assert assessment.components["evidence"] == 0


def test_low_quality_article_is_rejected_before_summarization():
    page = enrich_article(
        {
            "source": "Example VC",
            "title": "A New Opportunity",
            "url": "https://example.com/blog/new-opportunity",
            "published_at": "2026-06-12T10:00:00+00:00",
            "content": " ".join(["Join us and subscribe for more updates."] * 300),
        }
    )

    apply_ingestion_filters(page)

    assert page["page_type"] == "ARTICLE"
    assert page["quality_score"] < 7
    assert page["quality_reasoning"]
    assert page["skip_reason"].startswith("below_quality_threshold")
