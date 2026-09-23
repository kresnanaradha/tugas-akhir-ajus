import uuid
from datetime import datetime

import psycopg2.extras
from werkzeug.security import check_password_hash, generate_password_hash

from .db import register_schema, with_conn

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMP NOT NULL
);
"""
register_schema(_TABLE_SQL)

# Just these two for now — 'user' covers both individual and team usage
# (there's no separate "team member" role yet, since real team membership
# isn't built either, see CLAUDE.md). 'super_admin' is for the internal ops
# dashboard (cost/revenue/storage metrics, exportable reports) — a distinct
# concept from a team's own admin, which doesn't exist yet.
ROLES = ("user", "super_admin")


def _public(row: dict) -> dict:
    """Strips password_hash before a user record ever leaves this module —
    every caller (session endpoints, super-admin user list once that
    exists) gets this, never the raw row."""
    return {"id": row["id"], "email": row["email"], "name": row["name"], "role": row["role"]}


def create_user(email: str, password: str, name: str, role: str = "user") -> dict:
    """Raises psycopg2.errors.UniqueViolation (via with_conn) if the email's
    already taken — caller (app.py's /auth/register) turns that into a 409."""
    user_id = uuid.uuid4().hex
    record = {
        "id": user_id,
        "email": email.strip().lower(),
        "password_hash": generate_password_hash(password),
        "name": name.strip(),
        "role": role,
        "created_at": datetime.now(),
    }

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (id, email, password_hash, name, role, created_at)
                VALUES (%(id)s, %(email)s, %(password_hash)s, %(name)s, %(role)s, %(created_at)s)
                """,
                record,
            )
        conn.commit()

    with_conn(_do)
    return _public(record)


def get_user(user_id: str) -> dict | None:
    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
        return dict(row) if row else None

    row = with_conn(_do)
    return _public(row) if row else None


def count_users() -> int:
    def _do(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            return cur.fetchone()[0]

    return with_conn(_do)


def verify_login(email: str, password: str) -> dict | None:
    """Returns the public user record if email+password match, else None —
    deliberately one function (not get-then-check separately) so a caller
    can't accidentally branch on "user exists" vs "password wrong" and leak
    which emails are registered."""

    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (email.strip().lower(),))
            row = cur.fetchone()
        return dict(row) if row else None

    row = with_conn(_do)
    if row is None or not check_password_hash(row["password_hash"], password):
        return None
    return _public(row)
