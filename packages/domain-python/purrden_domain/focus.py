"""Focus-session state machine — Python port of packages/domain-ts/focus-session.mjs."""
from __future__ import annotations

import time
from typing import Any


class FocusState:
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


def _now_ms() -> int:
    return int(time.time() * 1000)


def create_focus_session(
    *,
    id: str,
    target_seconds: int,
    source: str = "focus_timer",
    now: int | None = None,
) -> dict[str, Any]:
    if not id:
        raise ValueError("id required")
    if not isinstance(target_seconds, int) or target_seconds <= 0:
        raise ValueError("target_seconds must be a positive integer")
    now = _now_ms() if now is None else now
    return {
        "id": id,
        "state": FocusState.IDLE,
        "targetSeconds": target_seconds,
        "startedAt": None,
        "runningSince": None,
        "accumulatedMs": 0,
        "completedAt": None,
        "cancelledAt": None,
        "source": source,
        "updatedAt": now,
    }


def _assert_state(session: dict, allowed: set[str], action: str) -> None:
    if session["state"] not in allowed:
        raise ValueError(f"cannot {action} from state={session['state']}")


def start_focus(session: dict, now: int | None = None) -> dict:
    now = _now_ms() if now is None else now
    _assert_state(session, {FocusState.IDLE, FocusState.PAUSED}, "start")
    next_ = dict(session)
    if next_["state"] == FocusState.IDLE:
        next_["startedAt"] = now
    next_["state"] = FocusState.RUNNING
    next_["runningSince"] = now
    next_["updatedAt"] = now
    return next_


def pause_focus(session: dict, now: int | None = None) -> dict:
    now = _now_ms() if now is None else now
    _assert_state(session, {FocusState.RUNNING}, "pause")
    next_ = dict(session)
    next_["accumulatedMs"] += now - next_["runningSince"]
    next_["runningSince"] = None
    next_["state"] = FocusState.PAUSED
    next_["updatedAt"] = now
    return next_


def cancel_focus(session: dict, now: int | None = None) -> dict:
    now = _now_ms() if now is None else now
    _assert_state(session, {FocusState.RUNNING, FocusState.PAUSED, FocusState.IDLE}, "cancel")
    next_ = dict(session)
    if next_["state"] == FocusState.RUNNING and next_["runningSince"] is not None:
        next_["accumulatedMs"] += now - next_["runningSince"]
        next_["runningSince"] = None
    next_["state"] = FocusState.CANCELLED
    next_["cancelledAt"] = now
    next_["updatedAt"] = now
    return next_


def elapsed_ms(session: dict, now: int | None = None) -> int:
    now = _now_ms() if now is None else now
    ms = session["accumulatedMs"]
    if session["state"] == FocusState.RUNNING and session["runningSince"] is not None:
        ms += now - session["runningSince"]
    return max(0, ms)


def elapsed_seconds(session: dict, now: int | None = None) -> int:
    return elapsed_ms(session, now) // 1000


def complete_focus(session: dict, now: int | None = None) -> dict:
    now = _now_ms() if now is None else now
    _assert_state(session, {FocusState.RUNNING, FocusState.PAUSED}, "complete")
    next_ = dict(session)
    if next_["state"] == FocusState.RUNNING and next_["runningSince"] is not None:
        next_["accumulatedMs"] += now - next_["runningSince"]
        next_["runningSince"] = None
        next_["state"] = FocusState.PAUSED
    elapsed = next_["accumulatedMs"] // 1000
    if elapsed < next_["targetSeconds"]:
        if session["state"] == FocusState.RUNNING:
            return dict(session)
        return next_
    next_["state"] = FocusState.COMPLETED
    next_["completedAt"] = now
    next_["updatedAt"] = now
    return next_


def growth_energy_for(session: dict) -> int:
    if session["state"] != FocusState.COMPLETED:
        return 0
    return max(1, session["targetSeconds"] // 60)
