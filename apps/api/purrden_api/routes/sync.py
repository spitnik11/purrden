from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import BffSession
from ..auth import player_from_request
from ..schemas import BootstrapOut, SyncIn, SyncOut
from ..services.sync import apply_sync, get_player_save

router = APIRouter(prefix="/v1", tags=["sync"])


def _player_from_session(
    db: Session, session_id: str | None
) -> str:
    if not session_id:
        raise HTTPException(status_code=401, detail="missing X-Purrden-Session")
    sess = db.get(BffSession, session_id)
    if not sess or sess.revoked:
        raise HTTPException(status_code=401, detail="invalid_session")
    return sess.player_id


@router.get("/bootstrap", response_model=BootstrapOut)
def bootstrap(
    request: Request,
    db: Session = Depends(get_db),
    x_purrden_session: str | None = Header(default=None, alias="X-Purrden-Session"),
) -> BootstrapOut:
    player_id = player_from_request(request, db, x_purrden_session)
    try:
        _player, save = get_player_save(db, player_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return BootstrapOut(
        player_id=player_id,
        save_version=save.save_version,
        content_version=save.content_version,
        projection=save.projection or {},
    )


@router.post("/sync", response_model=SyncOut)
def sync(
    body: SyncIn,
    request: Request,
    db: Session = Depends(get_db),
    x_purrden_session: str | None = Header(default=None, alias="X-Purrden-Session"),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> SyncOut:
    """Append-only command sync. Retries are harmless (command_id uniqueness)."""
    player_id = player_from_request(request, db, x_purrden_session, x_csrf_token, write=True)
    try:
        result = apply_sync(
            db,
            player_id=player_id,
            known_save_version=body.knownSaveVersion,
            commands=[c.model_dump() for c in body.commands],
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return SyncOut(
        save_version=result["save_version"],
        projection=result["projection"],
        acks=[
            {
                "commandId": a["commandId"],
                "status": a["status"],
                "reject_reason": a.get("reject_reason"),
            }
            for a in result["acks"]
        ],
        server_time=result["server_time"],
    )
