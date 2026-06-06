from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import call, patch

from fastapi.testclient import TestClient

from app.compare import compare_investors, parse_json_response, response_language
from app.main import app


COMPARE_RESULT = {
    "topic": "AI defensibility",
    "funds": [
        {
            "key": "a16z",
            "name": "Andreessen Horowitz",
            "core_thesis": "Distribution matters [1].",
            "key_arguments": ["Workflow ownership compounds [1]."],
            "evidence_status": "sufficient",
        },
        {
            "key": "nfx",
            "name": "NFX",
            "core_thesis": "Network effects matter [2].",
            "key_arguments": ["Data can reinforce networks [2]."],
            "evidence_status": "sufficient",
        },
    ],
    "agreements": ["AI alone is not a moat [1][2]."],
    "disagreements": ["They emphasize different moat mechanisms [1][2]."],
    "investment_implications": ["Test distribution and data advantages."],
    "citations": [],
    "retrieval_modes": {"a16z": "vector", "nfx": "vector"},
}


def chunk(article_id: int, source: str, title: str) -> dict:
    return {
        "article_id": article_id,
        "title": title,
        "source": source,
        "url": f"https://example.com/{article_id}",
        "published_at": "2026-06-01",
        "fetched_at": "2026-06-02",
        "chunk_content": f"Evidence from {source}.",
    }


def test_compare_page_renders_investor_options() -> None:
    response = TestClient(app).get("/compare")

    assert response.status_code == 200
    assert "比较顶级投资机构的观点" in response.text
    assert "Andreessen Horowitz" in response.text
    assert "Bessemer" in response.text
    assert "核心论点" in response.text
    assert "关键论据" in response.text
    assert "引用来源" in response.text
    assert "证据充足" in response.text


def test_compare_api_returns_structured_result() -> None:
    with patch("app.main.compare_investors", return_value=COMPARE_RESULT):
        response = TestClient(app).post(
            "/api/compare",
            json={"topic": "AI defensibility", "investors": ["a16z", "nfx"]},
        )

    assert response.status_code == 200
    assert response.json() == COMPARE_RESULT


def test_compare_api_validates_investor_selection() -> None:
    client = TestClient(app)

    too_few = client.post(
        "/api/compare",
        json={"topic": "AI", "investors": ["a16z"]},
    )
    invalid = client.post(
        "/api/compare",
        json={"topic": "AI", "investors": ["a16z", "unknown"]},
    )

    assert too_few.status_code == 400
    assert invalid.status_code == 400
    assert "Unknown investors" in invalid.json()["detail"]


def test_compare_investors_filters_retrieval_by_source() -> None:
    generated = {
        "funds": [
            {
                "key": "a16z",
                "name": "Andreessen Horowitz",
                "core_thesis": "Distribution matters [1].",
                "key_arguments": ["Argument [1]."],
                "evidence_status": "sufficient",
            },
            {
                "key": "nfx",
                "name": "NFX",
                "core_thesis": "Networks matter [2].",
                "key_arguments": ["Argument [2]."],
                "evidence_status": "sufficient",
            },
        ],
        "agreements": ["Shared view [1][2]."],
        "disagreements": [],
        "investment_implications": ["Inspect the moat."],
    }
    response = SimpleNamespace(output_text=__import__("json").dumps(generated))
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: response)
    )

    with (
        patch("app.compare.OPENAI_API_KEY", "test-key"),
        patch("app.compare.query_embedding", return_value=[0.1, 0.2]),
        patch(
            "app.compare.retrieve_chunks",
            side_effect=[
                ([chunk(1, "Andreessen Horowitz", "A16z AI")], "vector"),
                ([chunk(2, "NFX", "NFX AI")], "vector"),
            ],
        ) as retrieve,
        patch("app.compare.OpenAI", return_value=client),
    ):
        result = compare_investors("AI defensibility", ["a16z", "nfx"])

    assert retrieve.call_args_list == [
        call(
            "AI defensibility",
            top_k=4,
            source="Andreessen Horowitz",
            embedding=[0.1, 0.2],
        ),
        call(
            "AI defensibility",
            top_k=4,
            source="NFX",
            embedding=[0.1, 0.2],
        ),
    ]
    assert [citation["source"] for citation in result["citations"]] == [
        "Andreessen Horowitz",
        "NFX",
    ]


def test_parse_json_response_accepts_markdown_fence() -> None:
    assert parse_json_response('```json\n{"funds": []}\n```') == {"funds": []}


def test_response_language_follows_topic_language() -> None:
    assert response_language("AI 应用层的长期护城河") == "Chinese"
    assert response_language("AI application defensibility") == "English"
