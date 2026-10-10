"""Persistent receipts for atomic, review-only publication imports."""

import sqlalchemy as sa
from alembic import op

revision = "e4f5a6b7c8d9"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "import_records",
        sa.Column("fingerprint", sa.String(64), primary_key=True),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey("revisions.id"), nullable=False),
        sa.Column("artifact_key", sa.Text(), nullable=False),
        sa.Column("imported_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bindings", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("import_records")
