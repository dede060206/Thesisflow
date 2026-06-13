from __future__ import annotations

import re
import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

from app.config import (
    DAILY_ARTICLE_LIMIT,
    FEEDS,
    LONG_FORM_WORD_THRESHOLD,
    MIN_ARTICLE_DATE,
    QUALITY_SCORE_THRESHOLD,
    SOURCE_PRIORITY,
)
from app.content_quality import score_content_quality
from app.content_type_classifier import classify_content_type
from app.database import upsert_article
from app.page_classifier import ARTICLE, INDEX_PAGE, NEWSLETTER_ARCHIVE, classify_page


CATEGORY_KEYWORDS = {
    "AI": ["ai", "artificial intelligence", "machine learning", "llm", "agent", "model"],
    "SaaS": ["saas", "software", "enterprise", "subscription", "arr", "gtm"],
    "Fintech": ["fintech", "banking", "payments", "crypto", "insurance", "lending"],
    "Consumer": ["consumer", "social", "creator", "marketplace", "commerce", "gaming"],
    "Healthcare": ["health", "healthcare", "biotech", "clinical", "patient", "medical"],
    "Developer Tools": [
        "developer",
        "devtools",
        "api",
        "infrastructure",
        "cloud",
        "database",
        "security",
        "open source",
    ],
    "Fundraising": [
        "fundraising",
        "seed",
        "series a",
        "series b",
        "venture",
        "capital",
        "valuation",
        "pitch",
    ],
    "Market Analysis": ["market", "analysis", "trend", "economy", "macro", "forecast", "report"],
}

IGNORED_LINK_PARTS = {
    "about",
    "careers",
    "career",
    "jobs",
    "job",
    "events",
    "event",
    "contact",
    "privacy",
    "terms",
    "login",
    "signup",
    "newsletter",
    "newsletters",
    "tag",
    "tags",
    "category",
    "categories",
    "author",
    "authors",
}

ARTICLE_LINK_PARTS = {
    "article",
    "articles",
    "essay",
    "essays",
    "post",
    "posts",
    "blog",
    "news",
    "insight",
    "insights",
    "story",
    "stories",
}

RELEVANCE_TERMS = {
    "venture",
    "capital",
    "startup",
    "startups",
    "founder",
    "founders",
    "invest",
    "investing",
    "investment",
    "ai",
    "artificial intelligence",
    "technology",
    "software",
    "market",
    "markets",
    "saas",
    "fintech",
    "enterprise",
}

TRUSTED_SOURCE_HOSTS = {
    "a16z.com",
    "sequoiacap.com",
    "firstround.com",
    "review.firstround.com",
    "benchmark.com",
    "abovethecrowd.com",
    "ycombinator.com",
    "lsvp.com",
    "lightspeedvp.com",
    "nfx.com",
    "redpoint.com",
    "bvp.com",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_date(entry: Any) -> str | None:
    raw_date = entry.get("published") or entry.get("updated")
    if not raw_date:
        return None
    try:
        return parsedate_to_datetime(raw_date).astimezone(timezone.utc).isoformat(
            timespec="seconds"
        )
    except Exception:
        return None


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        return None


def calculate_recency_score(published_at: str | None) -> int:
    published = parse_iso_datetime(published_at)
    if not published:
        return 2
    age_days = max(0, (datetime.now(timezone.utc) - published).days)
    if age_days <= 15:
        return 10
    if age_days <= 45:
        return 8
    if age_days <= 90:
        return 6
    if age_days <= 180:
        return 4
    return 2


def is_before_minimum_article_date(published_at: str | None) -> bool:
    published = parse_iso_datetime(published_at)
    if not published:
        return False
    minimum = datetime.fromisoformat(MIN_ARTICLE_DATE).replace(tzinfo=timezone.utc)
    return published < minimum


def is_trusted_source(url: str) -> bool:
    host = internal_hostname(url)
    return any(host == trusted or host.endswith(f".{trusted}") for trusted in TRUSTED_SOURCE_HOSTS)


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(" ").split())


def word_count(text: str) -> int:
    return len([word for word in text.split() if word.strip()])


def categorize_article(title: str, content: str) -> str:
    haystack = f"{title} {content[:5000]}".lower()
    scores = {
        category: sum(1 for keyword in keywords if keyword in haystack)
        for category, keywords in CATEGORY_KEYWORDS.items()
    }
    best_category, best_score = max(scores.items(), key=lambda item: item[1])
    return best_category if best_score else "Market Analysis"


