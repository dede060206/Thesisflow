from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
    MAX_ARTICLE_AGE_DAYS,
    MIN_ARTICLE_DATE,
    SOURCE_PRIORITY,
)
from app.database import upsert_article


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


def is_recent_enough(published_at: str | None) -> bool:
    published = parse_iso_datetime(published_at)
    if not published:
        return False

    min_date = datetime.fromisoformat(MIN_ARTICLE_DATE).replace(tzinfo=timezone.utc)
    if published < min_date:
        return False

    newest_allowed = datetime.now(timezone.utc) - timedelta(days=MAX_ARTICLE_AGE_DAYS)
    return published >= newest_allowed


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
    article["is_long_form"] = 1 if count > LONG_FORM_WORD_THRESHOLD else 0
    article["category"] = categorize_article(
        article.get("title", ""),
        article.get("content") or "",
    )
    return article


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


def fetch_article_page_data(url: str) -> tuple[str, str | None, str | None]:
    try:
        response = httpx.get(
            url,
            timeout=20,
            headers={"User-Agent": "vc-blog-aggregator-mvp/0.1"},
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return "", None, None

    soup = BeautifulSoup(response.text, "html.parser")
    article = soup.find("article") or soup.find("main") or soup.body
    title_tag = soup.find("h1") or soup.find("title")
    title = html_to_text(title_tag.get_text(" ")) if title_tag else None
    published_at = extract_page_date(soup)
    return (html_to_text(str(article)) if article else ""), title, published_at


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


def fetch_homepage_articles(feed: dict[str, Any], max_items: int) -> list[dict[str, Any]]:
    html = fetch_feed_text(feed["homepage"])
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    articles: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for link in soup.find_all("a", href=True):
        url = urljoin(feed["homepage"], link["href"])
        if url in seen_urls or not is_homepage_article_url(url, feed):
            continue

        seen_urls.add(url)
        content, page_title, published_at = fetch_article_page_data(url)
        title = (page_title or html_to_text(link.get_text(" "))).strip()
        if len(title) < 12:
            continue

        article = enrich_article(
            {
                "source": feed["source"],
                "title": title,
                "url": url,
                "author": None,
                "published_at": published_at,
                "fetched_at": utc_now(),
                "content": content[:30000],
            }
        )
        if not is_long_enough(article):
            continue
        if not is_recent_enough(article["published_at"]):
            continue

        articles.append(article)

        if len(articles) >= max_items:
            break

    return articles


def fetch_rss_articles(feed: dict[str, Any], max_items: int) -> list[dict[str, Any]]:
    feed_text = fetch_feed_text(feed["feed_url"])
    parsed = feedparser.parse(feed_text) if feed_text else feedparser.parse("")
    articles: list[dict[str, Any]] = []

    for entry in parsed.entries[:max_items]:
        url = entry.get("link")
        title = html_to_text(entry.get("title", "")).strip()
        if not url or not title:
            continue

        content = entry_content(entry)
        if len(content) < 500:
            page_content = fetch_article_page(url)
            content = page_content or content

        article = enrich_article(
            {
                "source": feed["source"],
                "title": title,
                "url": url,
                "author": entry.get("author"),
                "published_at": parse_date(entry),
                "fetched_at": utc_now(),
                "content": content[:30000],
            }
        )
        if not is_long_enough(article):
            continue
        if not is_recent_enough(article["published_at"]):
            continue

        articles.append(article)

    return articles


def article_sort_key(article: dict[str, Any]) -> tuple[int, int, int, str]:
    source_rank = SOURCE_PRIORITY.get(article["source"], len(SOURCE_PRIORITY))
    timestamp = article.get("published_at") or article.get("fetched_at") or ""
    return (
        -int(article.get("is_long_form") or 0),
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
    candidates: list[dict[str, Any]] = []

    for feed in FEEDS:
        if feed.get("type") == "homepage":
            articles = fetch_homepage_articles(feed, max_per_feed)
        else:
            articles = fetch_rss_articles(feed, max_per_feed)

        candidates.extend(articles)

    for article in select_articles_for_insert(candidates, insert_limit):
        if inserted >= insert_limit:
            break
        was_inserted = upsert_article(article)
        if was_inserted:
            inserted += 1

    return {"seen": len(candidates), "inserted": inserted, "limit": insert_limit}
