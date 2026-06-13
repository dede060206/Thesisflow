from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.theses import (
    DRAFT_SECTION_KEYS,
    clean_memo_display,
    present_evidence,
    regenerate_thesis_section,
    select_section_evidence,
    upgrade_legacy_sections,
)
from app.thesis_research import (
    EvidenceCandidate,
    ExternalWebEvidenceProvider,
    fetch_external_evidence,
    research_thesis_evidence,
    resolve_candidate,
)


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


def test_thesis_workspace_sidebar_can_search_and_add_article_evidence() -> None:
    evidence = [
        {
            "id": 31,
            "article_id": 11,
            "title": "Identity for Agents",
            "source": "Sequoia",
            "url": "https://example.com/identity",
            "published_at": "2026-06-01",
            "excerpt": "Agents require permissions and audit logs.",
            "note": None,
            "evidence_type": "article",
            "classification": "SUPPORTING",
            "strength": "high",
            "source_credibility": "high",
            "ai_recommendation": "prioritise",
            "evidence_state": "added",
        }
    ]
    with (
        patch("app.thesis_routes.get_thesis", return_value=THESIS),
        patch("app.thesis_routes.list_thesis_evidence", return_value=evidence),
    ):
        response = TestClient(app).get("/thesis-builder/17")

    assert response.status_code == 200
    assert 'id="sidebar-evidence-search-form"' in response.text
    assert "/api/theses/${thesisId}/evidence/search" in response.text
    assert "/api/theses/${thesisId}/evidence/articles" in response.text
    assert 'href="/article/11"' in response.text
    assert 'href="https://example.com/identity"' in response.text
    assert "查看原文" in response.text
    assert 'setTimeout(() => window.location.reload(), 450)' not in response.text
    assert "appendEvidence([data.evidence])" in response.text
    assert "为本节搜索证据" in response.text
    assert "补充外部研究" in response.text
    assert "section-coverage" in response.text
    assert "生成 Investment Memo" in response.text
    assert 'id="memo-result"' in response.text
    assert "document.getElementById(\"memo-output\").textContent = data.memo" in response.text


def test_sidebar_article_search_reuses_existing_evidence_api() -> None:
    article = {
        "id": 11,
        "title": "Identity for Agents",
        "source": "Sequoia",
        "url": "https://example.com/identity",
        "published_at": "2026-06-01",
        "fetched_at": "2026-06-02",
        "category": "AI",
        "summary": "Identity and permissions become critical infrastructure.",
        "word_count": 1800,
    }
    with (
        patch("app.thesis_routes.get_thesis", return_value=THESIS),
        patch("app.thesis_routes.search_articles_for_evidence", return_value=[article]) as search,
    ):
        response = TestClient(app).get(
            "/api/theses/17/evidence/search?q=agent%20identity"
        )

    assert response.status_code == 200
    assert response.json()[0]["id"] == 11
    search.assert_called_once_with("agent identity")


def test_evidence_card_presentation_extracts_chinese_title_and_cleans_markdown() -> None:
    item = {
        "id": 60,
        "title": "India must choose: Import AI breakthroughs or create them",
        "excerpt": (
            "## 中文导读标题\n印度必须决定由谁创造 AI 突破\n\n"
            "## 核心判断\n**印度 AI 生态**需要加强基础设施和研发投入。\n"
            "- 目前仍依赖进口关键技术。"
        ),
        "note": "这份证据说明基础设施自主能力会影响 AI 价值链中的长期议价权。",
    }

    presented = present_evidence(item)

    assert presented["chinese_title"] == "印度必须决定由谁创造 AI 突破"
    assert presented["original_title"].startswith("India must choose")
    assert "##" not in presented["display_excerpt"]
    assert "**" not in presented["display_excerpt"]
    assert presented["importance"].startswith("这份证据说明")


def test_clean_memo_display_removes_markdown_heading_symbols() -> None:
    cleaned = clean_memo_display("# Investment Memo\n---\n## 投资摘要\n**核心判断**成立。")

    assert "#" not in cleaned
    assert "---" not in cleaned
    assert "**" not in cleaned
    assert "投资摘要" in cleaned


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


