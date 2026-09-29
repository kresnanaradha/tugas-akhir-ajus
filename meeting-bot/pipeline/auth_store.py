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
-- Deactivated accounts can't log in or use an existing session, but their
-- row stays (meetings point at users.id). NULL counts as active.
ALTER TABLE users ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE;
-- Optional contact info shown/edited on the Pengaturan page.
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT;
-- Whether app.py's _notify_meeting_ready() should email this user when a
-- meeting's summary is ready. NULL counts as TRUE (opted in by default,
-- matching the feature's original always-on behavior before this toggle
-- existed) -- see _public()'s `is not False` check below.
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_notifications BOOLEAN DEFAULT TRUE;
-- A user belongs to at most one team at a time (not a Slack-style multi-
-- workspace setup) -- see pipeline/team_store.py. NULL team_id = no team.
-- team_role is only meaningful when team_id is set: 'admin' (can invite,
-- remove members, rename the team) or 'member'.
ALTER TABLE users ADD COLUMN IF NOT EXISTS team_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS team_role TEXT;
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
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "phone": row.get("phone"),
        "role": row["role"],
        "active": row.get("active") is not False,
        "email_notifications": row.get("email_notifications") is not False,
        "team_id": row.get("team_id"),
        "team_role": row.get("team_role"),
    }


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


def list_users() -> list[dict]:
    """Every user with how many meetings they own, newest first (admin UI)."""

    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT u.*, (SELECT COUNT(*) FROM meetings m WHERE m.user_id = u.id) AS meeting_count "
                "FROM users u ORDER BY u.created_at DESC"
            )
            return [dict(r) for r in cur.fetchall()]

    return [
        {**_public(r), "meeting_count": r["meeting_count"], "created_at": r["created_at"].strftime("%Y-%m-%dT%H:%M:%S")}
        for r in with_conn(_do)
    ]


def update_user(
    user_id: str,
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    role: str | None = None,
    active: bool | None = None,
    email_notifications: bool | None = None,
) -> dict | None:
    """Raises psycopg2.errors.UniqueViolation (via with_conn) if `email` is
    already taken by another account — same as create_user()."""
    if email is not None:
        email = email.strip().lower()
    fields = {
        k: v
        for k, v in (
            ("name", name),
            ("email", email),
            ("phone", phone),
            ("role", role),
            ("active", active),
            ("email_notifications", email_notifications),
        )
        if v is not None
    }
    if fields:

        def _do(conn):
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE users SET {', '.join(f'{c} = %s' for c in fields)} WHERE id = %s", (*fields.values(), user_id)
                )
            conn.commit()

        with_conn(_do)
    return get_user(user_id)


def set_password(user_id: str, password: str) -> None:
    def _do(conn):
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (generate_password_hash(password), user_id))
        conn.commit()

    with_conn(_do)


def is_active(user_id: str) -> bool:
    user = get_user(user_id)
    return bool(user and user["active"])


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
