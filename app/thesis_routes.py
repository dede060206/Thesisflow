from __future__ import annotations

import re
import json

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from app.config import THESIS_MAX_EVIDENCE, THESIS_MAX_PER_WORKSPACE, THESIS_MODEL
from app.database import (
    add_article_evidence,
    add_snapshot_evidence,
    count_thesis_evidence,
    count_theses,
    create_thesis,
    delete_thesis_evidence,
    get_thesis,
    list_theses,
    list_thesis_evidence,
    save_thesis_memo,
    save_thesis_sections,
    search_articles_for_evidence,
    update_thesis,
)
from app.theses import generate_investment_memo, generate_thesis_sections
from app.workspace import set_workspace_cookie, workspace_for_request


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


class ThesisCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    core_claim: str = Field(min_length=1, max_length=3000)


class ThesisUpdate(ThesisCreate):
    pass


class ArticleEvidenceRequest(BaseModel):
    article_ids: list[int] = Field(min_length=1, max_length=5)


class SnapshotEvidenceRequest(BaseModel):
    evidence_type: str
    title: str = Field(min_length=1, max_length=250)
    excerpt: str = Field(min_length=1, max_length=12000)
    source: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=2000)
    note: str | None = Field(default=None, max_length=2000)
    article_ids: list[int] = Field(default_factory=list, max_length=10)
    metadata: dict = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value and not value.startswith(("https://", "http://")):
            raise ValueError("URL must use http or https.")
        return value


def owned_thesis_or_404(thesis_id: int, workspace_id: str) -> dict:
    thesis = get_thesis(thesis_id, workspace_id)
    if not thesis:
        raise HTTPException(status_code=404, detail="Thesis not found.")
    return thesis


def attach_cookie(
    response: Response, request: Request, workspace_id: str, is_new: bool
) -> None:
    if is_new:
        set_workspace_cookie(response, workspace_id, request)


@router.get("/theses", response_class=HTMLResponse)
def theses_page(request: Request) -> HTMLResponse:
    workspace_id, is_new = workspace_for_request(request)
    response = templates.TemplateResponse(
        request, "theses.html", {"theses": list_theses(workspace_id)}
    )
    attach_cookie(response, request, workspace_id, is_new)
    return response


@router.get("/theses/new", response_class=HTMLResponse)
def thesis_new_page(request: Request) -> HTMLResponse:
    workspace_id, is_new = workspace_for_request(request)
    response = templates.TemplateResponse(request, "thesis_new.html", {})
    attach_cookie(response, request, workspace_id, is_new)
    return response


@router.get("/theses/{thesis_id}", response_class=HTMLResponse)
def thesis_detail_page(request: Request, thesis_id: int) -> HTMLResponse:
    workspace_id, is_new = workspace_for_request(request)
    thesis = get_thesis(thesis_id, workspace_id)
    evidence = list_thesis_evidence(thesis_id, workspace_id) if thesis else []
    response = templates.TemplateResponse(
        request,
        "thesis_detail.html",
        {"thesis": thesis, "evidence": evidence, "max_evidence": THESIS_MAX_EVIDENCE},
        status_code=200 if thesis else 404,
    )
    attach_cookie(response, request, workspace_id, is_new)
    return response


@router.get("/api/theses")
def api_list_theses(request: Request, response: Response) -> list[dict]:
    workspace_id, is_new = workspace_for_request(request)
    attach_cookie(response, request, workspace_id, is_new)
    return list_theses(workspace_id)


@router.post("/api/theses", status_code=201)
def api_create_thesis(
    request: Request, response: Response, payload: ThesisCreate
) -> dict:
    workspace_id, is_new = workspace_for_request(request)
    title = payload.title.strip()
    core_claim = payload.core_claim.strip()
    if not title or not core_claim:
        raise HTTPException(status_code=400, detail="Title and core claim are required.")
    if count_theses(workspace_id) >= THESIS_MAX_PER_WORKSPACE:
        raise HTTPException(status_code=400, detail="Workspace thesis limit reached.")
    thesis = create_thesis(workspace_id, title, core_claim)
    attach_cookie(response, request, workspace_id, is_new)
    return thesis


@router.patch("/api/theses/{thesis_id}")
def api_update_thesis(
    request: Request, response: Response, thesis_id: int, payload: ThesisUpdate
) -> dict:
    workspace_id, is_new = workspace_for_request(request)
    title = payload.title.strip()
    core_claim = payload.core_claim.strip()
    if not title or not core_claim:
        raise HTTPException(status_code=400, detail="Title and core claim are required.")
    thesis = update_thesis(
        thesis_id,
        workspace_id,
        title=title,
        core_claim=core_claim,
    )
    if not thesis:
        raise HTTPException(status_code=404, detail="Thesis not found.")
    attach_cookie(response, request, workspace_id, is_new)
    return thesis


