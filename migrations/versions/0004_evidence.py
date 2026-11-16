from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"


def upgrade():
    op.create_table(
        "evidence_requests",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("claim_id", sa.String, sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "analysis_id", sa.String, sa.ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("item", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("document_id", sa.String, sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("note", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_evidence_requests_claim_id", "evidence_requests", ["claim_id"])
    active = sa.text("status IN ('OPEN','SUBMITTED')")
    op.create_index(
        "uq_active_evidence_item",
        "evidence_requests",
        ["claim_id", "item"],
        unique=True,
        postgresql_where=active,
        sqlite_where=active,
    )


def downgrade():
    op.drop_table("evidence_requests")
