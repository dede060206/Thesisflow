from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re

from openai import OpenAI

from app.config import CATEGORIES, OPENAI_API_KEY, OPENAI_MODEL, QUALITY_SCORE_THRESHOLD
from app.database import (
    get_weekly_insight,
    list_articles_for_resummary,
    list_articles_for_weekly_insight,
    list_unsummarized_articles,
    missing_weekly_insight_categories,
    save_summary,
    save_weekly_insight,
)


SUMMARY_SECTIONS = {
    "THESIS_ARTICLE": [
        "🎯 核心论点",
        "⏳ 为什么是现在",
        "🧾 支持证据",
        "💡 非共识洞察",
        "⚖️ 风险与反方观点",
        "🔭 投资相关性",
    ],
    "MARKET_MAP": [
        "🗺️ 市场结构",
        "🧩 关键类别",
        "🏢 代表性公司",
        "⛓️ 价值链位置",
        "🌱 市场空白",
        "🔭 投资相关性",
    ],
    "TECH_EXPLAINER": [
        "🧠 技术是什么",
        "⏳ 为什么现在重要",
        "🛠️ 技术瓶颈",
        "💼 商业影响",
        "🏢 相关公司或行业",
        "🔭 投资相关性",
    ],
    "COMPANY_ANALYSIS": [
        "🏢 公司概览",
        "🧩 产品与商业模式",
        "🏰 竞争位置",
        "📈 增长驱动因素",
        "⚠️ 风险",
        "🔭 投资相关性",
    ],
    "FUNDING_NEWS": [
        "🏢 公司",
        "💰 轮次、投资方与金额",
        "🧩 公司业务",
        "🎯 本轮融资意义",
        "📡 市场信号",
        "🔭 投资相关性",
    ],
    "PRODUCT_LAUNCH": [
        "🚀 发布的产品或功能",
        "👥 目标用户",
        "🧩 解决的问题",
        "♟️ 战略影响",
        "🏁 竞争影响",
        "🔭 投资相关性",
    ],
    "OPINION": [
        "🎯 主要观点",
        "🖋️ 作者视角",
        "💡 有用洞察",
        "⚖️ 局限性",
        "🔭 投资相关性",
    ],
    "PODCAST_TRANSCRIPT": [
        "🎙️ 嘉宾或发言人",
        "🗂️ 主要话题",
        "💡 最强洞察",
        "🏢 提及的公司与市场",
        "🧭 反共识或有用观点",
        "🔭 投资相关性",
    ],
}
DEFAULT_CONTENT_TYPE = "OPINION"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def summary_template_name(content_type: str | None) -> str:
    selected = content_type if content_type in SUMMARY_SECTIONS else DEFAULT_CONTENT_TYPE
    return f"adaptive_v3:{selected}"


def build_summary_prompt(article: dict) -> tuple[str, str]:
    content_type = article.get("content_type")
    if content_type not in SUMMARY_SECTIONS:
        content_type = DEFAULT_CONTENT_TYPE
    template_name = summary_template_name(content_type)
    tags = article.get("tags") or article.get("category") or "Not enough evidence in source"
    publish_date = article.get("published_at") or "Not enough evidence in source"
    sections = "\n\n".join(
        f"## {heading}\n用简洁、具体、基于原文的内容回答。"
        for heading in SUMMARY_SECTIONS[content_type]
    )
    prompt = (
        "Source Metadata / 来源信息：\n"
        f"- source_title: {article.get('title') or 'Not enough evidence in source'}\n"
        f"- source_url: {article.get('url') or 'Not enough evidence in source'}\n"
        f"- publish_date: {publish_date}\n"
        f"- content_type: {content_type}\n"
        f"- quality_score: {article.get('quality_score', 'Not enough evidence in source')}\n"
        f"- tags: {tags}\n\n"
        f"正文：{(article.get('content') or article.get('title') or '')[:12000]}\n\n"
        "请像一位见识广、表达自然的投资研究编辑来写，而不是像机器生成报告。"
        "语气清醒、有判断、有节奏，允许使用恰当的比喻和转折，但不要夸张营销。"
        "请严格使用下面的 Markdown 结构，不要添加多余寒暄或泛泛而谈的填充内容。"
        "所有判断必须有原文依据。只有当正文有直接证据支持时才输出对应章节；"
        "如果正文不支持某个章节，完全省略该章节及标题，不要写占位语。不要猜测或补充外部事实。"
        "每个章节最多使用 1-2 处 Markdown **加粗**。只加粗会改变投资判断的完整结论、"
        "关键数字或因果关系，不要只加粗孤立公司名、普通名词或泛泛关键词，也不要整段加粗。"
        "不要在输出中展示 Source Metadata 或来源信息字段。\n\n"
        "## 中文导读标题\n"
        "写一个有趣、克制、能抓住读者注意力的中文标题；不要标题党，不超过24个汉字。\n\n"
        "## Original Title\n"
        f"{article.get('title') or 'Not enough evidence in source'}\n\n"
        f"{sections}\n\n"
        "## 原文引用\n"
        "- 摘出 2-3 条正文中可核验的短引文；若没有，写“Not enough evidence in source”。"
    )
    return template_name, prompt


