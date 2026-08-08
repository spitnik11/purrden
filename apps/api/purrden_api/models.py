"""SQLAlchemy models — normalized invariants + JSONB/JSON projection.

Phase 2 focuses on cloud save authority. Async visits / outbox arrive in Phase 3.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .db import Base

# SQLite-friendly JSON; Postgres uses JSONB via dialect when available.
JsonType = JSON().with_variant(JSONB(), "postgresql")


def _uuid() -> str:
    return str(uuid4())


class Player(Base):
    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_guest: Mapped[int] = mapped_column(Integer, default=1)  # 1=guest, 0=claimed account

    devices: Mapped[list[Device]] = relationship(back_populates="player")
    save: Mapped[PlayerSave | None] = relationship(back_populates="player", uselist=False)
    commands: Mapped[list[PlayerCommand]] = relationship(back_populates="player")


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("player_id", "device_id", name="uq_player_device"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), index=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    player: Mapped[Player] = relationship(back_populates="devices")


class PlayerSave(Base):
    __tablename__ = "player_saves"

    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), primary_key=True)
    save_version: Mapped[int] = mapped_column(Integer, default=0)
    content_version: Mapped[str] = mapped_column(String(32), default="2026.09.0")
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    # Fast bootstrap projection (same shape as browser GameProjection subset)
    projection: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    projection_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    player: Mapped[Player] = relationship(back_populates="save")


class PlayerCommand(Base):
    __tablename__ = "player_commands"
    __table_args__ = (
        UniqueConstraint("player_id", "command_id", name="uq_player_command"),
        UniqueConstraint(
            "player_id", "device_id", "device_sequence", name="uq_player_device_seq"
        ),
    )

    # String PK avoids SQLite autoincrement quirks; Postgres is fine either way.
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), index=True)
    command_id: Mapped[str] = mapped_column(String(64))
    device_id: Mapped[str] = mapped_column(String(64))
    device_sequence: Mapped[int] = mapped_column(Integer)
    base_save_version: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="applied")  # applied|rejected|dup
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    player: Mapped[Player] = relationship(back_populates="commands")


class BffSession(Base):
    """Opaque server-side session. Phase 2 alpha: guest sessions only (no Keycloak yet)."""

    __tablename__ = "bff_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[int] = mapped_column(Integer, default=0)
