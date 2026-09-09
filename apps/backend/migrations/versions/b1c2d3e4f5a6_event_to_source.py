"""Let an Event name the Source it is about.

An Event carried a date and a description but no structured link, so a derivative
video's identity survived only as free text. Nullable: many events have no single
source behind them.
"""

import sqlalchemy as sa
from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "aafebf866348"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("events", sa.Column("to_source_id", sa.String(length=36), nullable=True))
    op.create_index("ix_events_to_source_id", "events", ["to_source_id"])
    op.create_foreign_key("fk_events_to_source_id", "events", "sources", ["to_source_id"], ["id"])


def downgrade():
    op.drop_constraint("fk_events_to_source_id", "events", type_="foreignkey")
    op.drop_index("ix_events_to_source_id", table_name="events")
    op.drop_column("events", "to_source_id")
