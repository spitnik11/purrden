from datetime import datetime, timezone

from purrden_api.db import SessionLocal
from purrden_api.models import Player
from purrden_api.services.visits import claim_due, create_visit, schedule_visit


def test_schedule_outbox_worker_inbox_is_idempotent():
    with SessionLocal() as db:
        player = Player(display_name="rain tester")
        db.add(player); db.commit(); db.refresh(player)
        schedule = schedule_visit(db, player.id, datetime.now(timezone.utc), {"precipitation": "rain"})
        assert claim_due(db) == [schedule]
        first = create_visit(db, schedule.id)
        second = create_visit(db, schedule.id)
        assert first.id == second.id
        assert first.cat_id == "cat:mizzle:v1"
