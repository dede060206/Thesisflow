from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
import time
from typing import Any, Callable
from urllib.parse import urlparse

import feedparser

from app.config import (
    DAILY_MANUAL_SOURCE_URLS,
    DAILY_MAX_ARTICLES_SUMMARIZED,
    DAILY_MAX_CANDIDATE_LINKS,
    DAILY_MAX_PAGES_FETCHED,
    DAILY_MAX_PER_SOURCE,
    DAILY_MAX_RECURSION_DEPTH,
    DAILY_MIN_QUALITY_SCORE,
    DAILY_RETRY_ATTEMPTS,
    DAILY_RETRY_BASE_SECONDS,
    FEEDS,
    OPENAI_MODEL,
)
from app.database import (
    get_article_by_url,
    list_existing_article_urls,
    save_summary,
    upsert_article,
)
from app.fetcher import (
    ARTICLE,
    RELEVANCE_TERMS,
    apply_ingestion_filters,
    calculate_recency_score,
    canonical_url,
    enrich_article,
    extract_internal_links,
    fetch_article_page_data,
    fetch_feed_text,
    html_to_text,
    is_trusted_source,
    parse_date,
    score_candidate_link,
    utc_now,
)
from app.summarizer import summarize_text


@dataclass(frozen=True)
class DailyIngestionConfig:
    max_candidate_links: int = DAILY_MAX_CANDIDATE_LINKS
    max_pages_fetched: int = DAILY_MAX_PAGES_FETCHED
    max_articles_summarized: int = DAILY_MAX_ARTICLES_SUMMARIZED
    min_quality_score: int = DAILY_MIN_QUALITY_SCORE
    max_per_source: int = DAILY_MAX_PER_SOURCE
    max_recursion_depth: int = DAILY_MAX_RECURSION_DEPTH
    retry_attempts: int = DAILY_RETRY_ATTEMPTS
    retry_base_seconds: int = DAILY_RETRY_BASE_SECONDS


@dataclass
class Candidate:
    source: str
    url: str
    title: str = ""
    discovered_at: str = field(default_factory=utc_now)
    publish_date: str | None = None
    discovery_method: str = "manual"
    source_tier: str = "standard"
    recency_score: int = 2
    triage_score: int = 0


@dataclass
class DailyIngestionServices:
    existing_url_loader: Callable[[list[str]], set[str]] = list_existing_article_urls
    page_fetcher: Callable[..., tuple[str, str | None, str | None, bool, str, str | None]] = (
        fetch_article_page_data
    )
    article_writer: Callable[[dict[str, Any]], bool] = upsert_article
    article_loader: Callable[[str], dict[str, Any] | None] = get_article_by_url
    summary_generator: Callable[[dict[str, Any]], tuple[str, str]] = summarize_text
    summary_saver: Callable[[int, str, str, str, str], None] = save_summary


def retry_operation(
    operation: Callable[[], Any],
    *,
    label: str,
    attempts: int,
    base_seconds: int,
    is_success: Callable[[Any], bool] | None = None,
) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            result = operation()
            if is_success is None or is_success(result):
                return result
            last_error = RuntimeError(f"{label} returned an unusable response")
        except Exception as exc:
            last_error = exc
        if attempt < attempts:
            delay = max(0, base_seconds) * (2 ** (attempt - 1))
            print(
                f"[DAILY RETRY] operation={label} | attempt={attempt}/{attempts} | "
                f"delay_seconds={delay} | error={last_error}"
            )
            if delay:
                time.sleep(delay)
    raise RuntimeError(f"{label} failed after {attempts} attempts: {last_error}")


def _candidate_from_values(
    source: str,
    url: str,
    title: str,
    publish_date: str | None,
    discovery_method: str,
) -> Candidate:
    normalized = canonical_url(url)
    trusted = is_trusted_source(normalized)
    return Candidate(
        source=source,
        url=normalized,
        title=" ".join((title or "").split()),
        publish_date=publish_date,
        discovery_method=discovery_method,
        source_tier="trusted" if trusted else "standard",
        recency_score=calculate_recency_score(publish_date),
    )


