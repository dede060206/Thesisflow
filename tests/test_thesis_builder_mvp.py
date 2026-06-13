from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.theses import DRAFT_SECTION_KEYS, upgrade_legacy_sections
from app.thesis_research import EvidenceCandidate, research_thesis_evidence


THESIS = {
    "id": 17,
    "workspace_id": "00000000-0000-0000-0000-000000000001",
    "title": "Agent Infrastructure 投资论点",
    "core_claim": "Agent infrastructure will shift toward identity and auditability.",
    "domain": "Agent Infrastructure",
    "research_question": "Where will value accrue?",
    "initial_view": "Identity and permissions will matter.",
    "status": "developed",
    "generated_sections": {},
    "investment_memo": None,
    "created_at": "2026-06-13T00:00:00+00:00",
    "updated_at": "2026-06-13T00:00:00+00:00",
}


def complete_sections() -> dict:
    return {
        key: {"content": f"Content for {key}", "evidence_ids": [11]}
        for key in DRAFT_SECTION_KEYS
    }


def test_thesis_builder_route_reuses_saved_thesis_list() -> None:
    with patch(
        "app.thesis_routes.list_theses",
        return_value=[{**THESIS, "evidence_count": 4}],
    ):
        response = TestClient(app).get("/thesis-builder")

    assert response.status_code == 200
    assert "AI Thesis Draft" in response.text
    assert "Agent Infrastructure 投资论点" in response.text


def test_existing_legacy_sections_are_upgraded_without_data_loss() -> None:
    upgraded = upgrade_legacy_sections(
        {
            "core_claim": "Legacy claim",
            "supporting_evidence": [
                {"statement": "Legacy support", "evidence_ids": [11]}
            ],
            "counterarguments": [
                {"statement": "Legacy counter", "evidence_ids": [12]}
            ],
            "key_questions": ["What changes?"],
            "investment_implications": [],
        }
    )

    assert upgraded["core_claim"]["content"] == "Legacy claim"
    assert "Legacy support" in upgraded["supporting_evidence"]["content"]
    assert upgraded["supporting_evidence"]["evidence_ids"] == [11]
    assert "Legacy counter" in upgraded["counter_evidence"]["content"]


def test_evidence_research_classifies_and_preserves_source_attribution() -> None:
    class Provider:
        def search(self, query, workspace_id):
            return [
                EvidenceCandidate(
                    ref="article:11",
                    evidence_type="article",
                    title="Identity for Agents",
                    source="Sequoia",
                    url="https://example.com/identity",
                    published_at="2026-06-01",
                    excerpt="Agents require permissions and audit logs.",
                    metadata={"article_id": 11},
                    source_credibility="high",
                )
            ]

    generated = {
        "evidence": [
            {
                "ref": "article:11",
                "classification": "SUPPORTING",
                "relationship_explanation": "Directly supports the identity claim.",
                "strength": "high",
                "source_credibility": "high",
                "ai_recommendation": "prioritise",
            }
        ]
    }
    response = SimpleNamespace(output_text=json.dumps(generated))
    client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: response))

    with (
        patch("app.thesis_research.OPENAI_API_KEY", "test-key"),
        patch("app.thesis_research.OpenAI", return_value=client),
    ):
        result = research_thesis_evidence(
            "Find supporting evidence", "workspace", providers=(Provider(),)
        )

    assert result[0]["classification"] == "SUPPORTING"
    assert result[0]["strength"] == "high"
    assert result[0]["source"] == "Sequoia"
    assert result[0]["url"] == "https://example.com/identity"


def test_add_evidence_candidate_uses_resolved_server_source() -> None:
    candidate = EvidenceCandidate(
        ref="article:11",
        evidence_type="article",
        title="Verified title",
        source="Sequoia",
        url="https://example.com/verified",
        published_at="2026-06-01",
        excerpt="Verified excerpt",
        metadata={"article_id": 11},
    )
    saved = {
        "id": 31,
        "title": candidate.title,
        "source": candidate.source,
        "classification": "SUPPORTING",
    }
    with (
        patch("app.thesis_routes.get_thesis", return_value=THESIS),
        patch("app.thesis_routes.count_thesis_evidence", return_value=2),
        patch("app.thesis_routes.resolve_candidate", return_value=candidate),
        patch("app.thesis_routes.add_candidate_to_thesis", return_value=saved) as add,
    ):
        response = TestClient(app).post(
            "/api/theses/17/evidence/candidates",
            json={
                "ref": "article:11",
                "classification": "SUPPORTING",
                "relationship_explanation": "Supports the claim.",
                "strength": "high",
                "source_credibility": "high",
                "ai_recommendation": "prioritise",
                "evidence_state": "added",
            },
        )

    assert response.status_code == 200
    assert response.json()["evidence"]["source"] == "Sequoia"
    assert add.call_args.args[2] is candidate


