from pathlib import Path
from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    sql = Path(__file__).with_name("initial.sql").read_text()
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    for table in (
        "policy_chunks",
        "extracted_fields",
        "analyses",
        "documents",
        "claims",
        "sessions",
        "audit_logs",
        "users",
    ):
        op.drop_table(table)
