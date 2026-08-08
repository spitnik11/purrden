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