@router.get("/api/theses/{thesis_id}/evidence/search")
def api_search_evidence(request: Request, thesis_id: int, q: str = "") -> list[dict]:
    workspace_id, _ = workspace_for_request(request)
    owned_thesis_or_404(thesis_id, workspace_id)
    query = q.strip()
    return search_articles_for_evidence(query[:200]) if len(query) >= 2 else []


@router.post("/api/theses/{thesis_id}/evidence/articles")
def api_add_article_evidence(
    request: Request, thesis_id: int, payload: ArticleEvidenceRequest
) -> dict:
    workspace_id, _ = workspace_for_request(request)
    owned_thesis_or_404(thesis_id, workspace_id)
    added = []
    for article_id in dict.fromkeys(payload.article_ids):
        if count_thesis_evidence(thesis_id, workspace_id) >= THESIS_MAX_EVIDENCE:
            break
        item = add_article_evidence(thesis_id, workspace_id, article_id)
        if item:
            added.append(item)
    if not added:
        raise HTTPException(status_code=400, detail="No evidence added or evidence limit reached.")
    return {"added": added, "evidence_count": count_thesis_evidence(thesis_id, workspace_id)}


@router.post("/api/theses/{thesis_id}/evidence/import")
def api_import_evidence(
    request: Request, thesis_id: int, payload: SnapshotEvidenceRequest
) -> dict:
    workspace_id, _ = workspace_for_request(request)
    owned_thesis_or_404(thesis_id, workspace_id)
    if payload.evidence_type not in {"chat", "comparison", "weekly_signal", "manual"}:
        raise HTTPException(status_code=400, detail="Unsupported evidence type.")
    if len(json.dumps(payload.metadata)) > 5000:
        raise HTTPException(status_code=400, detail="Evidence metadata is too large.")
    if count_thesis_evidence(thesis_id, workspace_id) >= THESIS_MAX_EVIDENCE:
        raise HTTPException(status_code=400, detail="Evidence limit reached.")
    snapshot = add_snapshot_evidence(
        thesis_id,
        workspace_id,
        evidence_type=payload.evidence_type,
        title=payload.title.strip(),
        excerpt=payload.excerpt.strip(),
        source=payload.source,
        url=payload.url,
        note=payload.note,
        metadata=payload.metadata,
    )
    added_articles = []
    for article_id in dict.fromkeys(payload.article_ids):
        if count_thesis_evidence(thesis_id, workspace_id) >= THESIS_MAX_EVIDENCE:
            break
        item = add_article_evidence(thesis_id, workspace_id, article_id)
        if item:
            added_articles.append(item)
    return {"snapshot": snapshot, "articles": added_articles}


@router.delete("/api/theses/{thesis_id}/evidence/{evidence_id}")
def api_delete_evidence(request: Request, thesis_id: int, evidence_id: int) -> dict:
    workspace_id, _ = workspace_for_request(request)
    if not delete_thesis_evidence(thesis_id, workspace_id, evidence_id):
        raise HTTPException(status_code=404, detail="Evidence not found.")
    return {"deleted": True}


@router.post("/api/theses/{thesis_id}/generate")
def api_generate_thesis(request: Request, thesis_id: int) -> dict:
    workspace_id, _ = workspace_for_request(request)
    thesis = owned_thesis_or_404(thesis_id, workspace_id)
    evidence = list_thesis_evidence(thesis_id, workspace_id)
    try:
        sections = generate_thesis_sections(thesis, evidence)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    updated = save_thesis_sections(thesis_id, workspace_id, sections, THESIS_MODEL)
    return {"thesis": updated, "sections": sections}


@router.post("/api/theses/{thesis_id}/memo")
def api_generate_memo(request: Request, thesis_id: int) -> dict:
    workspace_id, _ = workspace_for_request(request)
    thesis = owned_thesis_or_404(thesis_id, workspace_id)
    evidence = list_thesis_evidence(thesis_id, workspace_id)
    try:
        memo = generate_investment_memo(thesis, evidence)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    updated = save_thesis_memo(thesis_id, workspace_id, memo, THESIS_MODEL)
    return {"thesis": updated, "memo": memo}


@router.get("/theses/{thesis_id}/export.md")
def export_thesis_memo(request: Request, thesis_id: int) -> PlainTextResponse:
    workspace_id, _ = workspace_for_request(request)
    thesis = owned_thesis_or_404(thesis_id, workspace_id)
    if not thesis.get("investment_memo"):
        raise HTTPException(status_code=400, detail="Generate the memo before export.")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", thesis["title"]).strip("-").lower()
    return PlainTextResponse(
        thesis["investment_memo"],
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{slug or "investment-thesis"}.md"'
        },
    )
