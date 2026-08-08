"""Server-side projection helpers (authoritative after sign-in / guest cloud claim)."""
from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4


CONTENT_VERSION = "2026.09.0"


def empty_projection(*, local_save_id: str | None = None, device_id: str | None = None) -> dict[str, Any]:
    """Mirror of browser createNewProjection — kept intentionally parallel for Phase 2."""
    return {
        "schemaVersion": 1,
        "contentVersion": CONTENT_VERSION,
        "saveVersion": 0,
        "localSaveId": local_save_id or str(uuid4()),
        "deviceId": device_id or str(uuid4()),
        "deviceSequence": 0,
        "installationSecretHex": None,  # server does not trust client spawn secrets
        "growthEnergy": 5,
        "gardenLevel": 2,
        "slots": [
            {"index": i, "plantId": None, "visitor": None} for i in range(4)
        ],
        "plantInventory": {
            "plant:fern:v1": 2,
            "plant:pond:v1": 1,
            "plant:sunny_rock:v1": 1,
            "plant:flower:v1": 3,
        },
        "food": 5,
        "collection": {},
        "pity": {"common": 0, "uncommon": 0, "rare": 0, "legendary": 0},
        "recentCats": [],
        "cooldownCats": [],
        "world": {
            "precipitation": "none",
            "daylight": "day",
            "season": "summer",
            "moon": "new",
        },
        "clockOffsetMs": 0,
        "streakDays": 0,
        "lastFocusCompletedDay": None,
        "activeFocusId": None,
        "pendingSpawnWindows": 0,
        "lastSpawnAt": None,
    }


# Commands the server will re-validate in Phase 2 alpha.
# Spawn remains client-optimistic until Phase 3 world workers; server accepts
# garden/focus/world.set but re-checks invariants.
ALLOWED_COMMANDS = {
    "focus.start",
    "focus.pause",
    "focus.resume",
    "focus.complete",
    "focus.cancel",
    "garden.plant_place",
    "garden.plant_remove",
    "garden.collect_visitor",
    "garden.feed_visitor",
    "world.set",
    "world.advance_spawn",
}

PLANT_COSTS = {
    "plant:fern:v1": 2,
    "plant:pond:v1": 3,
    "plant:sunny_rock:v1": 2,
    "plant:flower:v1": 1,
}


