from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"


def upgrade():
    op.create_table(
        "workflow_settings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("police_report", sa.String, nullable=False),
    )
    op.execute("INSERT INTO workflow_settings(id, police_report) VALUES (1, 'conditional')")


def downgrade():
    op.drop_table("workflow_settings")