def normalize_summary_output(summary: str, article: dict) -> str:
    lines = summary.strip().splitlines()
    cleaned: list[str] = []
    hiding_metadata = False
    for line in lines:
        if line.strip().startswith("## "):
            heading = line.strip()[3:].strip().lower()
            hiding_metadata = heading in {
                "source metadata",
                "source metadata / 来源信息",
                "来源信息",
            }
            if hiding_metadata:
                continue
        if not hiding_metadata:
            cleaned.append(line)

    normalized = "\n".join(cleaned).strip()
    normalized = re.sub(
        r"(?ms)^##\s+[^\n]+\n(?:\s*[-*]?\s*)?(?:"
        r"Not enough evidence in source[。.．]?|"
        r"(?:原文|正文)(?:中)?(?:未|没有)(?:提供|包含|提及|说明|披露).+?"
        r")\s*(?=^##\s+|\Z)",
        "",
        normalized,
    ).strip()
    if not re.search(r"^##\s+中文导读标题\s*$", normalized, re.MULTILINE):
        first_heading = re.match(r"^##\s+([^\n]+)", normalized)
        if first_heading and first_heading.group(1).lower() != "original title":
            title = first_heading.group(1).strip()
            normalized = (
                f"## 中文导读标题\n{title}" + normalized[first_heading.end() :]
            )
        else:
            normalized = f"## 中文导读标题\n读懂这篇文章的关键判断\n\n{normalized}"

    if not re.search(r"^##\s+Original Title\s*$", normalized, re.MULTILINE):
        marker = re.search(r"\n##\s+", normalized)
        original = article.get("title") or "Not enough evidence in source"
        insertion = f"\n\n## Original Title\n{original}"
        if marker:
            normalized = normalized[: marker.start()] + insertion + normalized[marker.start() :]
        else:
            normalized += insertion
    return normalized.strip()


def summarize_text(article: dict) -> tuple[str, str]:
    template_name, prompt = build_summary_prompt(article)
    if not OPENAI_API_KEY:
        return "未配置 OPENAI_API_KEY，暂未生成 GPT 摘要。", template_name

    client = OpenAI(api_key=OPENAI_API_KEY)

    response = client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {
                "role": "system",
                "content": (
                    "You are a rigorous VC industry research assistant. Write in concise "
                    "natural Chinese with an intelligent, human editorial voice. Keep claims "
                    "grounded in the article, avoid generic filler, selectively bold key facts, "
                    "and use clean Markdown."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    )
    return normalize_summary_output(response.output_text, article), template_name


def summarize_pending(limit: int = 100, force: bool = False) -> dict[str, int]:
    if force:
        articles = list_articles_for_resummary(limit=limit)
    else:
        articles = list_unsummarized_articles(limit=limit)
    summarized = 0
    skipped = 0

    for article in articles:
        quality_score = int(article.get("quality_score") or 0)
        if (
            article.get("page_type", "ARTICLE") != "ARTICLE"
            or article.get("skip_reason")
            or quality_score < QUALITY_SCORE_THRESHOLD
        ):
            skipped += 1
            print(
                f"[SUMMARY SKIP] {article.get('page_type')} | {article.get('url')} | "
                f"{article.get('skip_reason') or 'not an ARTICLE or below quality threshold'}"
            )
            continue
        print(f"[SUMMARY ACCEPT] ARTICLE | {article['url']}")
        summary, template_name = summarize_text(article)
        save_summary(
            article["id"], summary, OPENAI_MODEL, utc_now(), template_name
        )
        summarized += 1

    return {"found": len(articles), "summarized": summarized, "skipped": skipped}


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
