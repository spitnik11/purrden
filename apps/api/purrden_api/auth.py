from __future__ import annotations

import secrets
from datetime import datetime, timezone
from urllib.parse import urlsplit
from fastapi import HTTPException, Request, Response
from sqlalchemy.orm import Session

from .models import BffSession
from .config import get_settings


def new_csrf() -> str:
    return secrets.token_urlsafe(32)


def set_session_cookies(response: Response, session: BffSession) -> None:
    settings = get_settings()
    name = "__Host-purrden_session" if settings.cookie_secure else "purrden_session"
    options = {"max_age": 60 * 60 * 24 * 30, "secure": settings.cookie_secure, "samesite": "lax", "path": "/"}
    response.set_cookie(name, session.id, httponly=True, **options)
    response.set_cookie("purrden_csrf", session.csrf_token or "", httponly=False, **options)


def session_expired(expires_at) -> bool:
    if not expires_at:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def player_from_request(
    request: Request,
    db: Session,
    x_purrden_session: str | None = None,
    x_csrf_token: str | None = None,
    *,
    write: bool = False,
) -> str:
    cookie_session = request.cookies.get("__Host-purrden_session") or request.cookies.get("purrden_session")
    session_id = x_purrden_session or cookie_session
    if not session_id:
        raise HTTPException(status_code=401, detail="missing_session")
    session = db.get(BffSession, session_id)
    if (not session or session.revoked or session_expired(session.expires_at)) and cookie_session and cookie_session != session_id:
        session_id = cookie_session
        session = db.get(BffSession, session_id)
    if not session or session.revoked:
        raise HTTPException(status_code=401, detail="invalid_session")
    if session_expired(session.expires_at):
        raise HTTPException(status_code=401, detail="expired_session")
    if write and not x_purrden_session and cookie_session:
        expected = urlsplit(str(request.base_url)).netloc
        supplied = request.headers.get("origin") or request.headers.get("referer")
        if not supplied or urlsplit(supplied).netloc != expected:
            raise HTTPException(status_code=403, detail="origin_failed")
        if not x_csrf_token or not secrets.compare_digest(x_csrf_token, session.csrf_token or ""):
            raise HTTPException(status_code=403, detail="csrf_failed")
    return session.player_id
