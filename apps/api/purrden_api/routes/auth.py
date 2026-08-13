from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..auth import new_csrf, player_from_request, set_session_cookies
from ..config import get_settings
from ..db import get_db
from ..models import BffSession, Player

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _cookie(response, name: str, value: str, *, http_only: bool = True, max_age: int = 600):
    settings = get_settings()
    response.set_cookie(name, value, max_age=max_age, httponly=http_only, secure=settings.cookie_secure, samesite="lax", path="/")


@router.get("/login")
def login(request: Request) -> RedirectResponse:
    s = get_settings()
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    query = urlencode({"client_id": s.keycloak_client_id, "redirect_uri": f"{s.public_url}/v1/auth/callback", "response_type": "code", "scope": "openid profile", "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})
    response = RedirectResponse(f"{s.keycloak_url}/realms/{s.keycloak_realm}/protocol/openid-connect/auth?{query}")
    _cookie(response, "purrden_oidc_state", state)
    _cookie(response, "purrden_oidc_verifier", verifier)
    existing = request.cookies.get("__Host-purrden_session") or request.cookies.get("purrden_session")
    if existing:
        _cookie(response, "purrden_claim_session", existing)
    return response


@router.get("/callback")
def callback(request: Request, state: str, code: str | None = None, error: str | None = None, db: Session = Depends(get_db)) -> RedirectResponse:
    s = get_settings()
    if not request.cookies.get("purrden_oidc_state") or not secrets.compare_digest(state, request.cookies["purrden_oidc_state"]):
        raise HTTPException(status_code=400, detail="invalid_oidc_state")
    if error or not code:
        raise HTTPException(status_code=400, detail="oidc_login_failed")
    token_url = f"{s.keycloak_internal_url}/realms/{s.keycloak_realm}/protocol/openid-connect/token"
    data = {"grant_type": "authorization_code", "client_id": s.keycloak_client_id, "code": code, "redirect_uri": f"{s.public_url}/v1/auth/callback", "code_verifier": request.cookies.get("purrden_oidc_verifier", "")}
    if s.keycloak_client_secret:
        data["client_secret"] = s.keycloak_client_secret
    with httpx.Client(timeout=5) as client:
        token = client.post(token_url, data=data); token.raise_for_status()
        user = client.get(f"{s.keycloak_internal_url}/realms/{s.keycloak_realm}/protocol/openid-connect/userinfo", headers={"Authorization": f"Bearer {token.json()['access_token']}"}); user.raise_for_status()
    identity = user.json()
    player = db.scalar(select(Player).where(Player.oidc_subject == identity["sub"]))
    claim_session = db.get(BffSession, request.cookies.get("purrden_claim_session", ""))
    if not player and claim_session:
        player = db.get(Player, claim_session.player_id)
        if player:
            player.oidc_subject = identity["sub"]
            player.display_name = identity.get("preferred_username") or identity.get("name")
            player.is_guest = 0
    if not player:
        player = Player(oidc_subject=identity["sub"], display_name=identity.get("preferred_username") or identity.get("name"), is_guest=0)
        db.add(player); db.flush()
    db.execute(update(BffSession).where(BffSession.player_id == player.id).values(revoked=1))
    session = BffSession(player_id=player.id, csrf_token=new_csrf(), expires_at=datetime.now(timezone.utc) + timedelta(days=30))
    db.add(session); db.commit()
    response = RedirectResponse("/")
    set_session_cookies(response, session)
    response.delete_cookie("purrden_oidc_state"); response.delete_cookie("purrden_oidc_verifier"); response.delete_cookie("purrden_claim_session")
    return response


@router.post("/claim")
def claim_named(request: Request, db: Session = Depends(get_db), x_purrden_session: str | None = Header(default=None, alias="X-Purrden-Session"), x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")):
    player_id = player_from_request(request, db, x_purrden_session, x_csrf_token, write=True)
    player = db.get(Player, player_id)
    if not player or not player.oidc_subject:
        raise HTTPException(status_code=409, detail="named_account_required")
    player.is_guest = 0; db.commit()
    return {"playerId": player.id, "claimed": True}


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db), x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")):
    player_from_request(request, db, None, x_csrf_token, write=True)
    session_id = request.cookies.get("__Host-purrden_session") or request.cookies.get("purrden_session")
    session = db.get(BffSession, session_id)
    session.revoked = 1
    db.commit()
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("__Host-purrden_session", path="/", secure=True, httponly=True, samesite="lax")
    response.delete_cookie("purrden_session", path="/", httponly=True, samesite="lax")
    response.delete_cookie("purrden_csrf", path="/", samesite="lax")
    return response
