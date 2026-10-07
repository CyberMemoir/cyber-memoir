"""Append-only source observations; no retrospective counter backfill."""

import sqlalchemy as sa
from alembic import op

revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("artifact_key", sa.Text(), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.CheckConstraint("status IN ('observed','fetch_failed','rate_limited')", name="observation_status"),
    )
    op.create_index("ix_source_observations_source_time", "source_observations", ["source_id", "observed_at"])


def downgrade():
    op.drop_index("ix_source_observations_source_time", table_name="source_observations")
    op.drop_table("source_observations")
