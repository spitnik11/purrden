from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import BffSession, Device, Player, PlayerSave
from ..projection import empty_projection
from ..schemas import GuestCreateOut

router = APIRouter(prefix="/v1", tags=["guest"])


@router.post("/guest", response_model=GuestCreateOut)
def create_guest(db: Session = Depends(get_db)) -> GuestCreateOut:
    """Create a guest player + opaque BFF session (Keycloak arrives later)."""
    device_id = str(uuid4())
    player = Player(is_guest=1, display_name="Guest")
    db.add(player)
    db.flush()

    projection = empty_projection(device_id=device_id)
    save = PlayerSave(
        player_id=player.id,
        save_version=0,
        projection=projection,
        content_version=projection["contentVersion"],
        schema_version=1,
    )
    db.add(save)
    db.add(Device(player_id=player.id, device_id=device_id, label="initial"))
    session = BffSession(player_id=player.id)
    db.add(session)
    db.commit()

    return GuestCreateOut(
        player_id=player.id,
        session_id=session.id,
        device_id=device_id,
        save_version=0,
        projection=projection,
    )
