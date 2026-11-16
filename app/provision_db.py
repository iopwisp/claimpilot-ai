"""Run after migrations as the database owner, before starting the API and worker."""

from pathlib import Path
from psycopg import sql
from .db import engine


def main():
    password = Path("/run/runtime/password").read_text().strip()
    with engine.begin() as connection:
        cursor = connection.connection.driver_connection.cursor()
        with cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(140785260)")
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname='claimpilot_app'")
            verb = "ALTER" if cursor.fetchone() else "CREATE"
            cursor.execute(
                sql.SQL(
                    verb
                    + " ROLE claimpilot_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}"
                ).format(sql.Literal(password))
            )
            cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            cursor.execute("GRANT USAGE ON SCHEMA public TO claimpilot_app")
            cursor.execute(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO claimpilot_app"
            )
            cursor.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO claimpilot_app")
            cursor.execute("REVOKE UPDATE, DELETE ON audit_logs FROM claimpilot_app")
            cursor.execute("REVOKE ALL ON alembic_version FROM claimpilot_app")


if __name__ == "__main__":
    main()
