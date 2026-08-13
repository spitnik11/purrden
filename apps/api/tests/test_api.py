"""API tests — SQLite in-memory, no Postgres required."""
from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["ENV"] = "test"

from fastapi.testclient import TestClient  # noqa: E402

from purrden_api.config import get_settings  # noqa: E402
from purrden_api.db import Base, engine, init_db  # noqa: E402
from purrden_api.main import create_app  # noqa: E402


def setup_function(_function=None):  # noqa: ANN001
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def client() -> TestClient:
    # Lifespan also calls init_db; tables already created in setup_function.
    return TestClient(create_app())


def test_health():
    c = client()
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_guest_bootstrap_and_sync_idempotent():
    c = client()
    g = c.post("/v1/guest")
    assert g.status_code == 200, g.text
    body = g.json()
    session = body["session_id"]
    device = body["device_id"]
    headers = {"X-Purrden-Session": session}

    boot = c.get("/v1/bootstrap", headers=headers)
    assert boot.status_code == 200
    assert boot.json()["save_version"] == 0

    cmd = {
        "commandId": "cmd-plant-1",
        "deviceId": device,
        "deviceSequence": 1,
        "baseSaveVersion": 0,
        "type": "garden.plant_place",
        "payload": {"slotIndex": 0, "plantId": "plant:fern:v1"},
    }
    s1 = c.post(
        "/v1/sync",
        headers=headers,
        json={"knownSaveVersion": 0, "commands": [cmd]},
    )
    assert s1.status_code == 200, s1.text
    j1 = s1.json()
    assert j1["acks"][0]["status"] == "applied"
    assert j1["save_version"] == 1
    assert j1["projection"]["slots"][0]["plantId"] == "plant:fern:v1"

    s2 = c.post(
        "/v1/sync",
        headers=headers,
        json={"knownSaveVersion": 1, "commands": [cmd]},
    )
    assert s2.status_code == 200
    j2 = s2.json()
    assert j2["acks"][0]["status"] == "dup"
    assert j2["save_version"] == 1


def test_focus_complete_idempotent_energy():
    c = client()
    g = c.post("/v1/guest").json()
    headers = {"X-Purrden-Session": g["session_id"]}
    device = g["device_id"]
    energy0 = g["projection"]["growthEnergy"]

    def sync(commands, known=0):
        return c.post(
            "/v1/sync",
            headers=headers,
            json={"knownSaveVersion": known, "commands": commands},
        ).json()

    r1 = sync(
        [
            {
                "commandId": "f-start",
                "deviceId": device,
                "deviceSequence": 1,
                "baseSaveVersion": 0,
                "type": "focus.start",
                "payload": {"seconds": 60},
            },
            {
                "commandId": "f-done",
                "deviceId": device,
                "deviceSequence": 2,
                "baseSaveVersion": 0,
                "type": "focus.complete",
                "payload": {},
            },
        ]
    )
    assert r1["acks"][0]["status"] == "applied"
    assert r1["acks"][1]["status"] == "applied"
    energy = r1["projection"]["growthEnergy"]
    spawns = r1["projection"]["pendingSpawnWindows"]
    assert energy > energy0
    assert spawns >= 1

    # Second complete (already rewarded) → applied as no-op, no extra energy
    r2 = sync(
        [
            {
                "commandId": "f-done-2",
                "deviceId": device,
                "deviceSequence": 3,
                "baseSaveVersion": r1["save_version"],
                "type": "focus.complete",
                "payload": {},
            }
        ],
        known=r1["save_version"],
    )
    assert r2["acks"][0]["status"] == "applied"
    assert r2["projection"]["growthEnergy"] == energy
    assert r2["projection"]["pendingSpawnWindows"] == spawns


def test_unauthorized_sync():
    c = client()
    r = c.post("/v1/sync", json={"knownSaveVersion": 0, "commands": []})
    assert r.status_code == 401


def test_cookie_write_requires_matching_csrf():
    c = client()
    session = c.post("/v1/guest").json()["session_id"]
    from purrden_api.auth import new_csrf
    from purrden_api.db import SessionLocal
    from purrden_api.models import BffSession
    token = new_csrf()
    with SessionLocal() as db:
        row = db.get(BffSession, session)
        row.csrf_token = token
        db.commit()
    c.cookies.set("purrden_session", session)
    body = {"knownSaveVersion": 0, "commands": []}
    assert c.post("/v1/sync", json=body).status_code == 403
    assert c.post("/v1/sync", json=body, headers={"X-CSRF-Token": token}).status_code == 403
    assert c.post("/v1/sync", json=body, headers={"X-CSRF-Token": token, "Origin": "http://testserver"}).status_code == 200


