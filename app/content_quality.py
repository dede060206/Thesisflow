from __future__ import annotations

import re
from dataclasses import dataclass


PROMOTIONAL_TERMS = {
    "apply now",
    "buy now",
    "contact us",
    "join us",
    "register now",
    "sign up",
    "subscribe",
    "we are excited to announce",
}

ANALYSIS_TERMS = {
    "analysis",
    "we believe",
    "our research",
    "our view",
    "thesis",
    "framework",
    "observed",
    "implication",
    "trade-off",
    "tradeoff",
}

SPECIFICITY_TERMS = {
    "business model",
    "dataset",
    "developer tool",
    "go-to-market",
    "gross margin",
    "infrastructure",
    "marketplace",
    "product",
    "revenue",
    "saas",
    "sector",
    "software",
    "technology",
    "valuation",
}

EVIDENCE_TERMS = {
    "according to",
    "benchmark",
    "case study",
    "data shows",
    "evidence",
    "example",
    "for instance",
    "research",
    "survey",
    "study",
    "source",
}

VENTURE_TERMS = {
    "ai",
    "artificial intelligence",
    "business strategy",
    "capital",
    "company",
    "enterprise",
    "founder",
    "fundraising",
    "infrastructure",
    "innovation",
    "investing",
    "investment",
    "market structure",
    "startup",
    "technology",
    "venture",
}

STRUCTURE_TERMS = {
    "however",
    "in contrast",
    "on the other hand",
    "therefore",
    "implication",
    "conclusion",
    "first",
    "second",
}

GENERIC_CAPITALIZED_WORDS = {
    "According",
    "Apply",
    "For",
    "However",
    "Join",
    "Our",
    "Sign",
    "Subscribe",
    "The",
    "This",
    "We",
}


@dataclass(frozen=True)
class QualityAssessment:
    score: int
    reasoning: str
    components: dict[str, int]


def term_count(text: str, terms: set[str]) -> int:
    return sum(
        1
        for term in terms
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text)
    )


def score_content_quality(
    title: str,
    content: str,
    *,
    trusted_source: bool = False,
) -> QualityAssessment:
    normalized = " ".join(f"{title} {content}".lower().split())
    words = normalized.split()
    word_count = len(words)
    promotional_count = term_count(normalized, PROMOTIONAL_TERMS)

    analysis_count = term_count(normalized, ANALYSIS_TERMS)
    if promotional_count >= 2 and analysis_count == 0:
        originality = 0
    elif analysis_count >= 2:
        originality = 2
    else:
        originality = 1

    specificity_count = term_count(normalized, SPECIFICITY_TERMS)
    named_entities = len(
        {
            match
            for match in re.findall(
                r"\b[A-Z][A-Za-z0-9.+-]{2,}(?:\s+[A-Z][A-Za-z0-9.+-]{2,})*\b",
                content,
            )
            if match not in GENERIC_CAPITALIZED_WORDS
        }
    )
    specificity_signals = specificity_count + min(named_entities, 4)
    specificity = 2 if specificity_signals >= 5 else 1 if specificity_signals >= 2 else 0

    evidence_terms = term_count(normalized, EVIDENCE_TERMS)
    numeric_evidence = len(
        re.findall(
            r"(?:\$|£|€)\s?\d|\b\d+(?:\.\d+)?%|\b\d+(?:\.\d+)?\s?(?:million|billion|trillion|x)\b",
            normalized,
        )
    )
    evidence_signals = evidence_terms + min(numeric_evidence, 4)
    evidence = 2 if evidence_signals >= 4 else 1 if evidence_signals >= 2 else 0

    venture_count = term_count(normalized, VENTURE_TERMS)
    venture_relevance = 2 if venture_count >= 4 else 1 if venture_count >= 2 else 0

    structure_count = term_count(normalized, STRUCTURE_TERMS)
    if word_count >= 2200 and (structure_count >= 1 or evidence_signals >= 4):
        depth = 2
    elif word_count >= 1000 or (trusted_source and word_count >= 500):
        depth = 1
    else:
        depth = 0
    if promotional_count >= 3:
        depth = max(0, depth - 1)

    components = {
        "originality": originality,
        "specificity": specificity,
        "evidence": evidence,
        "venture_relevance": venture_relevance,
        "depth": depth,
    }
    source_bonus = 1 if trusted_source else 0
    score = max(1, min(10, sum(components.values()) + source_bonus))
    reasoning = (
        "Component scores: "
        + ", ".join(f"{name}={value}/2" for name, value in components.items())
        + ". "
        f"Detected {word_count} words, {specificity_signals} specificity signals, "
        f"{evidence_signals} evidence signals, and {venture_count} venture-relevance signals. "
        f"Trusted-source editorial bonus={source_bonus}."
    )
    return QualityAssessment(score=score, reasoning=reasoning, components=components)
