"""auth and async visits

Revision ID: 20260813_0002
Revises: 20260808_0001
"""
import sqlalchemy as sa
from alembic import op

revision = "20260813_0002"
down_revision = "20260808_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("players", sa.Column("oidc_subject", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_players_oidc_subject", "players", ["oidc_subject"])
    op.add_column("bff_sessions", sa.Column("csrf_token", sa.String(64), nullable=True))
    op.create_table("spawn_schedules", sa.Column("id", sa.String(36), primary_key=True), sa.Column("player_id", sa.String(36), sa.ForeignKey("players.id"), nullable=False), sa.Column("due_at", sa.DateTime(timezone=True), nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("world", sa.JSON(), nullable=False))
    op.create_index("ix_spawn_schedules_due_at", "spawn_schedules", ["due_at"])
    op.create_index("ix_spawn_schedules_status", "spawn_schedules", ["status"])
    op.create_table("outbox_events", sa.Column("id", sa.String(36), primary_key=True), sa.Column("topic", sa.String(64), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.Column("published", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")))
    op.create_index("ix_outbox_events_published", "outbox_events", ["published"])
    op.create_table("visitor_inbox", sa.Column("id", sa.String(36), primary_key=True), sa.Column("schedule_id", sa.String(36), nullable=False), sa.Column("player_id", sa.String(36), sa.ForeignKey("players.id"), nullable=False), sa.Column("cat_id", sa.String(64), nullable=False), sa.Column("world", sa.JSON(), nullable=False), sa.Column("read", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")), sa.UniqueConstraint("schedule_id", name="uq_inbox_schedule"))


def downgrade():
    op.drop_table("visitor_inbox"); op.drop_table("outbox_events"); op.drop_table("spawn_schedules")
    op.drop_column("bff_sessions", "csrf_token"); op.drop_constraint("uq_players_oidc_subject", "players", type_="unique"); op.drop_column("players", "oidc_subject")