def discover_candidates(
    config: DailyIngestionConfig,
    feeds: list[dict[str, Any]] | None = None,
    manual_urls: list[str] | None = None,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    feeds = FEEDS if feeds is None else feeds
    manual_urls = DAILY_MANUAL_SOURCE_URLS if manual_urls is None else manual_urls
    source_discovery_limit = max(1, config.max_candidate_links // max(1, len(feeds)))

    def add(candidate: Candidate) -> bool:
        if len(candidates) >= config.max_candidate_links:
            return False
        candidates.append(candidate)
        return True

    for feed in feeds:
        if len(candidates) >= config.max_candidate_links:
            break
        source_start = len(candidates)
        source = feed["source"]
        if feed.get("type") == "rss":
            try:
                feed_text = retry_operation(
                    lambda: fetch_feed_text(feed["feed_url"]),
                    label=f"discover RSS {source}",
                    attempts=config.retry_attempts,
                    base_seconds=config.retry_base_seconds,
                    is_success=bool,
                )
            except RuntimeError as exc:
                print(f"[DAILY DISCOVERY ERROR] source={source} | error={exc}")
                continue
            parsed = feedparser.parse(feed_text) if feed_text else feedparser.parse("")
            for entry in parsed.entries:
                url = entry.get("link")
                title = html_to_text(entry.get("title", "")).strip()
                if url and title:
                    add(
                        _candidate_from_values(
                            source, url, title, parse_date(entry), "rss"
                        )
                    )
                if (
                    len(candidates) >= config.max_candidate_links
                    or len(candidates) - source_start >= source_discovery_limit
                ):
                    break
            continue

        homepage = feed.get("homepage")
        if not homepage or config.max_recursion_depth < 1:
            continue
        try:
            html = retry_operation(
                lambda: fetch_feed_text(homepage),
                label=f"discover index {source}",
                attempts=config.retry_attempts,
                base_seconds=config.retry_base_seconds,
                is_success=bool,
            )
        except RuntimeError as exc:
            print(f"[DAILY DISCOVERY ERROR] source={source} | error={exc}")
            continue
        links = extract_internal_links(html, homepage)
        prefix = feed.get("url_prefix")
        if prefix:
            links = [link for link in links if link["url"].startswith(prefix)]
        scored = sorted(
            links,
            key=lambda link: score_candidate_link(link["url"], link["anchor_text"]),
            reverse=True,
        )
        for link in scored:
            if len(candidates) - source_start >= source_discovery_limit:
                break
            if score_candidate_link(link["url"], link["anchor_text"]) <= 0:
                continue
            if not add(
                _candidate_from_values(
                    source,
                    link["url"],
                    link["anchor_text"],
                    None,
                    (
                        "newsletter_archive"
                        if feed.get("type") == "newsletter_archive"
                        else "index_page"
                    ),
                )
            ):
                break

    for url in manual_urls:
        if len(candidates) >= config.max_candidate_links:
            break
        host = (urlparse(url).hostname or "manual").removeprefix("www.")
        add(_candidate_from_values(host, url, "", None, "manual"))

    print(f"[DAILY DISCOVERY] candidates_discovered={len(candidates)}")
    return candidates


def deduplicate_candidates(candidates: list[Candidate]) -> list[Candidate]:
    unique: dict[str, Candidate] = {}
    for candidate in candidates:
        candidate.url = canonical_url(candidate.url)
        existing = unique.get(candidate.url)
        if existing is None:
            unique[candidate.url] = candidate
            continue
        if len(candidate.title) > len(existing.title):
            existing.title = candidate.title
        if candidate.publish_date and not existing.publish_date:
            existing.publish_date = candidate.publish_date
            existing.recency_score = calculate_recency_score(candidate.publish_date)
        if existing.discovery_method != candidate.discovery_method:
            existing.discovery_method = f"{existing.discovery_method}+{candidate.discovery_method}"
    return list(unique.values())


def score_candidate(candidate: Candidate) -> int:
    title = candidate.title.lower()
    title_relevance = min(sum(term in title for term in RELEVANCE_TERMS), 5)
    topic_match = min(
        sum(
            term in title
            for term in (
                "ai",
                "startup",
                "founder",
                "market",
                "software",
                "enterprise",
                "fintech",
                "infrastructure",
                "investment",
            )
        ),
        3,
    )
    source_score = 6 if candidate.source_tier == "trusted" else 2
    url_score = max(0, min(score_candidate_link(candidate.url, candidate.title), 10))
    return source_score + candidate.recency_score + title_relevance * 2 + topic_match + url_score


def triage_candidates(
    candidates: list[Candidate],
    processed_urls: set[str],
    config: DailyIngestionConfig,
) -> list[Candidate]:
    remaining = [candidate for candidate in candidates if candidate.url not in processed_urls]
    for candidate in remaining:
        candidate.triage_score = score_candidate(candidate)
    remaining.sort(
        key=lambda candidate: (
            -candidate.triage_score,
            -candidate.recency_score,
            candidate.source,
            candidate.url,
        )
    )
    selected = remaining[: config.max_pages_fetched]
    print(
        f"[DAILY TRIAGE] after_dedupe={len(candidates)} | "
        f"already_processed={len(candidates) - len(remaining)} | selected={len(selected)}"
    )
    return selected


def _article_from_candidate(
    candidate: Candidate,
    fetched: tuple[str, str | None, str | None, bool, str, str | None],
) -> dict[str, Any]:
    content, page_title, page_date, has_article, _raw_html, extraction_failure = fetched
    title = (page_title or candidate.title).strip()
    if not title:
        title = urlparse(candidate.url).path.rstrip("/").split("/")[-1] or candidate.url
    article = enrich_article(
        {
            "source": candidate.source,
            "title": title,
            "url": candidate.url,
            "author": None,
            "published_at": page_date or candidate.publish_date,
            "fetched_at": utc_now(),
            "content": content[:30000],
            "extraction_failure_reason": extraction_failure,
            "_has_article_element": has_article,
        }
    )
    return apply_ingestion_filters(article)


def _log_decision(article: dict[str, Any], accepted: bool, reason: str) -> None:
    print(
        f"[DAILY {'ACCEPT' if accepted else 'REJECT'}] source={article['source']} | "
        f"url={article['url']} | page_type={article['page_type']} | "
        f"quality_score={article['quality_score']} | content_type={article.get('content_type')} | "
        f"reason={reason}"
    )


def run_daily_ingestion(
    *,
    config: DailyIngestionConfig | None = None,
    dry_run: bool = False,
    preview: bool = False,
    discovered_candidates: list[Candidate] | None = None,
    feeds: list[dict[str, Any]] | None = None,
    manual_urls: list[str] | None = None,
    services: DailyIngestionServices | None = None,
) -> dict[str, Any]:
    config = config or DailyIngestionConfig()
    services = services or DailyIngestionServices()
    discovered = (
        discover_candidates(config, feeds, manual_urls)
        if discovered_candidates is None
        else discovered_candidates
    )
    discovered = discovered[: config.max_candidate_links]
    unique = deduplicate_candidates(discovered)
    processed = services.existing_url_loader([candidate.url for candidate in unique])
    selected = triage_candidates(unique, processed, config)

    report: dict[str, Any] = {
        "dry_run": dry_run,
        "preview": preview,
        "limits": asdict(config),
        "candidates_discovered": len(discovered),
        "candidates_after_dedupe": len(unique),
        "already_processed": len(processed),
        "pages_selected": len(selected),
        "pages_fetched": 0,
        "articles_accepted": 0,
        "articles_summarized": 0,
        "database_rows_written": 0,
        "rejection_reasons": {},
        "per_source_counts": {},
        "estimated_api_usage": {
            "summary_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        },
        "discovered_candidates": [asdict(candidate) for candidate in discovered],
        "selected_candidates": [asdict(candidate) for candidate in selected],
        "processed": [],
    }
    if dry_run:
        print("[DAILY DRY RUN] discovery and triage complete; fetch, AI, and writes skipped")
        return report

    rejection_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    operational_errors = 0
    for candidate in selected:
        if report["articles_summarized"] >= config.max_articles_summarized:
            break
        report["pages_fetched"] += 1
        try:
            fetched = retry_operation(
                lambda: services.page_fetcher(candidate.url),
                label=f"fetch {candidate.url}",
                attempts=config.retry_attempts,
                base_seconds=config.retry_base_seconds,
                is_success=lambda result: not (
                    result[-1] == "HTTP request failed" and not result[0]
                ),
            )
            article = _article_from_candidate(candidate, fetched)
        except Exception as exc:
            operational_errors += 1
            reason = f"fetch_or_classification_error: {exc}"
            rejection_counts[reason] += 1
            report["processed"].append(
                {"source": candidate.source, "url": candidate.url, "accepted": False, "reason": reason}
            )
            print(f"[DAILY ERROR] {candidate.url} | {reason}")
            continue

        reason = article.get("skip_reason")
        if article["page_type"] != ARTICLE:
            reason = reason or f"page_type={article['page_type']}"
        elif int(article.get("quality_score") or 0) < config.min_quality_score:
            reason = f"below_daily_quality_threshold: {article.get('quality_score')}"
        elif source_counts[article["source"]] >= config.max_per_source:
            reason = "max_per_source_reached"

        if reason:
            rejection_counts[reason] += 1
            _log_decision(article, False, reason)
            report["processed"].append(
                {
                    "source": article["source"],
                    "url": article["url"],
                    "page_type": article["page_type"],
                    "quality_score": article.get("quality_score"),
                    "quality_reasoning": article.get("quality_reasoning"),
                    "content_type": article.get("content_type"),
                    "content_type_reasoning": article.get("content_type_reasoning"),
                    "accepted": False,
                    "reason": reason,
                    "database_written": False,
                }
            )
            continue

        report["articles_accepted"] += 1
        source_counts[article["source"]] += 1
        try:
            summary, template = retry_operation(
                lambda: services.summary_generator(article),
                label=f"summarize {article['url']}",
                attempts=config.retry_attempts,
                base_seconds=config.retry_base_seconds,
                is_success=lambda result: bool(result[0].strip()),
            )
            if not preview:
                services.article_writer(article)
                stored = services.article_loader(article["url"])
                if not stored:
                    raise RuntimeError("article row was not found after upsert")
                services.summary_saver(
                    stored["id"], summary, OPENAI_MODEL, utc_now(), template
                )
        except Exception as exc:
            operational_errors += 1
            reason = f"summary_or_write_error: {exc}"
            rejection_counts[reason] += 1
            source_counts[article["source"]] -= 1
            print(f"[DAILY ERROR] {article['url']} | {reason}")
            report["processed"].append(
                {
                    "source": article["source"],
                    "url": article["url"],
                    "accepted": True,
                    "summarized": False,
                    "reason": reason,
                    "database_written": False,
                }
            )
            continue

        estimated_input = max(1, len(article.get("content") or "") // 4)
        estimated_output = max(1, len(summary) // 4)
        report["articles_summarized"] += 1
        if not preview:
            report["database_rows_written"] += 1
        report["estimated_api_usage"]["summary_calls"] += 1
        report["estimated_api_usage"]["input_tokens"] += estimated_input
        report["estimated_api_usage"]["output_tokens"] += estimated_output
        _log_decision(article, True, "summarized")
        report["processed"].append(
            {
                "source": article["source"],
                "url": article["url"],
                "page_type": article["page_type"],
                "quality_score": article.get("quality_score"),
                "quality_reasoning": article.get("quality_reasoning"),
                "content_type": article.get("content_type"),
                "content_type_reasoning": article.get("content_type_reasoning"),
                "accepted": True,
                "summarized": True,
                "summary_template": template,
                "summary": summary,
                "database_written": not preview,
            }
        )

    report["rejection_reasons"] = dict(rejection_counts)
    report["per_source_counts"] = dict(source_counts)
    report["operational_errors"] = operational_errors
    print(
        f"[DAILY COMPLETE] fetched={report['pages_fetched']} | "
        f"accepted={report['articles_accepted']} | "
        f"summarized={report['articles_summarized']} | per_source={dict(source_counts)} | "
        f"api_usage={report['estimated_api_usage']}"
    )
    return report
