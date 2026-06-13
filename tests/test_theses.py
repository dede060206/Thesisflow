from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.theses import deterministic_sources, normalize_sections
from app.workspace import sign_workspace, verify_workspace


THESIS = {
    "id": 7,
    "workspace_id": "00000000-0000-0000-0000-000000000001",
    "title": "AI Agent Thesis",
    "core_claim": "AI agents will reshape vertical SaaS.",
    "status": "draft",
    "generated_sections": {},
    "investment_memo": None,
    "created_at": "2026-06-06T10:00:00+00:00",
    "updated_at": "2026-06-06T10:00:00+00:00",
}


def test_workspace_cookie_signature_rejects_tampering() -> None:
    workspace_id = "00000000-0000-0000-0000-000000000001"
    signed = sign_workspace(workspace_id)

    assert verify_workspace(signed) == workspace_id
    assert verify_workspace(signed + "x") is None


def test_create_thesis_sets_anonymous_workspace_cookie() -> None:
    client = TestClient(app)
    with (
        patch("app.thesis_routes.count_theses", return_value=0),
        patch("app.thesis_routes.create_thesis", return_value=THESIS) as create,
    ):
        response = client.post(
            "/api/theses",
            json={"title": "AI Agent Thesis", "core_claim": "A core claim"},
        )

    assert response.status_code == 201
    assert "thesisflow_workspace" in response.cookies
    workspace_id = create.call_args.args[0]
    assert verify_workspace(response.cookies["thesisflow_workspace"]) == workspace_id


def test_create_thesis_rejects_whitespace_only_input() -> None:
    response = TestClient(app).post(
        "/api/theses",
        json={"title": "   ", "core_claim": "   "},
    )

    assert response.status_code == 400


def test_import_evidence_rejects_unsafe_url() -> None:
    response = TestClient(app).post(
        "/api/theses/7/evidence/import",
        json={
            "evidence_type": "manual",
            "title": "Unsafe evidence",
            "excerpt": "Evidence text",
            "url": "javascript:alert(1)",
        },
    )

    assert response.status_code == 422


def test_thesis_pages_render() -> None:
    client = TestClient(app)
    with patch("app.thesis_routes.list_theses", return_value=[{**THESIS, "evidence_count": 2}]):
        listing = client.get("/theses")
    with (
        patch("app.thesis_routes.get_thesis", return_value=THESIS),
        patch("app.thesis_routes.list_thesis_evidence", return_value=[]),
    ):
        detail = client.get("/theses/7")

    assert listing.status_code == 200
    assert "AI Agent Thesis" in listing.text
    assert detail.status_code == 200
    assert "投资论点初稿" in detail.text
    assert "证据研究工作区" in detail.text
    assert "现有投资备忘录功能" in detail.text


def test_thesis_detail_denies_unknown_workspace_thesis() -> None:
    with patch("app.thesis_routes.get_thesis", return_value=None):
        response = TestClient(app).get("/theses/999")

    assert response.status_code == 404


def test_normalize_sections_removes_fake_evidence_ids() -> None:
    sections = normalize_sections(
        {
            "core_claim": "Claim",
            "supporting_evidence": [
                {"statement": "Supported", "evidence_ids": [11, 999]}
            ],
            "counterarguments": [],
            "key_questions": ["What changes?"],
            "investment_implications": [],
        },
        [{"id": 11}],
    )

    assert sections["supporting_evidence"]["evidence_ids"] == [11]


def test_deterministic_sources_uses_verified_evidence_metadata() -> None:
    sources = deterministic_sources(
        [
            {
                "id": 11,
                "title": "AI Markets",
                "source": "Sequoia",
                "url": "https://example.com/ai",
            }
        ]
    )

    assert "[E11] AI Markets — Sequoia — https://example.com/ai" in sources
