from __future__ import annotations

import re
from dataclasses import dataclass


THESIS_ARTICLE = "THESIS_ARTICLE"
MARKET_MAP = "MARKET_MAP"
TECH_EXPLAINER = "TECH_EXPLAINER"
COMPANY_ANALYSIS = "COMPANY_ANALYSIS"
FUNDING_NEWS = "FUNDING_NEWS"
PRODUCT_LAUNCH = "PRODUCT_LAUNCH"
OPINION = "OPINION"
PODCAST_TRANSCRIPT = "PODCAST_TRANSCRIPT"

CONTENT_TYPES = {
    THESIS_ARTICLE,
    MARKET_MAP,
    TECH_EXPLAINER,
    COMPANY_ANALYSIS,
    FUNDING_NEWS,
    PRODUCT_LAUNCH,
    OPINION,
    PODCAST_TRANSCRIPT,
}

TYPE_TERMS = {
    PODCAST_TRANSCRIPT: {
        "podcast transcript",
        "transcript",
        "interviewer",
        "interviewee",
        "host:",
        "guest:",
        "conversation with",
    },
    FUNDING_NEWS: {
        "funding round",
        "series a",
        "series b",
        "series c",
        "seed round",
        "raised",
        "acquisition",
        "acquired",
        "ipo",
        "initial public offering",
        "investment in",
        "we invested in",
    },
    PRODUCT_LAUNCH: {
        "product launch",
        "launching",
        "introducing",
        "now available",
        "new feature",
        "release notes",
        "model release",
        "api release",
        "platform launch",
        "general availability",
    },
    MARKET_MAP: {
        "market map",
        "market landscape",
        "competitive landscape",
        "ecosystem map",
        "category breakdown",
        "sector overview",
        "value chain",
        "market segmentation",
        "taxonomy",
    },
    TECH_EXPLAINER: {
        "architecture",
        "protocol",
        "technical explanation",
        "how it works",
        "inference",
        "training pipeline",
        "developer tool",
        "database",
        "api",
        "infrastructure layer",
        "system design",
    },
    COMPANY_ANALYSIS: {
        "company analysis",
        "company deep dive",
        "business model",
        "competitive position",
        "unit economics",
        "gross margin",
        "go-to-market",
        "revenue model",
        "product strategy",
        "case study",
    },
    THESIS_ARTICLE: {
        "investment thesis",
        "our thesis",
        "we believe",
        "market thesis",
        "strategic view",
        "investment case",
        "market structure",
        "trend",
        "implication",
        "why now",
        "positioning",
        "position",
        "competitive advantage",
        "strategic argument",
        "point of view",
    },
    OPINION: {
        "opinion",
        "prediction",
        "reflection",
        "lessons learned",
        "personal essay",
        "what i learned",
        "my view",
        "thoughts on",
    },
}

TYPE_PRIORITY = [
    PODCAST_TRANSCRIPT,
    FUNDING_NEWS,
    PRODUCT_LAUNCH,
    MARKET_MAP,
    TECH_EXPLAINER,
    COMPANY_ANALYSIS,
    THESIS_ARTICLE,
    OPINION,
]


@dataclass(frozen=True)
class ContentTypeClassification:
    content_type: str
    reasoning: str


def term_matches(text: str, term: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text))


def classify_content_type(title: str, content: str) -> ContentTypeClassification:
    normalized_title = " ".join((title or "").lower().split())
    normalized_content = " ".join((content or "").lower().split())
    sample = f"{normalized_title} {normalized_content[:20000]}"
    scores: dict[str, int] = {}
    matches: dict[str, list[str]] = {}

    for content_type, terms in TYPE_TERMS.items():
        matched = sorted(term for term in terms if term_matches(sample, term))
        title_matches = sum(1 for term in terms if term_matches(normalized_title, term))
        matches[content_type] = matched
        scores[content_type] = len(matched) + (title_matches * 2)

    funding_title_signals = {
        "funding round", "series a", "series b", "series c", "seed round",
        "raises", "raised", "acquisition", "acquired", "ipo", "going public",
    }
    funding_event = any(term_matches(normalized_title, term) for term in funding_title_signals)
    if not funding_event:
        scores[FUNDING_NEWS] = 0

    launch_title_signals = {
        "launching", "introducing", "now available", "new feature", "release",
        "general availability",
    }
    launch_object_signals = {
        "product", "feature", "model", "api", "platform", "tool", "service",
    }
    product_launch = any(
        term_matches(normalized_title, term) for term in launch_title_signals
    ) and any(term_matches(sample, term) for term in launch_object_signals)
    if not product_launch:
        scores[PRODUCT_LAUNCH] = 0

    selected = max(TYPE_PRIORITY, key=lambda item: (scores[item], -TYPE_PRIORITY.index(item)))
    if scores[selected] == 0:
        selected = OPINION
        reasoning = "No strong structured content-type signals; using conservative opinion fallback."
    else:
        reasoning = (
            f"Matched {', '.join(matches[selected][:4])}; "
            f"{selected.lower().replace('_', ' ')} had the strongest signal score "
            f"({scores[selected]})."
        )

    return ContentTypeClassification(content_type=selected, reasoning=reasoning)
