from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import player_from_request
from ..db import get_db
from ..models import VisitorInbox
from ..services.visits import schedule_visit

router = APIRouter(prefix="/v1/visits", tags=["visits"])


@router.post("/schedule")
def schedule(request: Request, world: dict, db: Session = Depends(get_db), x_purrden_session: str | None = Header(default=None, alias="X-Purrden-Session"), x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")):
    player_id = player_from_request(request, db, x_purrden_session, x_csrf_token, write=True)
    row = schedule_visit(db, player_id, datetime.now(timezone.utc), world)
    return {"scheduleId": row.id, "status": row.status}


@router.get("/inbox")
def inbox(request: Request, db: Session = Depends(get_db), x_purrden_session: str | None = Header(default=None, alias="X-Purrden-Session")):
    player_id = player_from_request(request, db, x_purrden_session)
    rows = db.scalars(select(VisitorInbox).where(VisitorInbox.player_id == player_id).order_by(VisitorInbox.created_at.desc()).limit(50)).all()
    return [{"id": row.id, "catId": row.cat_id, "world": row.world, "read": row.read, "createdAt": row.created_at} for row in rows]
