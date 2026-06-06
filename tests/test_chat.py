from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.chat import build_context, chat_response_format, chat_response_language
from app.main import app


CHAT_RESULT = {
    "answer": "AI defensibility depends on workflow ownership [1].",
    "citations": [
        {
            "citation_number": 1,
            "article_id": 12,
            "title": "AI Application Defensibility",
            "source": "Sequoia",
            "url": "https://example.com/article",
            "published_at": "2026-06-01T00:00:00+00:00",
        }
    ],
    "retrieval_mode": "vector",
}


def test_chat_page_renders() -> None:
    response = TestClient(app).get("/chat")

    assert response.status_code == 200
    assert "向 Thesisflow 提问" in response.text
    assert "/api/chat" in response.text


def test_chat_api_returns_answer_and_citations() -> None:
    with patch("app.main.answer_question", return_value=CHAT_RESULT):
        response = TestClient(app).post(
            "/api/chat",
            json={"question": "What creates AI defensibility?", "top_k": 6},
        )

    assert response.status_code == 200
    assert response.json() == CHAT_RESULT


def test_chat_api_rejects_blank_question() -> None:
    response = TestClient(app).post(
        "/api/chat",
        json={"question": "   ", "top_k": 6},
    )

    assert response.status_code == 400


def test_build_context_deduplicates_article_citations() -> None:
    chunks = [
        {
            "article_id": 1,
            "title": "An AI Thesis",
            "source": "Bessemer",
            "url": "https://example.com/ai",
            "published_at": "2026-06-01",
            "fetched_at": "2026-06-02",
            "chunk_content": "First excerpt.",
        },
        {
            "article_id": 1,
            "title": "An AI Thesis",
            "source": "Bessemer",
            "url": "https://example.com/ai",
            "published_at": "2026-06-01",
            "fetched_at": "2026-06-02",
            "chunk_content": "Second excerpt.",
        },
    ]

    context, citations = build_context(chunks)

    assert len(citations) == 1
    assert context.count("SOURCE [1]") == 2


def test_chat_response_language_follows_question() -> None:
    assert chat_response_language("AI应用如何建立护城河？") == "Chinese"
    assert chat_response_language("How do AI applications build moats?") == "English"


def test_chat_response_format_is_structured() -> None:
    chinese = chat_response_format("Chinese")
    english = chat_response_format("English")

    assert "🎯 核心结论" in chinese
    assert "💡 关键洞察" in chinese
    assert "📈 Why It Matters" in english
    assert "**bold key phrase**" in english
