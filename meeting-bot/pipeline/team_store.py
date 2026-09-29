"""Team membership and invites — the Team plan's "invite others, share a
workspace" feature. One team per user (not a multi-workspace setup like
Slack): every user has `users.team_id`/`team_role` ('admin' or 'member'),
set/cleared here rather than through auth_store.update_user() (whose
"None means don't touch" convention can't express "clear this to NULL").

Deliberately NOT built: sub-teams, seat quotas (Team is a flat monthly fee
today, not metered per seat, so a hard cap would be enforcing a limit the
billing itself doesn't charge for), and any per-team custom roles beyond
Admin/Member. See CLAUDE.md's "Known gaps" once this is documented there.
"""

import secrets
import uuid
from datetime import datetime, timedelta

import psycopg2.extras

from . import auth_store
from .db import register_schema, with_conn

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS team_invites (
    token TEXT PRIMARY KEY,
    team_id TEXT NOT NULL,
    email TEXT,
    created_by TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP
);
"""
register_schema(_TABLE_SQL)

_INVITE_VALID_DAYS = 7


def _set_membership(user_id: str, team_id: str | None, role: str | None) -> None:
    def _do(conn):
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET team_id = %s, team_role = %s WHERE id = %s", (team_id, role, user_id))
        conn.commit()

    with_conn(_do)


def get_team(team_id: str) -> dict | None:
    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM teams WHERE id = %s", (team_id,))
            row = cur.fetchone()
        return dict(row) if row else None

    row = with_conn(_do)
    if row is None:
        return None
    row["created_at"] = row["created_at"].strftime("%Y-%m-%dT%H:%M:%S")
    return row


def list_members(team_id: str) -> list[dict]:
    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, name, email, team_role, created_at FROM users WHERE team_id = %s ORDER BY created_at", (team_id,)
            )
            return [dict(r) for r in cur.fetchall()]

    return [{**r, "created_at": r["created_at"].strftime("%Y-%m-%dT%H:%M:%S")} for r in with_conn(_do)]


def create_team(name: str, owner_id: str) -> dict:
    """Caller (app.py) already checked the owner isn't in a team yet and is
    on the Team plan."""
    team_id = uuid.uuid4().hex
    record = {"id": team_id, "name": name.strip(), "owner_id": owner_id, "created_at": datetime.now()}

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO teams (id, name, owner_id, created_at) VALUES (%(id)s, %(name)s, %(owner_id)s, %(created_at)s)",
                record,
            )
        conn.commit()

    with_conn(_do)
    _set_membership(owner_id, team_id, "admin")
    return get_team(team_id)


def rename_team(team_id: str, name: str) -> None:
    def _do(conn):
        with conn.cursor() as cur:
            cur.execute("UPDATE teams SET name = %s WHERE id = %s", (name.strip(), team_id))
        conn.commit()

    with_conn(_do)


def create_invite(team_id: str, created_by: str, email: str | None = None) -> dict:
    token = secrets.token_urlsafe(24)
    record = {
        "token": token,
        "team_id": team_id,
        "email": email.strip().lower() if email else None,
        "created_by": created_by,
        "created_at": datetime.now(),
        "expires_at": datetime.now() + timedelta(days=_INVITE_VALID_DAYS),
    }

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO team_invites (token, team_id, email, created_by, created_at, expires_at)
                VALUES (%(token)s, %(team_id)s, %(email)s, %(created_by)s, %(created_at)s, %(expires_at)s)
                """,
                record,
            )
        conn.commit()

    with_conn(_do)
    return record


def get_invite(token: str) -> dict | None:
    """None if the token doesn't exist, is expired, or was already used —
    callers don't need to distinguish which (all mean "not usable")."""

    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM team_invites WHERE token = %s AND used_at IS NULL AND expires_at > NOW()", (token,)
            )
            row = cur.fetchone()
        return dict(row) if row else None

    return with_conn(_do)


def accept_invite(token: str, user_id: str) -> dict | None:
    """Joins user_id into the invite's team as a member and marks the
    invite used. Returns the team, or None if the invite wasn't valid."""
    invite = get_invite(token)
    if invite is None:
        return None

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute("UPDATE team_invites SET used_at = %s WHERE token = %s", (datetime.now(), token))
        conn.commit()

    with_conn(_do)
    _set_membership(user_id, invite["team_id"], "member")
    return get_team(invite["team_id"])


def remove_member(user_id: str) -> None:
    """Also used for "leave team" (self-service) — same operation either
    way. If the team's now empty, delete the team row too rather than
    leaving an orphaned team nobody belongs to."""
    user = auth_store.get_user(user_id)
    team_id = user["team_id"] if user else None
    _set_membership(user_id, None, None)
    if team_id and not list_members(team_id):

        def _do(conn):
            with conn.cursor() as cur:
                cur.execute("DELETE FROM teams WHERE id = %s", (team_id,))
            conn.commit()

        with_conn(_do)


def set_role(user_id: str, team_id: str, role: str) -> None:
    _set_membership(user_id, team_id, role)
