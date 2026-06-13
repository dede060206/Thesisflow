from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

def env_str(name: str, default: str = "") -> str:
    return os.getenv(name) or default


def env_int(name: str, default: int) -> int:
    return int(env_str(name, str(default)))


APP_NAME = env_str("APP_NAME", "Thesisflow")
DATABASE_URL = env_str("DATABASE_URL")
OPENAI_API_KEY = env_str("OPENAI_API_KEY")
OPENAI_MODEL = env_str("OPENAI_MODEL", "gpt-4.1-mini")
CHAT_MODEL = env_str("CHAT_MODEL", OPENAI_MODEL)
WEEKLY_REPORT_MODEL = env_str("WEEKLY_REPORT_MODEL", CHAT_MODEL)
WEEKLY_REPORT_BATCH_SIZE = env_int("WEEKLY_REPORT_BATCH_SIZE", 12)
EMBEDDING_MODEL = env_str("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = env_int("EMBEDDING_DIMENSIONS", 1536)
CHAT_TOP_K = env_int("CHAT_TOP_K", 6)
ARTICLE_CHUNK_WORDS = env_int("ARTICLE_CHUNK_WORDS", 450)
ARTICLE_CHUNK_OVERLAP_WORDS = env_int("ARTICLE_CHUNK_OVERLAP_WORDS", 60)
CRON_SECRET = env_str("CRON_SECRET")
WORKSPACE_SECRET = env_str(
    "WORKSPACE_SECRET", CRON_SECRET or "thesisflow-local-development"
)
THESIS_MODEL = env_str("THESIS_MODEL", CHAT_MODEL)
THESIS_MAX_EVIDENCE = env_int("THESIS_MAX_EVIDENCE", 20)
THESIS_MAX_PER_WORKSPACE = env_int("THESIS_MAX_PER_WORKSPACE", 25)
DAILY_ARTICLE_LIMIT = env_int("DAILY_ARTICLE_LIMIT", 20)
DAILY_MAX_CANDIDATE_LINKS = env_int("DAILY_MAX_CANDIDATE_LINKS", 80)
DAILY_MAX_PAGES_FETCHED = env_int("DAILY_MAX_PAGES_FETCHED", 30)
DAILY_MAX_ARTICLES_SUMMARIZED = env_int("DAILY_MAX_ARTICLES_SUMMARIZED", 8)
DAILY_MIN_QUALITY_SCORE = env_int("DAILY_MIN_QUALITY_SCORE", 7)
DAILY_MAX_PER_SOURCE = env_int("DAILY_MAX_PER_SOURCE", 3)
DAILY_MAX_RECURSION_DEPTH = env_int("DAILY_MAX_RECURSION_DEPTH", 1)
DAILY_RETRY_ATTEMPTS = env_int("DAILY_RETRY_ATTEMPTS", 3)
DAILY_RETRY_BASE_SECONDS = env_int("DAILY_RETRY_BASE_SECONDS", 2)
INGESTION_ALERT_WEBHOOK_URL = env_str("INGESTION_ALERT_WEBHOOK_URL")
DAILY_MANUAL_SOURCE_URLS = [
    url.strip()
    for url in env_str("DAILY_MANUAL_SOURCE_URLS").split(",")
    if url.strip()
]
LONG_FORM_WORD_THRESHOLD = env_int("LONG_FORM_WORD_THRESHOLD", 1000)
MIN_ARTICLE_DATE = env_str("MIN_ARTICLE_DATE", "2025-09-01")
MAX_ARTICLE_AGE_DAYS = env_int("MAX_ARTICLE_AGE_DAYS", 15)
TOP_READS_MAX_AGE_DAYS = env_int("TOP_READS_MAX_AGE_DAYS", 7)
QUALITY_SCORE_THRESHOLD = env_int("QUALITY_SCORE_THRESHOLD", 7)

CATEGORIES = [
    "AI",
    "SaaS",
    "Fintech",
    "Consumer",
    "Healthcare",
    "Developer Tools",
    "Fundraising",
    "Market Analysis",
]

FEEDS = [
    {
        "source": "Andreessen Horowitz",
        "type": "homepage",
        "homepage": "https://a16z.com/ai/",
        "url_prefix": "https://a16z.com/",
        "exclude_paths": ["/ai/"],
    },
    {
        "source": "Sequoia",
        "type": "rss",
        "feed_url": "https://www.sequoiacap.com/feed/",
        "homepage": "https://www.sequoiacap.com/",
    },
    {
        "source": "Benchmark",
        "type": "rss",
        "feed_url": "https://abovethecrowd.com/feed/",
        "homepage": "https://www.benchmark.com/",
        "note": "Benchmark 官方站点未暴露博客 RSS；MVP 使用 Benchmark 合伙人 Bill Gurley 的 Above the Crowd。",
    },
    {
        "source": "Lightspeed",
        "type": "homepage",
        "homepage": "https://lsvp.com/stories/",
        "url_prefix": "https://lsvp.com/stories/",
        "exclude_paths": ["/stories/"],
    },
    {
        "source": "Y Combinator",
        "type": "rss",
        "feed_url": "https://www.ycombinator.com/blog/rss",
        "homepage": "https://www.ycombinator.com/blog",
    },
    {
        "source": "NFX",
        "type": "homepage",
        "homepage": "https://www.nfx.com/library/essays",
        "url_prefix": "https://www.nfx.com/post/",
    },
    {
        "source": "Redpoint",
        "type": "homepage",
        "homepage": "https://www.redpoint.com/blog/",
        "url_prefix": "https://www.redpoint.com/blog/",
    },
    {
        "source": "Bessemer",
        "type": "homepage",
        "homepage": "https://www.bvp.com/atlas",
        "url_prefix": "https://www.bvp.com/atlas/",
    },
]

SOURCE_PRIORITY = {feed["source"]: index for index, feed in enumerate(FEEDS)}

INVESTORS = {
    "a16z": "Andreessen Horowitz",
    "sequoia": "Sequoia",
    "benchmark": "Benchmark",
    "lightspeed": "Lightspeed",
    "yc": "Y Combinator",
    "nfx": "NFX",
    "redpoint": "Redpoint",
    "bessemer": "Bessemer",
}
