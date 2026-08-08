"""phase2 cloud save tables

Revision ID: 20260808_0001
Revises:
Create Date: 2026-08-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260808_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "players",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("display_name", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("is_guest", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "devices",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("player_id", sa.String(length=36), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("player_id", "device_id", name="uq_player_device"),
    )
    op.create_index("ix_devices_player_id", "devices", ["player_id"])
    op.create_index("ix_devices_device_id", "devices", ["device_id"])

    op.create_table(
        "player_saves",
        sa.Column("player_id", sa.String(length=36), sa.ForeignKey("players.id"), primary_key=True),
        sa.Column("save_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_version", sa.String(length=32), nullable=False, server_default="2026.09.0"),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("projection", sa.JSON(), nullable=False),
        sa.Column("projection_hash", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "player_commands",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("player_id", sa.String(length=36), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("command_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("device_sequence", sa.Integer(), nullable=False),
        sa.Column("base_save_version", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="applied"),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("player_id", "command_id", name="uq_player_command"),
        sa.UniqueConstraint("player_id", "device_id", "device_sequence", name="uq_player_device_seq"),
    )
    op.create_index("ix_player_commands_player_id", "player_commands", ["player_id"])

    op.create_table(
        "bff_sessions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("player_id", sa.String(length=36), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_bff_sessions_player_id", "bff_sessions", ["player_id"])


def downgrade() -> None:
    op.drop_table("bff_sessions")
    op.drop_table("player_commands")
    op.drop_table("player_saves")
    op.drop_table("devices")
    op.drop_table("players")
