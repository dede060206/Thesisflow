from __future__ import annotations

from datetime import datetime, timezone

from app.daily_ingestion import (
    Candidate,
    DailyIngestionConfig,
    DailyIngestionServices,
    deduplicate_candidates,
    retry_operation,
    run_daily_ingestion,
)


def substantive_content() -> str:
    paragraph = (
        "AI infrastructure is becoming a distinct software market for startup founders and "
        "venture investors. Acme Cloud and Vector Labs sell developer tools with usage-based "
        "business models. Customer adoption increased 42 percent to $120 million while model "
        "serving costs fell threefold, according to the cited market dataset. The analysis "
        "compares gross margins, technical architecture, competition, regulation, and go-to-market "
        "strategy. This evidence supports an investment thesis but also identifies valuation and "
        "execution risks. "
    )
    return paragraph * 45


def candidates(count: int, source: str = "Andreessen Horowitz") -> list[Candidate]:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return [
        Candidate(
            source=source,
            url=f"https://a16z.com/2026/06/ai-market-{index}",
            title=f"AI infrastructure market thesis {index}",
            publish_date=now,
            discovery_method="rss",
            source_tier="trusted",
            recency_score=10,
        )
        for index in range(count)
    ]


def services(calls: dict[str, int]) -> DailyIngestionServices:
    stored: dict[str, dict] = {}

    def fetch_page(_url):
        calls["fetch"] += 1
        return (
            substantive_content(),
            "AI Infrastructure Market Thesis",
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            True,
            "<article></article>",
            None,
        )

    def write_article(article):
        calls["write"] += 1
        stored[article["url"]] = {**article, "id": calls["write"]}
        return True

    def summarize(_article):
        calls["summary"] += 1
        return "## 核心论点\n**AI infrastructure** is investable.", "adaptive_v3:THESIS_ARTICLE"

    def save(*_args):
        calls["save"] += 1

    return DailyIngestionServices(
        existing_url_loader=lambda _urls: set(),
        page_fetcher=fetch_page,
        article_writer=write_article,
        article_loader=lambda url: stored.get(url),
        summary_generator=summarize,
        summary_saver=save,
    )


def call_counter() -> dict[str, int]:
    return {"fetch": 0, "write": 0, "summary": 0, "save": 0}


def test_deduplication_normalizes_urls_and_keeps_best_metadata():
    first = Candidate(source="a16z", url="https://a16z.com/post/?ref=home", title="AI")
    second = Candidate(
        source="a16z",
        url="https://a16z.com/post#section",
        title="A detailed AI investment thesis",
        publish_date="2026-06-10T00:00:00+00:00",
        discovery_method="index_page",
    )

    result = deduplicate_candidates([first, second])

    assert len(result) == 1
    assert result[0].url == "https://a16z.com/post"
    assert result[0].title == second.title
    assert result[0].publish_date == second.publish_date


def test_daily_fetch_and_summary_limits_are_enforced():
    calls = call_counter()
    report = run_daily_ingestion(
        config=DailyIngestionConfig(
            max_candidate_links=3,
            max_pages_fetched=2,
            max_articles_summarized=1,
        ),
        discovered_candidates=candidates(5),
        services=services(calls),
    )

    assert report["candidates_discovered"] == 3
    assert report["pages_selected"] == 2
    assert report["pages_fetched"] == 1
    assert report["articles_summarized"] == 1
    assert calls["summary"] == 1


def test_max_per_source_is_enforced():
    calls = call_counter()
    report = run_daily_ingestion(
        config=DailyIngestionConfig(
            max_pages_fetched=5,
            max_articles_summarized=5,
            max_per_source=2,
        ),
        discovered_candidates=candidates(5),
        services=services(calls),
    )

    assert report["articles_summarized"] == 2
    assert report["per_source_counts"] == {"Andreessen Horowitz": 2}
    assert report["rejection_reasons"]["max_per_source_reached"] == 3


def test_variable_output_does_not_fill_a_quota():
    calls = call_counter()
    report = run_daily_ingestion(
        config=DailyIngestionConfig(max_articles_summarized=8, max_per_source=8),
        discovered_candidates=candidates(3),
        services=services(calls),
    )

    assert report["articles_summarized"] == 3
    assert calls["summary"] == 3


def test_dry_run_stops_after_discovery_and_triage_without_writes():
    calls = call_counter()
    report = run_daily_ingestion(
        dry_run=True,
        discovered_candidates=candidates(4),
        services=services(calls),
    )

    assert report["pages_selected"] == 4
    assert report["pages_fetched"] == 0
    assert report["articles_summarized"] == 0
    assert report["database_rows_written"] == 0
    assert calls == {"fetch": 0, "write": 0, "summary": 0, "save": 0}


def test_preview_runs_full_pipeline_without_database_writes():
    calls = call_counter()
    report = run_daily_ingestion(
        preview=True,
        config=DailyIngestionConfig(max_articles_summarized=2, max_per_source=2),
        discovered_candidates=candidates(2),
        services=services(calls),
    )

    assert report["articles_summarized"] == 2
    assert report["database_rows_written"] == 0
    assert calls == {"fetch": 2, "write": 0, "summary": 2, "save": 0}
    assert all(item.get("summary") for item in report["processed"])


def test_retry_operation_retries_transient_failures():
    attempts = {"count": 0}

    def transient_operation():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("temporary failure")
        return "ok"

    result = retry_operation(
        transient_operation,
        label="test operation",
        attempts=3,
        base_seconds=0,
    )

    assert result == "ok"
    assert attempts["count"] == 3
