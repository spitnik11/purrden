"""One-time guest genesis import — local browser projection is untrusted input."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from ..models import BffSession, Device, Player, PlayerSave
from ..auth import new_csrf, session_expired
from ..projection import CONTENT_VERSION, PLANT_COSTS, empty_projection


class ClaimError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _clamp_int(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def sanitize_genesis(
    raw: dict[str, Any] | None,
    *,
    device_id: str,
) -> dict[str, Any]:
    """
    Validate/clamp a browser projection into a server-safe genesis snapshot.
    Never trusts currency/rare cats blindly — clamps extremes and drops secrets.
    """
    base = empty_projection(device_id=device_id)
    if not raw or not isinstance(raw, dict):
        return base

    proj = deepcopy(base)
    proj["deviceId"] = device_id
    proj["localSaveId"] = str(raw.get("localSaveId") or proj["localSaveId"])
    proj["contentVersion"] = str(raw.get("contentVersion") or CONTENT_VERSION)
    proj["schemaVersion"] = 1
    # Genesis starts at 0; claim bumps to 1 when stored
    proj["saveVersion"] = 0
    proj["deviceSequence"] = _clamp_int(raw.get("deviceSequence"), 0, 1_000_000, 0)
    proj["installationSecretHex"] = None  # never store client spawn secret as authority

    # Soft caps — portfolio alpha, not anti-cheat perfection
    proj["growthEnergy"] = _clamp_int(raw.get("growthEnergy"), 0, 500, 5)
    proj["food"] = _clamp_int(raw.get("food"), 0, 200, 5)
    proj["gardenLevel"] = _clamp_int(raw.get("gardenLevel"), 0, 20, 2)
    proj["streakDays"] = _clamp_int(raw.get("streakDays"), 0, 365, 0)
    proj["pendingSpawnWindows"] = _clamp_int(raw.get("pendingSpawnWindows"), 0, 20, 0)
    proj["clockOffsetMs"] = 0  # never import fake clock offset

    world = raw.get("world") if isinstance(raw.get("world"), dict) else {}
    allowed_precip = {"none", "drizzle", "rain", "storm"}
    allowed_light = {"dawn", "day", "dusk", "night"}
    allowed_season = {"spring", "summer", "autumn", "winter"}
    allowed_moon = {
        "new",
        "waxing_crescent",
        "first_quarter",
        "waxing_gibbous",
        "full",
        "waning_gibbous",
        "last_quarter",
        "waning_crescent",
    }
    proj["world"] = {
        "precipitation": world.get("precipitation")
        if world.get("precipitation") in allowed_precip
        else "none",
        "daylight": world.get("daylight")
        if world.get("daylight") in allowed_light
        else "day",
        "season": world.get("season")
        if world.get("season") in allowed_season
        else "summer",
        "moon": world.get("moon") if world.get("moon") in allowed_moon else "new",
    }

    inv_in = raw.get("plantInventory") if isinstance(raw.get("plantInventory"), dict) else {}
    inv: dict[str, int] = {}
    for pid in PLANT_COSTS:
        inv[pid] = _clamp_int(inv_in.get(pid), 0, 50, inv.get(pid, 0) or 0)
    # defaults if empty
    if sum(inv.values()) == 0:
        inv = dict(base["plantInventory"])
    proj["plantInventory"] = inv

    slots_in = raw.get("slots") if isinstance(raw.get("slots"), list) else []
    slots = []
    for i in range(4):
        src = slots_in[i] if i < len(slots_in) and isinstance(slots_in[i], dict) else {}
        plant_id = src.get("plantId")
        if plant_id not in PLANT_COSTS:
            plant_id = None
        visitor = None
        v = src.get("visitor")
        if isinstance(v, dict) and isinstance(v.get("catId"), str):
            cat_id = v["catId"]
            # only allow known cat id pattern
            if cat_id.startswith("cat:") and len(cat_id) < 64:
                visitor = {
                    "visitId": str(v.get("visitId") or uuid4()),
                    "catId": cat_id,
                    "slotIndex": i,
                    "stage": str(v.get("stage") or "kitten")[:32],
                    "bond": _clamp_int(v.get("bond"), 0, 10_000, 0),
                    "collected": False,
                    "explanation": list(v.get("explanation") or [])[:5]
                    if isinstance(v.get("explanation"), list)
                    else [],
                    "spawnWindowId": str(v.get("spawnWindowId") or f"genesis-{i}")[:64],
                    "arrivedAt": _clamp_int(v.get("arrivedAt"), 0, 10**13, 0),
                }
        slots.append({"index": i, "plantId": plant_id, "visitor": visitor})
    proj["slots"] = slots

    coll_in = raw.get("collection") if isinstance(raw.get("collection"), dict) else {}
    coll: dict[str, Any] = {}
    for cat_id, entry in list(coll_in.items())[:32]:
        if not isinstance(cat_id, str) or not cat_id.startswith("cat:"):
            continue
        if not isinstance(entry, dict):
            continue
        coll[cat_id] = {
            "catId": cat_id,
            "discoveredAt": _clamp_int(entry.get("discoveredAt"), 0, 10**13, 0),
            "bond": _clamp_int(entry.get("bond"), 0, 10_000, 0),
            "stage": str(entry.get("stage") or "kitten")[:32],
            "fullyEvolved": bool(entry.get("fullyEvolved")),
            "visitCount": _clamp_int(entry.get("visitCount"), 0, 10_000, 0),
        }
    proj["collection"] = coll

    pity_in = raw.get("pity") if isinstance(raw.get("pity"), dict) else {}
    proj["pity"] = {
        tier: _clamp_int(pity_in.get(tier), 0, 100, 0)
        for tier in ("common", "uncommon", "rare", "legendary")
    }

    recent = raw.get("recentCats") if isinstance(raw.get("recentCats"), list) else []
    proj["recentCats"] = [
        c for c in recent if isinstance(c, str) and c.startswith("cat:")
    ][:8]

    # Never import active focus mid-flight from another device
    proj["activeFocusId"] = None
    proj.pop("_focus", None)

    return proj


def create_guest_player(
    db: Session,
    *,
    device_id: str | None = None,
    label: str = "initial",
    projection: dict[str, Any] | None = None,
    display_name: str = "Guest",
) -> dict[str, Any]:
    device_id = device_id or str(uuid4())
    player = Player(is_guest=1, display_name=display_name)
    db.add(player)
    db.flush()

    if projection is None:
        proj = empty_projection(device_id=device_id)
        save_version = 0
    else:
        proj = sanitize_genesis(projection, device_id=device_id)
        save_version = 1  # claimed genesis counts as v1
        proj["saveVersion"] = 1

    save = PlayerSave(
        player_id=player.id,
        save_version=save_version,
        projection=proj,
        content_version=str(proj.get("contentVersion") or CONTENT_VERSION),
        schema_version=1,
    )
    db.add(save)
    db.add(Device(player_id=player.id, device_id=device_id, label=label))
    session = BffSession(player_id=player.id, csrf_token=new_csrf(), expires_at=datetime.now(timezone.utc) + timedelta(days=30))
    db.add(session)
    db.commit()

    return {
        "player_id": player.id,
        "session_id": session.id,
        "device_id": device_id,
        "save_version": save_version,
        "projection": proj,
    }


def join_session(
    db: Session,
    *,
    session_id: str,
    device_id: str | None = None,
    label: str = "device",
) -> dict[str, Any]:
    """Second browser joins an existing guest session (share session id for alpha)."""
    sess = db.get(BffSession, session_id)
    if not sess or sess.revoked or session_expired(sess.expires_at):
        raise ClaimError("invalid_session")
    player = db.get(Player, sess.player_id)
    save = db.get(PlayerSave, sess.player_id)
    if not player or not save or not player.is_guest:
        raise ClaimError("player_not_found")

    device_id = device_id or str(uuid4())
    from sqlalchemy import select

    existing = db.scalar(
        select(Device).where(
            Device.player_id == player.id, Device.device_id == device_id
        )
    )
    if not existing:
        db.add(Device(player_id=player.id, device_id=device_id, label=label))
        db.commit()

    # New opaque session token for this browser (same player)
    new_sess = BffSession(player_id=player.id, csrf_token=new_csrf(), expires_at=datetime.now(timezone.utc) + timedelta(days=30))
    db.add(new_sess)
    db.commit()
    db.refresh(save)

    return {
        "player_id": player.id,
        "session_id": new_sess.id,
        "device_id": device_id,
        "save_version": save.save_version,
        "projection": save.projection or {},
        "joined": True,
    }


def list_devices(db: Session, player_id: str) -> list[dict[str, Any]]:
    from sqlalchemy import select

    rows = db.scalars(select(Device).where(Device.player_id == player_id)).all()
    return [
        {
            "device_id": r.device_id,
            "label": r.label,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
