from purrden_api.db import SessionLocal
from purrden_api.services.visits import claim_due


def tick() -> int:
    with SessionLocal() as db:
        return len(claim_due(db))


if __name__ == "__main__":
    print(f"queued={tick()}")
