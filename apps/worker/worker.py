from celery import Celery
from kombu import Queue

from purrden_api.config import get_settings
from purrden_api.db import SessionLocal
from purrden_api.services.visits import create_visit

app = Celery("purrden", broker=get_settings().broker_url)
app.conf.update(
    broker_transport_options={"confirm_publish": True},
    task_acks_late=True,
    task_default_queue="visits",
    task_queues=(Queue("visits", durable=True, queue_arguments={"x-queue-type": "quorum"}),),
    task_reject_on_worker_lost=True,
    worker_enable_remote_control=False,
    worker_prefetch_multiplier=1,
)


@app.task(name="visit.evaluate")
def evaluate_visit(schedule_id: str) -> str:
    with SessionLocal() as db:
        return create_visit(db, schedule_id).id