def test_external_web_provider_returns_only_verified_signed_sources() -> None:
    generated = {
        "results": [
            {
                "title": "Agent identity infrastructure",
                "source": "Example Research",
                "url": "https://example.com/agent-identity",
                "published_at": "2026-06-10",
                "excerpt": "Enterprise agents require permissioning and audit logs.",
            },
            {
                "title": "Invented source",
                "source": "Unknown",
                "url": "https://invented.example/fake",
                "published_at": "",
                "excerpt": "This URL was not returned by web search.",
            },
        ]
    }
    response = SimpleNamespace(
        output_text=json.dumps(generated),
        model_dump=lambda: {
            "output": [
                {
                    "type": "web_search_call",
                    "action": {
                        "sources": [
                            {
                                "title": "Agent identity infrastructure",
                                "url": "https://example.com/agent-identity",
                            }
                        ]
                    },
                }
            ]
        },
    )
    client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: response))

    with (
        patch("app.thesis_research.OPENAI_API_KEY", "test-key"),
        patch("app.thesis_research.OpenAI", return_value=client),
    ):
        candidates = ExternalWebEvidenceProvider().search(
            "agent identity", "workspace-one"
        )

    assert len(candidates) == 1
    assert candidates[0].ref.startswith("web:")
    resolved = resolve_candidate(candidates[0].ref, "workspace-one")
    assert resolved is not None
    assert resolved.url == "https://example.com/agent-identity"
    assert resolve_candidate(candidates[0].ref, "different-workspace") is None


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


def test_section_regeneration_prompts_with_real_evidence_ids() -> None:
    evidence = [
        {
            "id": 51,
            "evidence_type": "article",
            "title": "Agent trust infrastructure",
            "source": "Sequoia",
            "url": "https://example.com/agent-trust",
            "excerpt": "Agent transactions require identity, permissions, and audit logs.",
            "classification": "SUPPORTING",
            "strength": "high",
            "source_credibility": "high",
            "evidence_state": "added",
        }
    ]
    response = SimpleNamespace(
        output_text=json.dumps(
            {"content": "Trust infrastructure becomes a control point.", "evidence_ids": [51]}
        )
    )
    calls = []
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: calls.append(kwargs) or response)
    )
    with (
        patch("app.theses.OPENAI_API_KEY", "test-key"),
        patch("app.theses.OpenAI", return_value=client),
    ):
        result = regenerate_thesis_section(THESIS, evidence, "core_claim")

    assert result["evidence_ids"] == [51]
    prompt = calls[0]["input"][1]["content"]
    assert "Allowed evidence IDs: [51]" in prompt
    prose_prompt = calls[1]["input"][1]["content"]
    assert "Allowed evidence IDs for this section: [51]" in prose_prompt
    assert "placeholder IDs" in prose_prompt


def test_section_evidence_selection_prefers_relevant_added_evidence() -> None:
    evidence = [
        {
            "id": 1,
            "title": "Identity and audit infrastructure",
            "excerpt": "Enterprise agent adoption requires permissions and audit logs.",
            "classification": "SUPPORTING",
            "strength": "high",
            "evidence_state": "added",
        },
        {
            "id": 2,
            "title": "Unrelated consumer brands",
            "excerpt": "A discussion of retail packaging.",
            "classification": "CONTEXT",
            "strength": "low",
            "evidence_state": "added",
        },
        {
            "id": 3,
            "title": "Saved risk",
            "excerpt": "Agent adoption may stall.",
            "classification": "COUNTER",
            "strength": "high",
            "evidence_state": "saved_for_later",
        },
    ]

    selected = select_section_evidence(THESIS, evidence, "why_now", limit=2)

    assert selected[0]["id"] == 1
    assert all(item["id"] != 3 for item in selected)


def test_section_selection_balances_web_and_internal_sources_and_limits_reuse() -> None:
    evidence = []
    for evidence_type, start in (("article", 10), ("web", 20), ("weekly_signal", 30)):
        for offset in range(4):
            evidence.append(
                {
                    "id": start + offset,
                    "evidence_type": evidence_type,
                    "title": f"Agent identity evidence {start + offset}",
                    "excerpt": "Agent identity permissions audit market adoption 42%",
                    "classification": "SUPPORTING",
                    "strength": "high",
                    "source_credibility": "high",
                    "evidence_state": "added",
                    "content_word_count": 1200,
                    "extraction_status": "extracted" if evidence_type == "web" else None,
                    "full_content": "Detailed source content" if evidence_type == "web" else None,
                }
            )

    selected = select_section_evidence(
        THESIS,
        evidence,
        "core_claim",
        usage_counts={10: 3, 20: 2},
    )

    assert 10 not in {item["id"] for item in selected}
    assert sum(item["evidence_type"] == "web" for item in selected) >= 2
    assert sum(item["evidence_type"] == "article" for item in selected) >= 2


