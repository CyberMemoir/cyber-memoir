"""evidence observed_at"""

from alembic import op
import sqlalchemy as sa

revision = "b1c4d7e29f30"
down_revision = "aafebf866348"
branch_labels = None
depends_on = None


def upgrade():
    # Observation time of the material itself. Backfilled material and material a reviewer enters
    # months later both describe an earlier observation than created_at records. Nullable: existing
    # rows have no observation time to infer, and inventing one would be exactly the kind of guess
    # ADR 0001 clause 5 rules out.
    op.add_column("evidence", sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("evidence", "observed_at")
