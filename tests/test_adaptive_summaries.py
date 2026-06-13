import pytest

from app.summarizer import (
    SUMMARY_SECTIONS,
    build_summary_prompt,
    normalize_summary_output,
    summary_template_name,
)


BASE_ARTICLE = {
    "title": "The Future of AI Infrastructure",
    "url": "https://example.com/blog/ai-infrastructure",
    "published_at": "2026-06-12T10:00:00+00:00",
    "quality_score": 9,
    "category": "Developer Tools",
    "content": "Detailed source content about markets, companies, and technology.",
}


@pytest.mark.parametrize("content_type", SUMMARY_SECTIONS)
def test_each_content_type_selects_its_own_template(content_type):
    article = {**BASE_ARTICLE, "content_type": content_type}

    template_name, prompt = build_summary_prompt(article)

    assert template_name == f"adaptive_v3:{content_type}"
    assert f"- content_type: {content_type}" in prompt
    for section in SUMMARY_SECTIONS[content_type]:
        assert f"## {section}" in prompt


def test_templates_are_distinct():
    prompts = {
        content_type: build_summary_prompt(
            {**BASE_ARTICLE, "content_type": content_type}
        )[1]
        for content_type in SUMMARY_SECTIONS
    }

    assert len(set(prompts.values())) == len(SUMMARY_SECTIONS)


def test_prompt_contains_metadata_and_grounding_instruction():
    template_name, prompt = build_summary_prompt(
        {**BASE_ARTICLE, "content_type": "THESIS_ARTICLE"}
    )

    assert template_name == "adaptive_v3:THESIS_ARTICLE"
    assert "source_title: The Future of AI Infrastructure" in prompt
    assert "source_url: https://example.com/blog/ai-infrastructure" in prompt
    assert "publish_date: 2026-06-12T10:00:00+00:00" in prompt
    assert "quality_score: 9" in prompt
    assert "tags: Developer Tools" in prompt
    assert "Not enough evidence in source" in prompt
    assert "不要猜测" in prompt
    assert "## 中文导读标题" in prompt
    assert "## Original Title" in prompt
    assert "不要在输出中展示 Source Metadata" in prompt
    assert "**加粗**" in prompt
    assert "完全省略该章节及标题" in prompt
    assert "## 原文引用" in prompt


def test_unknown_content_type_uses_opinion_fallback():
    template_name, prompt = build_summary_prompt(
        {**BASE_ARTICLE, "content_type": None}
    )

    assert template_name == summary_template_name("OPINION")
    assert "## 🎯 主要观点" in prompt


def test_normalize_summary_repairs_missing_title_label_and_removes_metadata():
    raw = """## Source Metadata / 来源信息
- source_url: https://example.com

## AI 成本战争刚刚开始

## Core Thesis / 核心论点
成本正在下降。
"""

    normalized = normalize_summary_output(raw, BASE_ARTICLE)

    assert "Source Metadata" not in normalized
    assert "source_url" not in normalized
    assert normalized.startswith("## 中文导读标题\nAI 成本战争刚刚开始")
    assert "## Original Title\nThe Future of AI Infrastructure" in normalized


def test_normalize_summary_removes_unsupported_section():
    raw = """## 中文导读标题
融资之后，真正的问题才开始

## Original Title
Funding Update

## 💰 轮次、投资方与金额
Not enough evidence in source

## 📡 市场信号
市场正在回暖。
"""

    normalized = normalize_summary_output(raw, BASE_ARTICLE)

    assert "轮次、投资方与金额" not in normalized
    assert "Not enough evidence" not in normalized
    assert "## 📡 市场信号" in normalized


def test_normalize_summary_removes_chinese_missing_evidence_section():
    raw = """## 中文导读标题
上市不是终点

## Original Title
Going Public

## 💰 轮次、投资方与金额
原文未包含具体融资轮次、投资方或金额信息。

## 📡 市场信号
公司完成上市。
"""

    normalized = normalize_summary_output(raw, BASE_ARTICLE)

    assert "轮次、投资方与金额" not in normalized
    assert "原文未包含" not in normalized
    assert "## 📡 市场信号" in normalized


def test_normalize_summary_removes_english_placeholder_with_chinese_period():
    raw = """## 中文导读标题
定位比标签更重要

## Original Title
AI-Powered Isn't a Position

## ⚖️ 风险与反方观点
- Not enough evidence in source。

## 🔭 投资相关性
品牌定位决定长期价值。
"""

    normalized = normalize_summary_output(raw, BASE_ARTICLE)

    assert "风险与反方观点" not in normalized
    assert "Not enough evidence" not in normalized
    assert "## 🔭 投资相关性" in normalized
