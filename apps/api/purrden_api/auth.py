from __future__ import annotations

import secrets
from fastapi import Header, HTTPException, Request
from sqlalchemy.orm import Session

from .models import BffSession


def new_csrf() -> str:
    return secrets.token_urlsafe(32)


def player_from_request(
    request: Request,
    db: Session,
    x_purrden_session: str | None = None,
    x_csrf_token: str | None = None,
    *,
    write: bool = False,
) -> str:
    session_id = request.cookies.get("__Host-purrden_session") or request.cookies.get("purrden_session") or x_purrden_session
    if not session_id:
        raise HTTPException(status_code=401, detail="missing_session")
    session = db.get(BffSession, session_id)
    if not session or session.revoked:
        raise HTTPException(status_code=401, detail="invalid_session")
    if write and (request.cookies.get("purrden_session") or request.cookies.get("__Host-purrden_session")):
        if not x_csrf_token or not secrets.compare_digest(x_csrf_token, session.csrf_token or ""):
            raise HTTPException(status_code=403, detail="csrf_failed")
    return session.player_id
