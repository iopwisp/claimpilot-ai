from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"


def upgrade():
    op.create_table(
        "inconsistencies",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column(
            "analysis_id", sa.String, sa.ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("severity", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("evidence", sa.JSON, nullable=False),
        sa.Column("review_status", sa.String, nullable=False),
    )
    op.create_index("ix_inconsistencies_analysis_id", "inconsistencies", ["analysis_id"])


def downgrade():
    op.drop_table("inconsistencies")
