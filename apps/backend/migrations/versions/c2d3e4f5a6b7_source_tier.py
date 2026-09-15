"""Reviewer-supplied facts about a source: its authority tier, and platform metadata.

Evidence.kind is the extraction method (asr/ocr/subtitle). The rubric's A-D tiers
are about the authority of the source itself, which nothing recorded. NULL means
no reviewer has judged it yet.
"""

import sqlalchemy as sa
from alembic import op

revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sources", sa.Column("source_tier", sa.String(length=1), nullable=True))
    op.add_column("sources", sa.Column("source_tier_reason", sa.Text(), nullable=True))
    op.add_column("sources", sa.Column("metadata_note", sa.Text(), nullable=True))
    op.create_check_constraint(
        "source_tier_range", "sources", "source_tier IS NULL OR source_tier IN ('A','B','C','D')"
    )


def downgrade():
    op.drop_constraint("source_tier_range", "sources", type_="check")
    op.drop_column("sources", "metadata_note")
    op.drop_column("sources", "source_tier_reason")
    op.drop_column("sources", "source_tier")
