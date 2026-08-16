from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import player_from_request
from ..db import get_db
from ..models import VisitorInbox
from ..config import get_settings
from ..schemas import VisitScheduleIn
from ..services.visits import schedule_visit
from ..services.world import OpenMeteoWeather, WorldContextService

router = APIRouter(prefix="/v1/visits", tags=["visits"])


@router.post("/schedule")
def schedule(request: Request, body: VisitScheduleIn, db: Session = Depends(get_db), x_purrden_session: str | None = Header(default=None, alias="X-Purrden-Session"), x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")):
    player_id = player_from_request(request, db, x_purrden_session, x_csrf_token, write=True)
    world = WorldContextService(OpenMeteoWeather(get_settings().weather_base_url)).get(body.latitude, body.longitude)
    row = schedule_visit(db, player_id, datetime.now(timezone.utc), world)
    return {"scheduleId": row.id, "status": row.status}


@router.get("/inbox")
def inbox(request: Request, db: Session = Depends(get_db), x_purrden_session: str | None = Header(default=None, alias="X-Purrden-Session")):
    player_id = player_from_request(request, db, x_purrden_session)
    rows = db.scalars(select(VisitorInbox).where(VisitorInbox.player_id == player_id).order_by(VisitorInbox.created_at.desc()).limit(50)).all()
    return [{"id": row.id, "catId": row.cat_id, "world": row.world, "read": row.read, "createdAt": row.created_at} for row in rows]
