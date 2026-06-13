from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from app.fetcher import (
    apply_ingestion_filters,
    calculate_recency_score,
    enrich_article,
    extract_page_content,
    extract_page_title,
    is_trusted_source,
)


def analytical_content(repetitions: int) -> str:
    paragraph = (
        "Our research presents an investment thesis and strategic point of view on AI markets. "
        "Acme Cloud and Vector Labs illustrate specific products, business models, datasets, "
        "gross margin, and go-to-market strategy for enterprise software companies. "
        "According to a cited market study, revenue rose 42% to $120 million and costs fell 3x. "
        "For example, this case study explains the technical trade-off and competitive advantage. "
        "However, founders and venture investors should consider market structure and valuation. "
    )
    return paragraph * repetitions


def iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def test_recency_score_buckets():
    assert calculate_recency_score(iso_days_ago(10)) == 10
    assert calculate_recency_score(iso_days_ago(30)) == 8
    assert calculate_recency_score(iso_days_ago(60)) == 6
    assert calculate_recency_score(iso_days_ago(120)) == 4
    assert calculate_recency_score(iso_days_ago(365)) == 2
    assert calculate_recency_score(None) == 2


def test_trusted_source_domains_include_configured_publications():
    assert is_trusted_source("https://a16z.com/article")
    assert is_trusted_source("https://sequoiacap.com/article/example")
    assert is_trusted_source("https://review.firstround.com/example")
    assert is_trusted_source("https://abovethecrowd.com/2025/example")
    assert is_trusted_source("https://www.ycombinator.com/blog/example")
    assert is_trusted_source("https://lsvp.com/stories/example")
    assert not is_trusted_source("https://example.com/blog/article")


def test_article_before_september_2025_is_rejected_even_if_high_quality():
    article = enrich_article(
        {
            "source": "Benchmark",
            "title": "A Venture Market Thesis",
            "url": "https://abovethecrowd.com/2022/11/28/venture-market-thesis/",
            "published_at": iso_days_ago(800),
            "content": analytical_content(18),
        }
    )

    apply_ingestion_filters(article)

    assert article["quality_score"] >= 7
    assert article["skip_reason"].startswith("published_before_minimum_date")


def test_trusted_source_can_qualify_between_500_and_1000_words():
    article = enrich_article(
        {
            "source": "Sequoia",
            "title": "Listen to the Market",
            "url": "https://sequoiacap.com/article/listen-to-the-market/",
            "published_at": iso_days_ago(20),
            "content": analytical_content(9),
        }
    )

    apply_ingestion_filters(article)

    assert 500 <= article["word_count"] < 1000
    assert article["trusted_source"] is True
    assert article["quality_score"] >= 7
    assert article["skip_reason"] is None


def test_sequoia_fallback_uses_longer_content_container():
    html = """
    <html><body><article>Short teaser.</article>
    <main><div class="article-body">%s</div></main></body></html>
    """ % analytical_content(9)
    content, has_article, failure = extract_page_content(
        BeautifulSoup(html, "html.parser"),
        "https://sequoiacap.com/article/example/",
    )

    assert has_article is True
    assert len(content.split()) >= 500
    assert failure is None


def test_page_title_prefers_open_graph_metadata_over_site_heading():
    soup = BeautifulSoup(
        '<meta property="og:title" content="Venture Capital Red Flag Checklist">'
        '<h1>Above the Crowd</h1>',
        "html.parser",
    )

    assert extract_page_title(soup) == "Venture Capital Red Flag Checklist"