def test_external_fetch_blocks_private_network_urls() -> None:
    with patch(
        "app.thesis_research.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("127.0.0.1", 0))],
    ):
        result = fetch_external_evidence("http://example.com/private")

    assert result["status"] == "blocked_url"
    assert result["content"] == ""


def test_generate_all_uses_only_currently_added_evidence() -> None:
    evidence = [
        {"id": 11, "evidence_state": "added"},
        {"id": 12, "evidence_state": "saved_for_later"},
    ]
    sections = complete_sections()
    with (
        patch("app.thesis_routes.get_thesis", return_value=THESIS),
        patch("app.thesis_routes.list_thesis_evidence", return_value=evidence),
        patch("app.thesis_routes.generate_thesis_sections", return_value=sections) as generate,
        patch("app.thesis_routes.save_thesis_sections", return_value=THESIS),
        patch("app.thesis_routes.add_researched_evidence") as research,
    ):
        response = TestClient(app).post("/api/theses/17/generate")

    assert response.status_code == 200
    assert generate.call_args.args[1] == [evidence[0]]
    research.assert_not_called()


def test_refresh_research_adds_evidence_for_existing_thesis() -> None:
    added = [{"id": 91, "title": "External identity research", "excerpt": "Finding"}]
    with (
        patch("app.thesis_routes.get_thesis", return_value=THESIS),
        patch("app.thesis_routes.count_thesis_evidence", return_value=8),
        patch("app.thesis_routes.build_initial_evidence_library", return_value=added) as research,
        patch("app.thesis_routes.list_thesis_evidence", return_value=added),
    ):
        response = TestClient(app).post("/api/theses/17/research/refresh")

    assert response.status_code == 200
    assert response.json()["added"][0]["id"] == 91
    assert research.call_args.args[0] == THESIS
    assert research.call_args.kwargs["limit"] == 20


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
        patch("app.thesis_routes.add_researched_evidence", return_value=[]) as research,
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
    query = research.call_args_list[0].args[2]
    assert "Agent Infrastructure" in query
    assert "Where will value accrue?" in query
    assert THESIS["initial_view"] in query
    assert research.call_args_list[0].kwargs["limit"] == 12
    assert len(research.call_args_list) > 1


def test_memo_exports_markdown_and_text() -> None:
    thesis = {**THESIS, "investment_memo": "## Core Claim\nEvidence-backed claim [E11]."}
    with patch("app.thesis_routes.get_thesis", return_value=thesis):
        markdown = TestClient(app).get("/theses/17/export.md")
        text = TestClient(app).get("/theses/17/export.txt")

    assert markdown.status_code == 200
    assert markdown.headers["content-disposition"].endswith('.md"')
    assert text.status_code == 200
    assert text.headers["content-disposition"].endswith('.txt"')


def test_memo_exports_word_document() -> None:
    thesis = {**THESIS, "investment_memo": "## Core Claim\n- Evidence-backed claim [E11]."}
    with patch("app.thesis_routes.get_thesis", return_value=thesis):
        response = TestClient(app).get("/theses/17/export.docx")

    assert response.status_code == 200
    assert response.headers["content-disposition"].endswith('.docx"')
    assert response.content.startswith(b"PK")


def test_memo_api_returns_actionable_generation_error() -> None:
    with (
        patch("app.thesis_routes.get_thesis", return_value=THESIS),
        patch("app.thesis_routes.list_thesis_evidence", return_value=[]),
        patch(
            "app.thesis_routes.generate_investment_memo",
            side_effect=ValueError("context is too large"),
        ),
    ):
        response = TestClient(app).post("/api/theses/17/memo")

    assert response.status_code == 502
    assert "context is too large" in response.json()["detail"]


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


def test_evidence_shortage_message_does_not_replace_core_claim() -> None:
    with (
        patch("app.thesis_routes.get_thesis", return_value=THESIS),
        patch("app.thesis_routes.update_thesis", return_value=THESIS) as update,
    ):
        response = TestClient(app).patch(
            "/api/theses/17",
            json={
                "title": THESIS["title"],
                "core_claim": "现有证据不足，无法形成有来源支持的判断。",
            },
        )

    assert response.status_code == 200
    assert update.call_args.kwargs["core_claim"] == THESIS["initial_view"]
