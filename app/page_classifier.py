from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


ARTICLE = "ARTICLE"
INDEX_PAGE = "INDEX_PAGE"
AUTHOR_PAGE = "AUTHOR_PAGE"
PODCAST_PAGE = "PODCAST_PAGE"
NEWSLETTER_ARCHIVE = "NEWSLETTER_ARCHIVE"
LOW_VALUE_PAGE = "LOW_VALUE_PAGE"

PAGE_TYPES = {
    ARTICLE,
    INDEX_PAGE,
    AUTHOR_PAGE,
    PODCAST_PAGE,
    NEWSLETTER_ARCHIVE,
    LOW_VALUE_PAGE,
}


@dataclass(frozen=True)
class PageClassification:
    page_type: str
    reason: str


def path_parts(url: str) -> list[str]:
    return [part.lower() for part in urlparse(url).path.split("/") if part]


def classify_page(
    *,
    url: str,
    title: str,
    content: str,
    published_at: str | None = None,
    has_article_element: bool = False,
) -> PageClassification:
    parts = path_parts(url)
    path = "/".join(parts)
    normalized_title = " ".join((title or "").lower().split())
    normalized_content = " ".join((content or "").lower().split())
    count = len(normalized_content.split())

    if any(part in {"author", "authors", "people", "team"} for part in parts):
        return PageClassification(AUTHOR_PAGE, "author/profile URL pattern")
    if normalized_title.startswith(("author:", "articles by ", "posts by ")):
        return PageClassification(AUTHOR_PAGE, "author archive title pattern")

    if any(part in {"podcast", "podcasts"} for part in parts):
        return PageClassification(PODCAST_PAGE, "podcast URL pattern")
    if "podcast" in normalized_title or normalized_title.startswith("episode "):
        return PageClassification(PODCAST_PAGE, "podcast title pattern")

    if parts and parts[-1] in {"newsletter", "newsletters", "archive", "archives"}:
        return PageClassification(
            NEWSLETTER_ARCHIVE, "newsletter/archive listing URL pattern"
        )
    if any(
        phrase in normalized_title
        for phrase in ("newsletter archive", "all newsletters", "past issues")
    ):
        return PageClassification(NEWSLETTER_ARCHIVE, "newsletter archive title")

    low_value_parts = {
        "about",
        "careers",
        "career",
        "jobs",
        "job",
        "events",
        "event",
        "contact",
        "portfolio",
        "companies",
        "terms",
        "privacy",
        "login",
        "signup",
        "subscribe",
    }
    if any(part in low_value_parts for part in parts):
        return PageClassification(LOW_VALUE_PAGE, "low-value URL pattern")
    if count < 200:
        return PageClassification(LOW_VALUE_PAGE, "insufficient extracted content")

    index_parts = {
        "blog",
        "insights",
        "stories",
        "resources",
        "library",
        "atlas",
        "topics",
        "categories",
        "category",
        "tags",
        "tag",
        "ai",
        "enterprise",
        "consumer",
        "infra",
        "infrastructure",
    }
    index_titles = {
        "blog",
        "insights",
        "stories",
        "resources",
        "resource library",
        "latest articles",
        "all articles",
    }
    if normalized_title in index_titles:
        return PageClassification(INDEX_PAGE, "collection page title")
    if parts and parts[-1] in index_parts and not published_at:
        return PageClassification(INDEX_PAGE, "collection/topic URL without publish date")
    if len(parts) <= 1 and not published_at and not has_article_element:
        return PageClassification(INDEX_PAGE, "top-level content hub without article signals")

    article_path_markers = {"post", "posts", "article", "articles", "blog"}
    if published_at:
        return PageClassification(ARTICLE, "standalone page with publish date")
    if has_article_element:
        return PageClassification(ARTICLE, "page contains an article element")
    if any(part in article_path_markers for part in parts) and len(parts) >= 2:
        return PageClassification(ARTICLE, "standalone article URL pattern")
    if count >= 1000:
        return PageClassification(ARTICLE, "substantial standalone page content")

    return PageClassification(LOW_VALUE_PAGE, "no reliable standalone article signals")
