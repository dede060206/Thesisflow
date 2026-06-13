from datetime import datetime, timezone
from unittest.mock import patch

from app.fetcher import (
    extract_internal_links,
    fetch_classified_url,
    score_candidate_link,
    select_candidate_links,
)


def long_content(label: str) -> str:
    paragraph = (
        f"{label} research analysis presents an investment thesis and framework. "
        "Acme Cloud and Vector Labs build AI infrastructure products for enterprise software. "
        "The case study covers datasets, business models, revenue, gross margin, and markets. "
        "According to cited research, adoption rose 42% to $120 million and costs fell 3x. "
        "For example, the technical explanation shows a trade-off for startup founders and "
        "venture investors. However, market structure and valuation remain important. "
    )
    return paragraph * 90


def test_extract_internal_links_deduplicates_and_filters_low_value_paths():
    html = """
    <html><body>
      <a href="/insights/ai-market-2026?ref=home">AI market</a>
      <a href="/insights/ai-market-2026#section">A detailed AI market outlook</a>
      <a href="https://example.com/blog/startup-fundraising">Startup fundraising</a>
      <a href="https://other.example.com/article/external">External article</a>
      <a href="/about">About</a>
      <a href="/authors/jane">Jane</a>
      <a href="mailto:hello@example.com">Email</a>
    </body></html>
    """

    links = extract_internal_links(html, "https://example.com/insights")

    assert links == [
        {
            "url": "https://example.com/insights/ai-market-2026",
            "anchor_text": "A detailed AI market outlook",
        },
        {
            "url": "https://example.com/blog/startup-fundraising",
            "anchor_text": "Startup fundraising",
        },
    ]


def test_candidate_scoring_prefers_article_patterns_dates_and_relevance():
    strong = score_candidate_link(
        "https://example.com/blog/2026/06/ai-startup-investing",
        "How AI startups are changing venture investing",
    )
    weak = score_candidate_link(
        "https://example.com/company",
        "Learn more",
    )

    assert strong > weak
    assert strong >= 10


def test_select_candidate_links_returns_only_top_five():
    links = [
        {
            "url": f"https://example.com/blog/2026/06/ai-market-{index}",
            "anchor_text": f"AI venture market analysis number {index}",
        }
        for index in range(7)
    ]

    candidates = select_candidate_links(links)

    assert len(candidates) == 5
    assert all(candidate["score"] > 0 for candidate in candidates)


def test_collection_page_fetches_top_candidates_once_and_accepts_articles():
    index_url = "https://example.com/insights"
    candidate_urls = [
        f"https://example.com/blog/2026/06/ai-investing-{index}" for index in range(6)
    ]
    links = "".join(
        f'<a href="{url}">AI venture investing analysis {index}</a>'
        for index, url in enumerate(candidate_urls)
    )
    index_html = f"<html><head><title>Insights</title></head><body>{links}</body></html>"

    def fake_fetch(url):
        if url == index_url:
            return long_content("index"), "Insights", None, False, index_html, None
        return (
            long_content("article"),
            "AI Investing",
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            True,
            "<article>Article</article>",
            None,
        )

    visited = set()
    with patch("app.fetcher.fetch_article_page_data", side_effect=fake_fetch) as mocked:
        pages = fetch_classified_url(
            feed={"source": "Example VC"},
            url=index_url,
            visited_urls=visited,
        )

    accepted = [page for page in pages if not page.get("skip_reason")]
    assert len(accepted) == 5
    assert len(visited) == 6
    assert mocked.call_count == 6
    assert index_url in visited

    with patch("app.fetcher.fetch_article_page_data") as duplicate_fetch:
        assert (
            fetch_classified_url(
                feed={"source": "Example VC"},
                url=index_url,
                visited_urls=visited,
            )
            == []
        )
    duplicate_fetch.assert_not_called()


def test_collection_candidate_does_not_recurse_beyond_depth_one(capsys):
    url = "https://example.com/insights/ai"
    html = (
        '<a href="https://example.com/blog/2026/06/ai-market">'
        "AI venture market analysis</a>"
    )

    with patch(
        "app.fetcher.fetch_article_page_data",
        return_value=(long_content("index"), "Insights", None, False, html, None),
    ) as mocked:
        pages = fetch_classified_url(
            feed={"source": "Example VC"},
            url=url,
            visited_urls=set(),
            depth=1,
        )

    assert len(pages) == 1
    assert mocked.call_count == 1
    assert "max recursion depth 1 reached" in capsys.readouterr().out
