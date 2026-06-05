from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from openai import OpenAI

from app.config import CATEGORIES, OPENAI_API_KEY, OPENAI_MODEL
from app.database import (
    get_weekly_insight,
    list_articles_for_resummary,
    list_articles_for_weekly_insight,
    list_unsummarized_articles,
    missing_weekly_insight_categories,
    save_summary,
    save_weekly_insight,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def summarize_text(title: str, content: str) -> str:
    if not OPENAI_API_KEY:
        return "未配置 OPENAI_API_KEY，暂未生成 GPT 摘要。"

    client = OpenAI(api_key=OPENAI_API_KEY)
    source_text = content[:12000] if content else title

    response = client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {
                "role": "system",
                "content": (
                    "You are a rigorous VC industry research assistant. Write in concise "
                    "Chinese, keep claims grounded in the article, and use clean Markdown."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"标题：{title}\n\n"
                    f"正文：{source_text}\n\n"
                    "请严格按下面格式输出，不要添加多余寒暄：\n\n"
                    "## Core Thesis / 核心论点\n"
                    "用 2-3 句话概括文章的核心论点。\n\n"
                    "## Key Insights / 关键洞察\n"
                    "- 提炼 3-5 个关键洞察，每条说明为什么重要。\n\n"
                    "## Actionable Takeaways / 行动启发\n"
                    "- 分别给创业者、投资人或运营者可执行的启发。\n\n"
                    "## 原文引用\n"
                    "- 从正文中摘出 2-3 条短引文。必须是正文里出现过的原话；"
                    "如果正文没有可引用内容，写“原文未提供足够可核验的直接引文”。"
                ),
            },
        ],
    )
    return response.output_text.strip()


def summarize_pending(limit: int = 100, force: bool = False) -> dict[str, int]:
    if force:
        articles = list_articles_for_resummary(limit=limit)
    else:
        articles = list_unsummarized_articles(limit=limit)
    summarized = 0

    for article in articles:
        summary = summarize_text(article["title"], article["content"] or "")
        save_summary(article["id"], summary, OPENAI_MODEL, utc_now())
        summarized += 1

    return {"found": len(articles), "summarized": summarized}


def current_week_range() -> tuple[str, str]:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start.isoformat(), week_end.isoformat()


def generate_weekly_insight(category: str, articles: list) -> str:
    if not articles:
        return "本周该分类暂无足够文章生成趋势洞察。"
    if not OPENAI_API_KEY:
        return "未配置 OPENAI_API_KEY，暂未生成周度趋势洞察。"

    client = OpenAI(api_key=OPENAI_API_KEY)
    article_context = "\n\n".join(
        (
            f"标题：{article['title']}\n"
            f"来源：{article['source']}\n"
            f"摘要：{article['summary'] or (article['content'] or '')[:1000]}"
        )
        for article in articles
    )

    response = client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {
                "role": "system",
                "content": (
                    "You are a VC market analyst. Identify weekly category trends "
                    "from the provided article set. Write concise Chinese Markdown."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"分类：{category}\n\n"
                    f"文章集合：\n{article_context[:14000]}\n\n"
                    "请严格输出：\n\n"
                    "## Weekly Trend\n"
                    "总结本周最重要的行业趋势。\n\n"
                    "## Evidence\n"
                    "- 用文章中的信号支持判断。\n\n"
                    "## What To Watch\n"
                    "- 未来一周值得关注的变化。"
                ),
            },
        ],
    )
    return response.output_text.strip()


def generate_weekly_category_insights(force: bool = False) -> dict[str, int]:
    week_start, week_end = current_week_range()
    categories = CATEGORIES if force else missing_weekly_insight_categories(week_start)
    generated = 0

    for category in categories:
        if not force and get_weekly_insight(category, week_start):
            continue
        articles = list_articles_for_weekly_insight(category, week_start, week_end)
        insight = generate_weekly_insight(category, articles)
        save_weekly_insight(
            category=category,
            week_start=week_start,
            week_end=week_end,
            insight=insight,
            model=OPENAI_MODEL,
            generated_at=utc_now(),
        )
        generated += 1

    return {"found": len(categories), "generated": generated}
