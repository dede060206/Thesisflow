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
CRON_SECRET = env_str("CRON_SECRET")
DAILY_ARTICLE_LIMIT = env_int("DAILY_ARTICLE_LIMIT", 20)
LONG_FORM_WORD_THRESHOLD = env_int("LONG_FORM_WORD_THRESHOLD", 1000)
MIN_ARTICLE_DATE = env_str("MIN_ARTICLE_DATE", "2025-06-01")
MAX_ARTICLE_AGE_DAYS = env_int("MAX_ARTICLE_AGE_DAYS", 15)
TOP_READS_MAX_AGE_DAYS = env_int("TOP_READS_MAX_AGE_DAYS", 7)

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