def enrich_article(article: dict[str, Any]) -> dict[str, Any]:
    count = word_count(article.get("content") or "")
    article["word_count"] = count
    article["is_long_form"] = count > LONG_FORM_WORD_THRESHOLD
    article["category"] = categorize_article(
        article.get("title", ""),
        article.get("content") or "",
    )
    article["trusted_source"] = is_trusted_source(article.get("url", ""))
    article["source_tier"] = "trusted" if article["trusted_source"] else "standard"
    article["recency_score"] = calculate_recency_score(article.get("published_at"))
    quality = score_content_quality(
        article.get("title", ""),
        article.get("content") or "",
        trusted_source=article["trusted_source"],
    )
    article["quality_score"] = quality.score
    article["quality_reasoning"] = quality.reasoning
    article["_quality_components"] = quality.components
    article["content_type"] = None
    article["content_type_reasoning"] = None
    classification = classify_page(
        url=article.get("url", ""),
        title=article.get("title", ""),
        content=article.get("content") or "",
        published_at=article.get("published_at"),
        has_article_element=bool(article.pop("_has_article_element", False)),
    )
    article["page_type"] = classification.page_type
    article["classification_reason"] = classification.reason
    article["skip_reason"] = (
        None
        if classification.page_type == ARTICLE
        else f"page_type={classification.page_type}: {classification.reason}"
    )
    return article


def apply_ingestion_filters(article: dict[str, Any]) -> dict[str, Any]:
    if article["page_type"] != ARTICLE:
        return article
    if is_before_minimum_article_date(article.get("published_at")):
        article["skip_reason"] = (
            f"published_before_minimum_date: {article['published_at']} < "
            f"{MIN_ARTICLE_DATE}"
        )
        return article
    if article["quality_score"] < QUALITY_SCORE_THRESHOLD:
        article["skip_reason"] = (
            f"below_quality_threshold: {article['quality_score']} < "
            f"{QUALITY_SCORE_THRESHOLD}"
        )
        return article

    content_type = classify_content_type(
        article.get("title", ""),
        article.get("content") or "",
    )
    article["content_type"] = content_type.content_type
    article["content_type_reasoning"] = content_type.reasoning

    minimum_words = 500 if article["trusted_source"] else 800
    evidence_score = int(article.get("_quality_components", {}).get("evidence", 0))
    if (
        article["word_count"] < minimum_words
        and not (
            not article["trusted_source"]
            and article["word_count"] >= 500
            and evidence_score == 2
        )
    ):
        article["skip_reason"] = (
            f"below_source_aware_depth_threshold: {article['word_count']} < "
            f"{minimum_words} words for {article['source_tier']} source"
        )
    return article


def log_page_decision(article: dict[str, Any]) -> None:
    quality_accepted = (
        article["page_type"] == ARTICLE
        and article["quality_score"] >= QUALITY_SCORE_THRESHOLD
    )
    print(
        f"[QUALITY {'ACCEPT' if quality_accepted else 'REJECT'}] "
        f"{article['url']} | page_type={article['page_type']} | "
        f"quality_score={article['quality_score']} | "
        f"{article['quality_reasoning']}"
    )
    print(
        f"[RANKING] {article['url']} | source_tier={article['source_tier']} | "
        f"recency_score={article['recency_score']}"
    )
    if article.get("extraction_failure_reason"):
        print(
            f"[EXTRACTION WARNING] {article['url']} | "
            f"{article['extraction_failure_reason']}"
        )
    if article.get("content_type"):
        print(
            f"[CONTENT TYPE] {article['url']} | page_type={article['page_type']} | "
            f"quality_score={article['quality_score']} | "
            f"content_type={article['content_type']} | "
            f"{article['content_type_reasoning']}"
        )
    if article.get("skip_reason"):
        print(
            f"[SKIP] {article['page_type']} | {article['source']} | "
            f"{article['url']} | {article['skip_reason']}"
        )
    else:
        print(
            f"[ACCEPT] ARTICLE | {article['source']} | {article['url']} | "
            f"{article.get('classification_reason', 'article signals')} | "
            f"{article['word_count']} words"
        )


