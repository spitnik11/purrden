from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import OutboxEvent, SpawnSchedule, VisitorInbox


def schedule_visit(db: Session, player_id: str, due_at: datetime, world: dict) -> SpawnSchedule:
    row = SpawnSchedule(player_id=player_id, due_at=due_at, world=world)
    db.add(row); db.commit(); db.refresh(row)
    return row


def claim_due(db: Session, limit: int = 100) -> list[SpawnSchedule]:
    query = select(SpawnSchedule).where(SpawnSchedule.status == "pending", SpawnSchedule.due_at <= datetime.now(timezone.utc)).order_by(SpawnSchedule.due_at).limit(limit)
    if db.bind and db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    rows = list(db.scalars(query).all())
    for row in rows:
        row.status = "queued"
        db.add(OutboxEvent(topic="visit.evaluate", payload={"scheduleId": row.id}))
    db.commit()
    return rows


def create_visit(db: Session, schedule_id: str) -> VisitorInbox:
    existing = db.scalar(select(VisitorInbox).where(VisitorInbox.schedule_id == schedule_id))
    if existing:
        return existing
    schedule = db.get(SpawnSchedule, schedule_id)
    if not schedule:
        raise LookupError("schedule_not_found")
    precipitation = (schedule.world or {}).get("precipitation")
    cat_id = "cat:mizzle:v1" if precipitation in {"rain", "drizzle", "storm"} else "cat:tabby:v1"
    visit = VisitorInbox(schedule_id=schedule.id, player_id=schedule.player_id, cat_id=cat_id, world=schedule.world or {})
    schedule.status = "completed"
    db.add(visit); db.commit(); db.refresh(visit)
    return visit
