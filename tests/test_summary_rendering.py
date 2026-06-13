from app.main import render_summary, summary_title


def test_render_summary_hides_source_metadata_and_styles_titles():
    value = """## Source Metadata / 来源信息
- source_title: Hidden title
- source_url: https://example.com

## 中文导读标题
AI 的成本战争，刚刚开始

## Original Title
The New Economics of AI

## Core Thesis / 核心论点
真正重要的是 **推理成本下降了 80%**。
"""

    rendered = render_summary(value)

    assert "source_title" not in rendered
    assert "example.com" not in rendered
    assert "<strong>推理成本下降了 80%</strong>" in rendered
    assert "AI 的成本战争，刚刚开始" not in rendered
    assert "The New Economics of AI" not in rendered
    assert summary_title(value) == "AI 的成本战争，刚刚开始"


def test_render_summary_hides_unsupported_section_and_translates_old_heading():
    value = """## Round / Investors / Amount / 轮次、投资方与金额
Not enough evidence in source

## Main Argument / 主要观点
真正的变化是 **市场开始奖励效率**。
"""

    rendered = render_summary(value)

    assert "轮次、投资方与金额" not in rendered
    assert "Not enough evidence" not in rendered
    assert "🎯 主要观点" in rendered
