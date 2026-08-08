from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import BffSession
from ..schemas import (
    DeviceListOut,
    DeviceOut,
    GuestClaimIn,
    GuestCreateIn,
    GuestCreateOut,
    SessionJoinIn,
)
from ..services.claim import (
    ClaimError,
    create_guest_player,
    join_session,
    list_devices,
)

router = APIRouter(prefix="/v1", tags=["guest"])


@router.post("/guest", response_model=GuestCreateOut)
def create_guest(
    body: GuestCreateIn | None = None,
    db: Session = Depends(get_db),
) -> GuestCreateOut:
    """Create empty guest player + opaque BFF session."""
    body = body or GuestCreateIn()
    result = create_guest_player(
        db,
        device_id=body.deviceId,
        label=body.label or "initial",
    )
    return GuestCreateOut(**result)


@router.post("/guest/claim", response_model=GuestCreateOut)
def claim_guest_genesis(
    body: GuestClaimIn,
    db: Session = Depends(get_db),
) -> GuestCreateOut:
    """
    One-time genesis import: create a guest cloud save from a sanitized local projection.
    Browser IDB is untrusted — server clamps inventory/energy and drops secrets.
    """
    result = create_guest_player(
        db,
        device_id=body.deviceId,
        label=body.label or "claim",
        projection=body.projection,
        display_name="Guest (claimed)",
    )
    return GuestCreateOut(**result)


@router.post("/session/join", response_model=GuestCreateOut)
def session_join(
    body: SessionJoinIn,
    db: Session = Depends(get_db),
) -> GuestCreateOut:
    """Second browser joins via shared session id (alpha multi-device)."""
    try:
        result = join_session(
            db,
            session_id=body.sessionId,
            device_id=body.deviceId,
            label=body.label or "join",
        )
    except ClaimError as e:
        raise HTTPException(status_code=401, detail=e.reason) from e
    return GuestCreateOut(**result)


@router.get("/devices", response_model=DeviceListOut)
def devices(
    db: Session = Depends(get_db),
    x_purrden_session: str | None = Header(default=None, alias="X-Purrden-Session"),
) -> DeviceListOut:
    if not x_purrden_session:
        raise HTTPException(status_code=401, detail="missing X-Purrden-Session")
    sess = db.get(BffSession, x_purrden_session)
    if not sess or sess.revoked:
        raise HTTPException(status_code=401, detail="invalid_session")
    rows = list_devices(db, sess.player_id)
    return DeviceListOut(
        player_id=sess.player_id,
        devices=[DeviceOut(**r) for r in rows],
    )