def test_section_level_regeneration_updates_only_selected_section() -> None:
    thesis = {**THESIS, "generated_sections": complete_sections()}
    regenerated = {"content": "New why now", "evidence_ids": [11]}
    evidence = [{"id": 11, "evidence_state": "added"}]
    with (
        patch("app.thesis_routes.get_thesis", return_value=thesis),
        patch("app.thesis_routes.list_thesis_evidence", return_value=evidence),
        patch(
            "app.thesis_routes.regenerate_thesis_section", return_value=regenerated
        ),
        patch("app.thesis_routes.save_thesis_section_data", return_value=thesis) as save,
    ):
        response = TestClient(app).post(
            "/api/theses/17/sections/why_now/regenerate"
        )

    assert response.status_code == 200
    saved_sections = save.call_args.args[2]
    assert saved_sections["why_now"] == regenerated
    assert saved_sections["core_claim"]["content"] == "Content for core_claim"


def test_update_all_sections_removes_unverified_evidence_ids() -> None:
    payload = complete_sections()
    payload["core_claim"]["evidence_ids"] = [11, 999]
    with (
        patch("app.thesis_routes.get_thesis", return_value=THESIS),
        patch(
            "app.thesis_routes.list_thesis_evidence", return_value=[{"id": 11}]
        ),
        patch("app.thesis_routes.save_thesis_section_data", return_value=THESIS),
    ):
        response = TestClient(app).patch(
            "/api/theses/17/sections", json={"sections": payload}
        )

    assert response.status_code == 200
    assert response.json()["sections"]["core_claim"]["evidence_ids"] == [11]


def test_ai_generated_claim_without_real_source_is_replaced() -> None:
    from app.theses import normalize_sections

    sections = normalize_sections(
        {
            key: {"content": "Unsupported factual claim", "evidence_ids": []}
            for key in DRAFT_SECTION_KEYS
        },
        [],
        require_evidence=True,
    )

    assert sections["market_drivers"]["content"] == "现有证据不足，无法形成有来源支持的判断。"
    assert sections["open_questions"]["content"] == "Unsupported factual claim"


def test_create_ai_draft_preserves_domain_and_generates_sections() -> None:
    sections = complete_sections()
    created = {**THESIS, "status": "draft"}
    with (
        patch("app.thesis_routes.count_theses", return_value=0),
        patch("app.thesis_routes.create_thesis", return_value=created) as create,
        patch("app.thesis_routes.research_thesis_evidence", return_value=[]),
        patch("app.thesis_routes.list_thesis_evidence", return_value=[]),
        patch("app.thesis_routes.generate_thesis_sections", return_value=sections),
        patch("app.thesis_routes.save_thesis_section_data", return_value={**created, "generated_sections": sections}),
    ):
        response = TestClient(app).post(
            "/api/theses/draft",
            json={
                "domain": "Agent Infrastructure",
                "research_question": "Where will value accrue?",
                "initial_view": "Identity will matter.",
            },
        )

    assert response.status_code == 201
    assert response.json()["sections"]["why_now"]["content"] == "Content for why_now"
    assert create.call_args.kwargs["domain"] == "Agent Infrastructure"


def test_legacy_update_request_preserves_new_thesis_fields() -> None:
    with (
        patch("app.thesis_routes.get_thesis", return_value=THESIS),
        patch("app.thesis_routes.update_thesis", return_value=THESIS) as update,
    ):
        response = TestClient(app).patch(
            "/api/theses/17",
            json={"title": "Updated title", "core_claim": "Updated claim"},
        )

    assert response.status_code == 200
    assert update.call_args.kwargs["domain"] == THESIS["domain"]
    assert update.call_args.kwargs["research_question"] == THESIS["research_question"]