def canonical_url(url: str) -> str:
    parsed = urlparse(url)
    normalized_path = parsed.path or "/"
    if normalized_path != "/":
        normalized_path = normalized_path.rstrip("/")
    return parsed._replace(path=normalized_path, query="", fragment="").geturl()


def internal_hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def extract_internal_links(html: str, page_url: str) -> list[dict[str, str]]:
    if not html:
        return []
    page_host = internal_hostname(page_url)
    current_url = canonical_url(page_url)
    links_by_url: dict[str, dict[str, str]] = {}
    soup = BeautifulSoup(html, "html.parser")

    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        url = canonical_url(urljoin(page_url, href))
        if internal_hostname(url) != page_host or url == current_url:
            continue
        parts = {part.lower() for part in urlparse(url).path.split("/") if part}
        if parts & IGNORED_LINK_PARTS:
            continue
        anchor_text = html_to_text(link.get_text(" ")).strip()
        existing = links_by_url.get(url)
        if not existing or len(anchor_text) > len(existing["anchor_text"]):
            links_by_url[url] = {"url": url, "anchor_text": anchor_text}

    return list(links_by_url.values())


def score_candidate_link(url: str, anchor_text: str) -> int:
    parsed = urlparse(url)
    parts = [part.lower() for part in parsed.path.split("/") if part]
    path_text = " ".join(parts)
    normalized_anchor = " ".join(anchor_text.lower().split())
    combined = f"{path_text} {normalized_anchor}"
    score = 0

    if any(part in ARTICLE_LINK_PARTS for part in parts):
        score += 5
    if re.search(r"/(?:19|20)\d{2}(?:/\d{1,2})?(?:/\d{1,2})?(?:/|$)", parsed.path):
        score += 4
    if len(parts) >= 2:
        score += 2
    if 20 <= len(anchor_text) <= 160:
        score += 4
    elif 8 <= len(anchor_text) <= 220:
        score += 2
    if normalized_anchor in {"read more", "learn more", "view all", "more"}:
        score -= 4
    score += min(sum(1 for term in RELEVANCE_TERMS if term in combined), 5)
    return score


def select_candidate_links(
    links: list[dict[str, str]], limit: int = 5
) -> list[dict[str, Any]]:
    scored = [
        {**link, "score": score_candidate_link(link["url"], link["anchor_text"])}
        for link in links
    ]
    scored.sort(
        key=lambda item: (-item["score"], -len(item["anchor_text"]), item["url"])
    )
    return [item for item in scored if item["score"] > 0][:limit]


def fetch_article_page(url: str) -> str:
    try:
        response = httpx.get(
            url,
            timeout=20,
            headers={"User-Agent": "vc-blog-aggregator-mvp/0.1"},
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return ""

    soup = BeautifulSoup(response.text, "html.parser")
    article = soup.find("article") or soup.find("main") or soup.body
    return html_to_text(str(article)) if article else ""


def extract_page_date(soup: BeautifulSoup) -> str | None:
    selectors = [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"name": "article:published_time"}),
        ("meta", {"name": "pubdate"}),
        ("meta", {"name": "publish-date"}),
        ("meta", {"name": "date"}),
    ]
    for tag_name, attrs in selectors:
        tag = soup.find(tag_name, attrs=attrs)
        content = tag.get("content") if tag else None
        parsed = parse_iso_datetime(content)
        if parsed:
            return parsed.isoformat(timespec="seconds")

    time_tag = soup.find("time")
    if time_tag:
        parsed = parse_iso_datetime(time_tag.get("datetime"))
        if parsed:
            return parsed.isoformat(timespec="seconds")
    return None


def extract_page_title(soup: BeautifulSoup) -> str | None:
    for attrs in (
        {"property": "og:title"},
        {"name": "twitter:title"},
    ):
        tag = soup.find("meta", attrs=attrs)
        content = tag.get("content") if tag else None
        if content:
            return html_to_text(content).strip()
    title_tag = soup.find("h1") or soup.find("title")
    return html_to_text(title_tag.get_text(" ")).strip() if title_tag else None


