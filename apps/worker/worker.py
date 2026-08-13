from celery import Celery

from purrden_api.config import get_settings
from purrden_api.db import SessionLocal
from purrden_api.services.visits import create_visit

app = Celery("purrden", broker=get_settings().broker_url)
app.conf.task_acks_late = True
app.conf.task_reject_on_worker_lost = True


@app.task(name="visit.evaluate")
def evaluate_visit(schedule_id: str) -> str:
    with SessionLocal() as db:
        return create_visit(db, schedule_id).id
