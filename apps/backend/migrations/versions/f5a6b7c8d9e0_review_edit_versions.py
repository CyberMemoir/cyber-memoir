"""Monotonic draft versions for conditional editing and exact-snapshot decisions."""

import sqlalchemy as sa
from alembic import op

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("revisions", sa.Column("edit_version", sa.Integer(), nullable=False, server_default="1"))
    op.create_check_constraint("revision_edit_version_positive", "revisions", "edit_version >= 1")


def downgrade():
    op.drop_constraint("revision_edit_version_positive", "revisions", type_="check")
    op.drop_column("revisions", "edit_version")