def json_ld_article_body(soup: BeautifulSoup) -> str:
    def find_body(value: Any) -> str:
        if isinstance(value, dict):
            body = value.get("articleBody")
            if isinstance(body, str):
                return body
            for child in value.values():
                found = find_body(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = find_body(child)
                if found:
                    return found
        return ""

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            body = find_body(json.loads(script.string or script.get_text()))
        except (json.JSONDecodeError, TypeError):
            continue
        if body:
            return " ".join(body.split())
    return ""


def extract_page_content(soup: BeautifulSoup, url: str) -> tuple[str, bool, str | None]:
    article_element = soup.find("article")
    primary = article_element or soup.find("main") or soup.body
    content = html_to_text(str(primary)) if primary else ""

    if internal_hostname(url) == "sequoiacap.com" and word_count(content) < 500:
        candidates = [content, json_ld_article_body(soup)]
        for selector in (
            "[class*='article-body']",
            "[class*='content-body']",
            "[class*='entry-content']",
            "[class*='post-content']",
            "main [class*='content']",
        ):
            candidates.extend(html_to_text(str(node)) for node in soup.select(selector))
        content = max(candidates, key=word_count, default=content)

    count = word_count(content)
    failure_reason = None
    if not content:
        failure_reason = "no article, main, body, or structured article content found"
    elif count < 200:
        failure_reason = f"only {count} words extracted; page may require rendered-content fallback"
    return content, article_element is not None, failure_reason


def fetch_article_page_data(
    url: str,
) -> tuple[str, str | None, str | None, bool, str, str | None]:
    try:
        response = httpx.get(
            url,
            timeout=20,
            headers={"User-Agent": "vc-blog-aggregator-mvp/0.1"},
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return "", None, None, False, "", "HTTP request failed"

    soup = BeautifulSoup(response.text, "html.parser")
    content, has_article_element, extraction_failure_reason = extract_page_content(soup, url)
    title = extract_page_title(soup)
    published_at = extract_page_date(soup)
    return (
        content,
        title,
        published_at,
        has_article_element,
        response.text,
        extraction_failure_reason,
    )


def fetch_feed_text(url: str) -> str:
    try:
        response = httpx.get(
            url,
            timeout=20,
            headers={"User-Agent": "vc-blog-aggregator-mvp/0.1"},
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.text
    except httpx.HTTPError:
        return ""


def entry_content(entry: Any) -> str:
    if entry.get("content"):
        return html_to_text(entry.content[0].value)
    if entry.get("summary"):
        return html_to_text(entry.summary)
    return ""


def is_homepage_article_url(url: str, feed: dict[str, Any]) -> bool:
    parsed = urlparse(url)
    prefix = feed.get("url_prefix", "")
    if prefix and not url.startswith(prefix):
        return False
    if any(parsed.path == path for path in feed.get("exclude_paths", [])):
        return False
    path_parts = [part for part in parsed.path.split("/") if part]
    return bool(path_parts) and all("." not in part for part in path_parts)


def is_long_enough(article: dict[str, Any]) -> bool:
    return int(article.get("word_count") or 0) > LONG_FORM_WORD_THRESHOLD


def fetch_classified_url(
    *,
    feed: dict[str, Any],
    url: str,
    title_hint: str = "",
    author: str | None = None,
    published_hint: str | None = None,
    content_hint: str = "",
    visited_urls: set[str],
    depth: int = 0,
) -> list[dict[str, Any]]:
    url = canonical_url(url)
    if url in visited_urls:
        print(f"[CRAWL SKIP] {url} | already fetched in this run")
        return []
    visited_urls.add(url)

    content, page_title, page_date, has_article_element, raw_html, extraction_failure_reason = (
        fetch_article_page_data(url)
    )
    content = content or content_hint
    title = (page_title or title_hint).strip()
    if not title:
        title = urlparse(url).path.rstrip("/").split("/")[-1] or url

    article = enrich_article(
        {
            "source": feed["source"],
            "title": title,
            "url": url,
            "author": author,
            "published_at": page_date or published_hint,
            "fetched_at": utc_now(),
            "content": content[:30000],
            "extraction_failure_reason": extraction_failure_reason,
            "_has_article_element": has_article_element,
        }
    )
    apply_ingestion_filters(article)
    log_page_decision(article)
    pages = [article]

    if article["page_type"] not in {INDEX_PAGE, NEWSLETTER_ARCHIVE}:
        return pages
    if depth >= 1:
        print(f"[CRAWL STOP] {url} | max recursion depth 1 reached")
        return pages

    links = extract_internal_links(raw_html, url)
    candidates = select_candidate_links(links, limit=5)
    print(f"[CRAWL INDEX] {url} | extracted_links={len(links)}")
    print(
        f"[CRAWL TOP] {url} | "
        + (", ".join(f"{item['url']} (score={item['score']})" for item in candidates) or "none")
    )

    accepted_urls: list[str] = []
    for candidate in candidates:
        child_pages = fetch_classified_url(
            feed=feed,
            url=candidate["url"],
            title_hint=candidate["anchor_text"],
            visited_urls=visited_urls,
            depth=depth + 1,
        )
        pages.extend(child_pages)
        accepted_urls.extend(
            child["url"]
            for child in child_pages
            if child["page_type"] == ARTICLE and not child.get("skip_reason")
        )
    print(
        f"[CRAWL ACCEPTED] {url} | "
        + (", ".join(accepted_urls) or "none")
    )
    return pages


def fetch_homepage_articles(
    feed: dict[str, Any],
    max_items: int,
    visited_urls: set[str] | None = None,
) -> list[dict[str, Any]]:
    visited_urls = visited_urls if visited_urls is not None else set()
    pages = fetch_classified_url(
        feed=feed,
        url=feed["homepage"],
        visited_urls=visited_urls,
    )
    return pages[: max_items + 1]


def fetch_rss_articles(
    feed: dict[str, Any],
    max_items: int,
    visited_urls: set[str] | None = None,
) -> list[dict[str, Any]]:
    feed_text = fetch_feed_text(feed["feed_url"])
    parsed = feedparser.parse(feed_text) if feed_text else feedparser.parse("")
    articles: list[dict[str, Any]] = []
    visited_urls = visited_urls if visited_urls is not None else set()

    for entry in parsed.entries[:max_items]:
        url = entry.get("link")
        title = html_to_text(entry.get("title", "")).strip()
        if not url or not title:
            continue

        articles.extend(
            fetch_classified_url(
                feed=feed,
                url=url,
                title_hint=title,
                author=entry.get("author"),
                published_hint=parse_date(entry),
                content_hint=entry_content(entry),
                visited_urls=visited_urls,
            )
        )

    return articles


def article_sort_key(article: dict[str, Any]) -> tuple[int, int, int, int, int, str]:
    source_rank = SOURCE_PRIORITY.get(article["source"], len(SOURCE_PRIORITY))
    timestamp = article.get("published_at") or article.get("fetched_at") or ""
    return (
        -int(article.get("quality_score") or 0),
        -int(article.get("recency_score") or 0),
        -int(article.get("trusted_source") or 0),
        source_rank,
        -int(article.get("word_count") or 0),
        timestamp,
    )


def select_articles_for_insert(
    candidates: list[dict[str, Any]], insert_limit: int
) -> list[dict[str, Any]]:
    by_source: dict[str, list[dict[str, Any]]] = {}
    for article in sorted(candidates, key=article_sort_key):
        by_source.setdefault(article["source"], []).append(article)

    selected: list[dict[str, Any]] = []
    source_order = sorted(by_source, key=lambda source: SOURCE_PRIORITY.get(source, 999))

    while len(selected) < insert_limit:
        added_this_round = False
        for source in source_order:
            if by_source[source]:
                selected.append(by_source[source].pop(0))
                added_this_round = True
                if len(selected) >= insert_limit:
                    break
        if not added_this_round:
            break

    return selected


def fetch_all_feeds(
    max_per_feed: int = 20, insert_limit: int = DAILY_ARTICLE_LIMIT
) -> dict[str, int]:
    inserted = 0
    skipped = 0
    skipped_stored = 0
    candidates: list[dict[str, Any]] = []
    visited_urls: set[str] = set()

    for feed in FEEDS:
        if feed.get("type") == "homepage":
            articles = fetch_homepage_articles(feed, max_per_feed, visited_urls)
        else:
            articles = fetch_rss_articles(feed, max_per_feed, visited_urls)

        for article in articles:
            if article.get("skip_reason"):
                skipped += 1
                upsert_article(article)
                skipped_stored += 1
            else:
                candidates.append(article)

    for article in select_articles_for_insert(candidates, insert_limit):
        if inserted >= insert_limit:
            break
        was_inserted = upsert_article(article)
        if was_inserted:
            inserted += 1

    return {
        "seen": len(candidates) + skipped,
        "accepted": len(candidates),
        "skipped": skipped,
        "skipped_stored": skipped_stored,
        "inserted": inserted,
        "limit": insert_limit,
    }
