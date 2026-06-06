from __future__ import annotations

import hashlib
import hmac
import uuid

from fastapi import Request
from starlette.responses import Response

from app.config import WORKSPACE_SECRET


COOKIE_NAME = "thesisflow_workspace"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365


def sign_workspace(workspace_id: str) -> str:
    signature = hmac.new(
        WORKSPACE_SECRET.encode("utf-8"),
        workspace_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{workspace_id}.{signature}"


def verify_workspace(value: str | None) -> str | None:
    if not value or "." not in value:
        return None
    workspace_id, signature = value.rsplit(".", 1)
    try:
        normalized = str(uuid.UUID(workspace_id))
    except ValueError:
        return None
    expected = sign_workspace(normalized).rsplit(".", 1)[1]
    return normalized if hmac.compare_digest(signature, expected) else None


def workspace_for_request(request: Request) -> tuple[str, bool]:
    existing = verify_workspace(request.cookies.get(COOKIE_NAME))
    if existing:
        return existing, False
    return str(uuid.uuid4()), True


def set_workspace_cookie(
    response: Response,
    workspace_id: str,
    request: Request,
) -> None:
    response.set_cookie(
        COOKIE_NAME,
        sign_workspace(workspace_id),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