def test_claim_genesis_and_join_second_device():
    c = client()
    # Claim a local-looking projection
    genesis = {
        "growthEnergy": 99,
        "food": 3,
        "gardenLevel": 2,
        "plantInventory": {"plant:fern:v1": 5},
        "slots": [
            {"index": 0, "plantId": "plant:fern:v1", "visitor": None},
            {"index": 1, "plantId": None, "visitor": None},
            {"index": 2, "plantId": None, "visitor": None},
            {"index": 3, "plantId": None, "visitor": None},
        ],
        "world": {"precipitation": "rain", "daylight": "dusk", "season": "autumn", "moon": "full"},
        "collection": {
            "cat:mizzle:v1": {
                "catId": "cat:mizzle:v1",
                "bond": 50,
                "stage": "kitten",
                "visitCount": 1,
            }
        },
        "deviceSequence": 4,
    }
    claim = c.post(
        "/v1/guest/claim",
        json={"deviceId": "dev-a", "projection": genesis},
    )
    assert claim.status_code == 200, claim.text
    body = claim.json()
    assert body["save_version"] == 1
    assert body["projection"]["slots"][0]["plantId"] == "plant:fern:v1"
    assert body["projection"]["growthEnergy"] == 99
    assert body["projection"]["installationSecretHex"] is None
    share = body["session_id"]

    # Second device joins
    joined = c.post(
        "/v1/session/join",
        json={"sessionId": share, "deviceId": "dev-b", "label": "laptop"},
    )
    assert joined.status_code == 200, joined.text
    j = joined.json()
    assert j["joined"] is True
    assert j["player_id"] == body["player_id"]
    assert j["session_id"] != share  # new opaque token
    assert j["projection"]["slots"][0]["plantId"] == "plant:fern:v1"

    # Devices list
    devs = c.get("/v1/devices", headers={"X-Purrden-Session": j["session_id"]})
    assert devs.status_code == 200
    ids = {d["device_id"] for d in devs.json()["devices"]}
    assert "dev-a" in ids and "dev-b" in ids

    # Sync from device B is idempotent with empty commands
    s = c.post(
        "/v1/sync",
        headers={"X-Purrden-Session": j["session_id"]},
        json={"knownSaveVersion": j["save_version"], "commands": []},
    )
    assert s.status_code == 200
    assert s.json()["save_version"] == 1


def test_visit_world_is_server_derived(monkeypatch):
    monkeypatch.setattr(
        "purrden_api.routes.visits.WorldContextService.get",
        lambda _self, _lat, _lon: {"precipitation": "rain", "geoCell": "40.00,-74.00"},
    )
    c = client()
    session = c.post("/v1/guest").json()["session_id"]
    response = c.post(
        "/v1/visits/schedule",
        headers={"X-Purrden-Session": session},
        json={"latitude": 40, "longitude": -74},
    )
    assert response.status_code == 200
    assert c.post(
        "/v1/visits/schedule",
        headers={"X-Purrden-Session": session},
        json={"latitude": 91, "longitude": -74, "precipitation": "storm"},
    ).status_code == 422


def test_production_settings_fail_closed(monkeypatch):
    from pydantic import ValidationError
    from purrden_api.config import Settings

    monkeypatch.setenv("ENV", "production")
    try:
        Settings()
        assert False, "insecure production defaults must fail"
    except ValidationError:
        pass


def test_logout_revokes_cookie_session():
    from purrden_api.auth import new_csrf
    from purrden_api.db import SessionLocal
    from purrden_api.models import BffSession

    c = client()
    session_id = c.post("/v1/guest").json()["session_id"]
    token = new_csrf()
    with SessionLocal() as db:
        db.get(BffSession, session_id).csrf_token = token
        db.commit()
    c.cookies.set("purrden_session", session_id)
    response = c.post(
        "/v1/auth/logout",
        headers={"Origin": "http://testserver", "X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert c.get("/v1/bootstrap").status_code == 401
