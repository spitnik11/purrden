from celery import Celery
from sqlalchemy import select

from purrden_api.config import get_settings
from purrden_api.db import SessionLocal
from purrden_api.models import OutboxEvent

app = Celery("purrden-dispatch", broker=get_settings().broker_url)


def dispatch() -> int:
    sent = 0
    with SessionLocal() as db:
        rows = db.scalars(select(OutboxEvent).where(OutboxEvent.published.is_(False)).limit(100)).all()
        for row in rows:
            app.send_task(row.topic, kwargs={"schedule_id": row.payload["scheduleId"]}, task_id=row.id)
            row.published = True
            sent += 1
        db.commit()
    return sent


if __name__ == "__main__":
    print(f"published={dispatch()}")
