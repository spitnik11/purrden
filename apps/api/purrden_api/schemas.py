from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthOut(BaseModel):
    status: str
    version: str
    env: str


class GuestCreateOut(BaseModel):
    player_id: str
    session_id: str
    device_id: str
    save_version: int
    projection: dict[str, Any]
    joined: bool = False


class GuestCreateIn(BaseModel):
    """Optional body for POST /v1/guest."""

    deviceId: str | None = Field(default=None, max_length=64)
    label: str | None = Field(default=None, max_length=64)


class GuestClaimIn(BaseModel):
    """Upload sanitized local garden as one-time cloud genesis."""

    deviceId: str | None = Field(default=None, max_length=64)
    label: str | None = Field(default="claim", max_length=64)
    projection: dict[str, Any]


class SessionJoinIn(BaseModel):
    """Second device joins an existing guest cloud (share session id for alpha)."""

    sessionId: str = Field(min_length=8, max_length=64)
    deviceId: str | None = Field(default=None, max_length=64)
    label: str | None = Field(default="join", max_length=64)


class DeviceOut(BaseModel):
    device_id: str
    label: str | None = None
    created_at: str | None = None


class DeviceListOut(BaseModel):
    player_id: str
    devices: list[DeviceOut]


class SyncCommandIn(BaseModel):
    commandId: str = Field(min_length=1, max_length=64)
    deviceId: str = Field(min_length=1, max_length=64)
    deviceSequence: int = Field(ge=0)
    baseSaveVersion: int = Field(ge=0)
    type: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class SyncIn(BaseModel):
    knownSaveVersion: int = Field(ge=0)
    cursor: str | None = None
    commands: list[SyncCommandIn] = Field(default_factory=list, max_length=100)


class CommandAck(BaseModel):
    commandId: str
    status: str
    reject_reason: str | None = None


class SyncOut(BaseModel):
    save_version: int
    projection: dict[str, Any]
    acks: list[CommandAck]
    server_time: str


class BootstrapOut(BaseModel):
    player_id: str
    save_version: int
    content_version: str
    projection: dict[str, Any]