class CommandError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def apply_server_command(projection: dict[str, Any], cmd_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Authoritative subset of browser applyCommand. Raises CommandError on reject."""
    proj = deepcopy(projection)
    t = cmd_type

    if t not in ALLOWED_COMMANDS:
        raise CommandError(f"unknown_command:{t}")

    if t == "focus.start":
        if proj.get("activeFocusId"):
            raise CommandError("focus_already_active")
        seconds = payload.get("seconds")
        minutes = float(payload.get("minutes", 25))
        target = int(seconds) if seconds is not None else max(1, int(minutes * 60))
        focus_id = str(uuid4())
        proj["activeFocusId"] = focus_id
        # Server stores minimal focus fields on projection for bootstrap
        proj["_focus"] = {
            "id": focus_id,
            "state": "running",
            "targetSeconds": target,
            "rewarded": False,
        }
        return proj

    if t in {"focus.pause", "focus.resume", "focus.cancel"}:
        if not proj.get("activeFocusId") and t != "focus.cancel":
            raise CommandError("no_active_focus")
        if t == "focus.cancel":
            proj["activeFocusId"] = None
            if proj.get("_focus"):
                proj["_focus"]["state"] = "cancelled"
        elif t == "focus.pause" and proj.get("_focus"):
            proj["_focus"]["state"] = "paused"
        elif t == "focus.resume" and proj.get("_focus"):
            proj["_focus"]["state"] = "running"
        return proj

    if t == "focus.complete":
        focus = proj.get("_focus") or {}
        if focus.get("rewarded") or focus.get("state") == "completed":
            proj["activeFocusId"] = None
            return proj  # idempotent
        if not proj.get("activeFocusId") and focus.get("state") not in {"running", "paused"}:
            raise CommandError("no_active_focus")
        # Trust client completion for alpha; full timestamp verification is Phase 2 polish
        energy = max(1, int((focus.get("targetSeconds") or 60) // 60))
        proj["growthEnergy"] = int(proj.get("growthEnergy", 0)) + energy
        proj["pendingSpawnWindows"] = int(proj.get("pendingSpawnWindows", 0)) + 1
        if not proj.get("lastFocusCompletedDay"):
            proj["streakDays"] = max(1, int(proj.get("streakDays", 0)))
        if focus:
            focus["rewarded"] = True
            focus["state"] = "completed"
            proj["_focus"] = focus
        proj["activeFocusId"] = None
        return proj

    if t == "garden.plant_place":
        slot_index = int(payload["slotIndex"])
        plant_id = str(payload["plantId"])
        if plant_id not in PLANT_COSTS:
            raise CommandError("unknown_plant")
        slots = proj.setdefault("slots", [])
        if slot_index < 0 or slot_index >= len(slots):
            raise CommandError("bad_slot")
        slot = slots[slot_index]
        if slot.get("plantId"):
            raise CommandError("slot_occupied")
        if slot.get("visitor"):
            raise CommandError("visitor_present")
        inv = proj.setdefault("plantInventory", {})
        owned = int(inv.get(plant_id, 0))
        cost = PLANT_COSTS[plant_id]
        if owned >= 1:
            inv[plant_id] = owned - 1
        elif int(proj.get("growthEnergy", 0)) >= cost:
            proj["growthEnergy"] = int(proj["growthEnergy"]) - cost
        else:
            raise CommandError("insufficient_resources")
        slot["plantId"] = plant_id
        return proj

    if t == "garden.plant_remove":
        slot_index = int(payload["slotIndex"])
        slots = proj.setdefault("slots", [])
        slot = slots[slot_index]
        if not slot.get("plantId"):
            raise CommandError("no_plant")
        if slot.get("visitor"):
            raise CommandError("visitor_present")
        pid = slot["plantId"]
        slot["plantId"] = None
        inv = proj.setdefault("plantInventory", {})
        inv[pid] = int(inv.get(pid, 0)) + 1
        return proj

    if t == "garden.feed_visitor":
        slot_index = int(payload["slotIndex"])
        slot = proj["slots"][slot_index]
        visitor = slot.get("visitor")
        if not visitor:
            raise CommandError("no_visitor")
        if int(proj.get("food", 0)) < 1:
            raise CommandError("no_food")
        proj["food"] = int(proj["food"]) - 1
        visitor["bond"] = int(visitor.get("bond", 0)) + 50
        cat_id = visitor["catId"]
        coll = proj.setdefault("collection", {})
        entry = coll.get(cat_id) or {
            "catId": cat_id,
            "bond": 0,
            "stage": visitor.get("stage", "kitten"),
            "fullyEvolved": False,
            "visitCount": 0,
        }
        entry["bond"] = max(int(entry.get("bond", 0)), visitor["bond"])
        coll[cat_id] = entry
        slot["visitor"] = visitor
        return proj

    if t == "garden.collect_visitor":
        slot_index = int(payload["slotIndex"])
        slot = proj["slots"][slot_index]
        visitor = slot.get("visitor")
        if not visitor:
            raise CommandError("no_visitor")
        cat_id = visitor["catId"]
        coll = proj.setdefault("collection", {})
        entry = coll.get(cat_id) or {
            "catId": cat_id,
            "bond": 0,
            "stage": visitor.get("stage", "kitten"),
            "fullyEvolved": False,
            "visitCount": 0,
        }
        entry["visitCount"] = int(entry.get("visitCount", 0)) + 1
        coll[cat_id] = entry
        proj["food"] = int(proj.get("food", 0)) + 1
        slot["visitor"] = None
        return proj

    if t == "world.set":
        world = payload.get("world") or {}
        proj["world"] = {**proj.get("world", {}), **world}
        return proj

    if t == "world.advance_spawn":
        # Phase 2 alpha: accept client-provided visitor payload if present;
        # otherwise mark a pending window consumed without inventing a cat
        # (Phase 3 runs authoritative spawn on workers).
        windows = int(proj.get("pendingSpawnWindows", 0))
        force = bool(payload.get("force"))
        if windows < 1 and not force:
            raise CommandError("no_spawn_window")
        if windows >= 1:
            proj["pendingSpawnWindows"] = windows - 1
        visitor = payload.get("visitor")
        if visitor and isinstance(visitor, dict):
            slots = proj.get("slots", [])
            free = next((s for s in slots if not s.get("visitor")), None)
            if free is None:
                raise CommandError("no_free_slot")
            free["visitor"] = visitor
        return proj

    raise CommandError(f"unhandled:{t}")
