"""Command ledger + projection application."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Device, Player, PlayerCommand, PlayerSave
from ..projection import CommandError, apply_server_command


def get_player_save(db: Session, player_id: str) -> tuple[Player, PlayerSave]:
    player = db.get(Player, player_id)
    if not player:
        raise LookupError("player_not_found")
    save = db.get(PlayerSave, player_id)
    if not save:
        raise LookupError("save_not_found")
    return player, save


def apply_sync(
    db: Session,
    *,
    player_id: str,
    known_save_version: int,
    commands: list[dict[str, Any]],
) -> dict[str, Any]:
    player, save = get_player_save(db, player_id)
    acks: list[dict[str, Any]] = []
    projection = dict(save.projection or {})

    # Soft conflict signal: client behind/ahead is OK for append-only commands;
    # we still apply idempotently by command_id / device_sequence.
    for raw in commands:
        command_id = raw["commandId"]
        device_id = raw["deviceId"]
        device_sequence = int(raw["deviceSequence"])
        cmd_type = raw["type"]
        payload = raw.get("payload") or {}

        # Ensure device is known
        existing_dev = db.scalar(
            select(Device).where(
                Device.player_id == player_id, Device.device_id == device_id
            )
        )
        if not existing_dev:
            db.add(Device(player_id=player_id, device_id=device_id, label="sync"))

        # Idempotency: same command_id
        prior = db.scalar(
            select(PlayerCommand).where(
                PlayerCommand.player_id == player_id,
                PlayerCommand.command_id == command_id,
            )
        )
        if prior:
            acks.append(
                {
                    "commandId": command_id,
                    "status": "dup",
                    "reject_reason": None,
                }
            )
            continue

        # Idempotency: same device sequence
        prior_seq = db.scalar(
            select(PlayerCommand).where(
                PlayerCommand.player_id == player_id,
                PlayerCommand.device_id == device_id,
                PlayerCommand.device_sequence == device_sequence,
            )
        )
        if prior_seq:
            acks.append(
                {
                    "commandId": command_id,
                    "status": "dup",
                    "reject_reason": "device_sequence",
                }
            )
            continue

        try:
            projection = apply_server_command(projection, cmd_type, payload)
            status = "applied"
            reject = None
            save.save_version = int(save.save_version) + 1
            projection["saveVersion"] = save.save_version
            projection["deviceSequence"] = max(
                int(projection.get("deviceSequence") or 0), device_sequence
            )
            save.projection = projection
        except CommandError as e:
            status = "rejected"
            reject = e.reason

        db.add(
            PlayerCommand(
                player_id=player_id,
                command_id=command_id,
                device_id=device_id,
                device_sequence=device_sequence,
                base_save_version=int(raw.get("baseSaveVersion") or known_save_version),
                type=cmd_type,
                payload=payload,
                status=status,
                reject_reason=reject,
            )
        )
        acks.append(
            {"commandId": command_id, "status": status, "reject_reason": reject}
        )

    db.add(save)
    db.commit()
    db.refresh(save)

    return {
        "save_version": save.save_version,
        "projection": save.projection,
        "acks": acks,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "known_save_version_echo": known_save_version,
        "player_id": player.id,
    }
