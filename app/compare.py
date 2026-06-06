from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from app.chat import build_context, query_embedding, retrieve_chunks
from app.config import CHAT_MODEL, INVESTORS, OPENAI_API_KEY


def response_language(topic: str) -> str:
    return "Chinese" if re.search(r"[\u3400-\u9fff]", topic) else "English"


def parse_json_response(value: str) -> dict[str, Any]:
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("Comparison response must be a JSON object.")
    return result


def normalize_fund_result(
    value: dict[str, Any] | None,
    key: str,
    name: str,
    has_evidence: bool,
) -> dict[str, Any]:
    value = value or {}
    status = "sufficient" if has_evidence else "insufficient"
    return {
        "key": key,
        "name": name,
        "core_thesis": value.get("core_thesis")
        or (
            "当前文章库中没有找到足够相关的来源。"
            if not has_evidence
            else "现有来源不足以形成明确结论。"
        ),
        "key_arguments": value.get("key_arguments") or [],
        "evidence_status": status,
    }


def compare_investors(topic: str, investor_keys: list[str]) -> dict[str, Any]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required for investor comparison.")

    language = response_language(topic)
    embedding = query_embedding(topic)
    chunks_by_investor: dict[str, list[dict]] = {}
    retrieval_modes: dict[str, str] = {}
    all_chunks: list[dict] = []

    for key in investor_keys:
        source = INVESTORS[key]
        chunks, mode = retrieve_chunks(
            topic,
            top_k=4,
            source=source,
            embedding=embedding,
        )
        chunks_by_investor[key] = chunks
        retrieval_modes[key] = mode
        all_chunks.extend(chunks)

    context, citations = build_context(all_chunks)
    selected_funds = [
        {
            "key": key,
            "name": INVESTORS[key],
            "evidence_available": bool(chunks_by_investor[key]),
        }
        for key in investor_keys
    ]

    if not all_chunks:
        return {
            "topic": topic,
            "funds": [
                normalize_fund_result(None, fund["key"], fund["name"], False)
                for fund in selected_funds
            ],
            "agreements": [],
            "disagreements": [],
            "investment_implications": [],
            "citations": [],
            "retrieval_modes": retrieval_modes,
        }

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.responses.create(
        model=CHAT_MODEL,
        input=[
            {
                "role": "system",
                "content": (
                    "You are an investment research analyst comparing venture firms. "
                    "Use only the supplied excerpts. Return valid JSON only, with no "
                    f"Markdown fences. Write every analytical field in {language}. "
                    "This language requirement is mandatory even when all source "
                    "excerpts are in another language. Keep fund names unchanged. Cite "
                    "claims inline using the supplied source numbers such as [1]. "
                    "Never invent a firm's position or a citation. If evidence is "
                    "missing, say so explicitly."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Topic: {topic}\n\n"
                    f"Required response language: {language}\n\n"
                    f"Selected funds: {json.dumps(selected_funds)}\n\n"
                    f"Sources:\n{context}\n\n"
                    "Return exactly this JSON shape:\n"
                    "{\n"
                    '  "funds": [{"key": "fund key", "name": "fund name", '
                    '"core_thesis": "concise thesis with citations", '
                    '"key_arguments": ["argument with citation"], '
                    '"evidence_status": "sufficient or insufficient"}],\n'
                    '  "agreements": ["shared view with citations"],\n'
                    '  "disagreements": ["difference with citations"],\n'
                    '  "investment_implications": ["practical implication"]\n'
                    "}"
                ),
            },
        ],
    )
    generated = parse_json_response(response.output_text)
    generated_by_key = {
        item.get("key"): item
        for item in generated.get("funds", [])
        if isinstance(item, dict) and item.get("key") in investor_keys
    }
    funds = [
        normalize_fund_result(
            generated_by_key.get(key),
            key,
            INVESTORS[key],
            bool(chunks_by_investor[key]),
        )
        for key in investor_keys
    ]

    return {
        "topic": topic,
        "funds": funds,
        "agreements": generated.get("agreements") or [],
        "disagreements": generated.get("disagreements") or [],
        "investment_implications": generated.get("investment_implications") or [],
        "citations": citations,
        "retrieval_modes": retrieval_modes,
    }
