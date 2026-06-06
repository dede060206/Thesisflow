from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any

from openai import OpenAI

from app.config import (
    CHAT_MODEL,
    CHAT_TOP_K,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    OPENAI_API_KEY,
)
from app.database import search_article_chunks_text, search_article_chunks_vector


def chat_response_language(question: str) -> str:
    return "Chinese" if re.search(r"[\u3400-\u9fff]", question) else "English"


def chat_response_format(language: str) -> str:
    if language == "Chinese":
        return (
            "严格使用以下 Markdown 结构：\n"
            "## 🎯 核心结论\n"
            "用 2-3 句话直接回答问题，并标注引用。\n\n"
            "## 💡 关键洞察\n"
            "- 提炼 3-5 条洞察。每条以 **加粗重点短语** 开头，并标注引用。\n\n"
            "## 📈 为什么重要\n"
            "说明这些观点对投资人、创业者或市场判断的意义，并标注引用。\n\n"
            "## ⚠️ 值得关注\n"
            "列出证据限制、分歧或仍需验证的问题。"
        )
    return (
        "Use exactly this Markdown structure:\n"
        "## 🎯 Bottom Line\n"
        "Answer directly in 2-3 sentences with citations.\n\n"
        "## 💡 Key Insights\n"
        "- Provide 3-5 insights. Start each with a **bold key phrase** and cite it.\n\n"
        "## 📈 Why It Matters\n"
        "Explain the implications for investors, founders, or market analysis with citations.\n\n"
        "## ⚠️ What To Watch\n"
        "List evidence limitations, disagreements, or open questions."
    )


def query_embedding(question: str) -> list[float]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required for AI chat.")
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=question,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    return response.data[0].embedding


def retrieve_chunks(
    question: str,
    top_k: int = CHAT_TOP_K,
    source: str | None = None,
    embedding: list[float] | None = None,
) -> tuple[list[dict], str]:
    candidates: list[dict] = []
    retrieval_mode = "full_text"
    try:
        candidates = search_article_chunks_vector(
            embedding or query_embedding(question),
            limit=max(top_k * 3, top_k),
            source=source,
        )
        if candidates:
            retrieval_mode = "vector"
    except Exception as exc:
        print(f"Vector retrieval unavailable, using full-text search: {exc}")

    if not candidates:
        candidates = search_article_chunks_text(
            question,
            limit=max(top_k * 3, top_k),
            source=source,
        )

    selected: list[dict] = []
    per_article: dict[int, int] = {}
    for chunk in candidates:
        article_id = chunk["article_id"]
        if per_article.get(article_id, 0) >= 2:
            continue
        selected.append(chunk)
        per_article[article_id] = per_article.get(article_id, 0) + 1
        if len(selected) >= top_k:
            break
    return selected, retrieval_mode


def serialize_date(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def build_context(chunks: list[dict]) -> tuple[str, list[dict[str, Any]]]:
    citations: list[dict[str, Any]] = []
    citation_numbers: dict[int, int] = {}
    context_blocks: list[str] = []

    for chunk in chunks:
        article_id = chunk["article_id"]
        if article_id not in citation_numbers:
            number = len(citations) + 1
            citation_numbers[article_id] = number
            citations.append(
                {
                    "citation_number": number,
                    "article_id": article_id,
                    "title": chunk["title"],
                    "source": chunk["source"],
                    "url": chunk["url"],
                    "published_at": serialize_date(
                        chunk.get("published_at") or chunk.get("fetched_at")
                    ),
                }
            )
        number = citation_numbers[article_id]
        context_blocks.append(
            "\n".join(
                [
                    f"SOURCE [{number}]",
                    f"Title: {chunk['title']}",
                    f"Publisher: {chunk['source']}",
                    f"Date: {serialize_date(chunk.get('published_at') or chunk.get('fetched_at'))}",
                    f"Excerpt: {chunk['chunk_content']}",
                ]
            )
        )
    return "\n\n".join(context_blocks), citations


def answer_question(question: str, top_k: int = CHAT_TOP_K) -> dict[str, Any]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required for AI chat.")

    language = chat_response_language(question)
    chunks, retrieval_mode = retrieve_chunks(question, top_k=top_k)
    if not chunks:
        return {
            "answer": "当前文章库中没有找到足够相关的内容来回答这个问题。",
            "citations": [],
            "retrieval_mode": retrieval_mode,
        }

    context, citations = build_context(chunks)
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.responses.create(
        model=CHAT_MODEL,
        input=[
            {
                "role": "system",
                "content": (
                    "You are an investment research assistant. "
                    f"Write every analytical section in {language}. This is mandatory "
                    "even when the source excerpts use another language. Use only the supplied source "
                    "excerpts. Cite factual claims inline with source numbers such as "
                    "[1] or [2]. Do not invent facts or citations. If the sources are "
                    "insufficient, state that clearly. Keep the answer concise, "
                    "structured, and analytical. Use the requested emoji only in "
                    "section headings; do not decorate every sentence."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question:\n{question}\n\n"
                    f"Required response language: {language}\n\n"
                    f"Required output format:\n{chat_response_format(language)}\n\n"
                    f"Sources:\n{context}"
                ),
            },
        ],
    )
    return {
        "answer": response.output_text.strip(),
        "citations": citations,
        "retrieval_mode": retrieval_mode,
    }
