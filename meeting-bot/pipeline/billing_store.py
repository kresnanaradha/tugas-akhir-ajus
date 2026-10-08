from datetime import datetime, timedelta

import psycopg2.extras

from .db import register_schema, with_conn

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    plan TEXT NOT NULL,
    status TEXT NOT NULL,
    xendit_session_id TEXT,
    xendit_plan_id TEXT,
    current_period_end TIMESTAMP,
    updated_at TIMESTAMP NOT NULL
);
-- "Turunkan ke Free" doesn't cancel immediately — it stops future billing
-- right away (the Xendit recurring plan gets deactivated) but the user
-- keeps the paid plan until current_period_end, like most SaaS billing.
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE;
"""
register_schema(_TABLE_SQL)

# Fallback account id for a caller that doesn't pass its own (kept mainly so
# every function below still works if ever called without a real user id —
# app.py's routes always pass session["user_id"] now that auth exists).
DEFAULT_ACCOUNT_ID = "default"

# What each plan actually allows — matches the bullet points shown on the
# frontend's Pengaturan page ("5 rapat direkam / bulan" for Free, "Rapat
# direkam tanpa batas" for Pro/Team). None = no cap. Enforced in app.py's
# _check_meeting_quota()/_join(); a plan not in this dict (shouldn't happen)
# falls back to Free's limits, the safe default.
PLAN_LIMITS = {
    "free": {"meetings_per_month": 5, "max_duration_minutes": None, "minutes_per_week": 60},
    "pro": {"meetings_per_month": None, "max_duration_minutes": None, "minutes_per_week": None},
    "team": {"meetings_per_month": None, "max_duration_minutes": None, "minutes_per_week": None},
}

# In IDR — matches the pricing shown on the frontend's Pengaturan page. Free
# has no checkout at all (nothing to charge). Lives here (not app.py) so
# admin_stats.py's MRR calculation can share it instead of duplicating it.
PLAN_PRICES = {"pro": 99_000, "team": 299_000}


def count_active_by_plan() -> dict:
    """{"pro": N, "team": N, ...} — active subscription counts per plan,
    for the super admin dashboard's MRR figure. Mirrors get_subscription()'s
    lazy cancel-at-period-end check (a row whose period has already lapsed
    doesn't count as active even if its `status` column hasn't been updated
    yet — nothing flips that column on its own, see get_subscription())."""

    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT plan, COUNT(*) AS n FROM subscriptions
                WHERE status = 'active' AND (NOT cancel_at_period_end OR current_period_end > NOW())
                GROUP BY plan
                """
            )
            return cur.fetchall()

    rows = with_conn(_do)
    return {row["plan"]: row["n"] for row in rows}


def _apply_effective_state(row: dict) -> None:
    """What the plan really is right now: a scheduled cancellation takes effect
    once the paid period is over (computed on read, no cron job), and an unpaid
    checkout ('pending') gets no paid entitlements yet."""
    period_end = row.get("current_period_end")
    if row["cancel_at_period_end"] and period_end and period_end < datetime.now():
        row["plan"] = "free"
        row["status"] = "canceled"
    if row["status"] == "pending":
        row["plan"] = "free"


def get_subscription(account_id: str = DEFAULT_ACCOUNT_ID) -> dict:
    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM subscriptions WHERE id = %s", (account_id,))
            row = cur.fetchone()
        return dict(row) if row else None

    row = with_conn(_do)
    if row is None:
        # No row yet = never subscribed to anything paid — Free, not an error.
        return {"id": account_id, "plan": "free", "status": "active", "current_period_end": None, "cancel_at_period_end": False}
    _apply_effective_state(row)
    period_end = row.get("current_period_end")
    if period_end:
        row["current_period_end"] = period_end.strftime("%Y-%m-%dT%H:%M:%S")
    return row


def team_plans(user_id: str | None = None) -> dict[str, str]:
    """{user_id: plan} for users whose team's owner has a live paid plan -- team
    members share the owner's plan. One query; pass user_id for just one user."""

    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT u.id AS user_id, s.plan, s.status, s.cancel_at_period_end, s.current_period_end
                FROM users u JOIN teams t ON t.id = u.team_id JOIN subscriptions s ON s.id = t.owner_id
                WHERE %s::text IS NULL OR u.id = %s
                """,
                (user_id, user_id),
            )
            return [dict(r) for r in cur.fetchall()]

    rows = with_conn(_do)
    out = {}
    for r in rows:
        _apply_effective_state(r)
        if r["plan"] == "team":
            out[r["user_id"]] = "team"
    return out


def effective_plan(user_id: str) -> tuple[str, bool]:
    """(plan, inherited_from_team): the user's own paid plan, else the Team plan
    shared by their team's owner."""
    own = get_subscription(user_id)["plan"]
    if own != "free":
        return own, False
    return ("team", True) if user_id in team_plans(user_id) else ("free", False)


def plans_by_user() -> dict[str, str]:
    """{user_id: effective plan} for every user with a subscription row, in one
    query -- users without a row are Free."""

    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, plan, status, cancel_at_period_end, current_period_end FROM subscriptions")
            return [dict(r) for r in cur.fetchall()]

    rows = with_conn(_do)
    for r in rows:
        _apply_effective_state(r)
    return {r["id"]: r["plan"] for r in rows}


def start_checkout(plan: str, session_id: str, account_id: str = DEFAULT_ACCOUNT_ID) -> None:
    """Records that a checkout session was started for `plan` — status stays
    'pending' until the payment_session.completed webhook confirms the user
    actually linked a payment method and Xendit created the recurring plan."""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO subscriptions (id, plan, status, xendit_session_id, updated_at)
                VALUES (%s, %s, 'pending', %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    plan = EXCLUDED.plan, status = 'pending', cancel_at_period_end = FALSE,
                    xendit_session_id = EXCLUDED.xendit_session_id, updated_at = EXCLUDED.updated_at
                """,
                (account_id, plan, session_id, datetime.now()),
            )
        conn.commit()

    with_conn(_do)


def clear_pending(account_id: str) -> None:
    """Drops an unpaid checkout (status 'pending') -- back to plain Free."""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute("DELETE FROM subscriptions WHERE id = %s AND status = 'pending'", (account_id,))
        conn.commit()

    with_conn(_do)


def activate_subscription(session_id: str, plan_id: str, period_days: int = 30) -> str | None:
    """Called from the payment_session.completed webhook — flips the
    pending row (matched by xendit_session_id) to active and records the
    recurring plan id, so later per-cycle webhooks (matched by plan id
    instead) know which row to update. Returns the account_id activated, or
    None if no pending checkout matched (e.g. a stale/duplicate webhook)."""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE subscriptions SET status = 'active', xendit_plan_id = %s,
                    current_period_end = %s, updated_at = %s
                WHERE xendit_session_id = %s
                RETURNING id
                """,
                (plan_id, datetime.now() + timedelta(days=period_days), datetime.now(), session_id),
            )
            row = cur.fetchone()
        conn.commit()
        return row[0] if row else None

    return with_conn(_do)


def extend_subscription(plan_id: str, period_days: int = 30) -> None:
    """recurring.cycle.succeeded — this cycle's charge went through, push
    current_period_end out another cycle (and clear a prior past_due)."""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE subscriptions SET status = 'active', current_period_end = %s, updated_at = %s "
                "WHERE xendit_plan_id = %s",
                (datetime.now() + timedelta(days=period_days), datetime.now(), plan_id),
            )
        conn.commit()

    with_conn(_do)


def mark_past_due(plan_id: str) -> None:
    """recurring.cycle.failed — all retries exhausted for this cycle."""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE subscriptions SET status = 'past_due', updated_at = %s WHERE xendit_plan_id = %s",
                (datetime.now(), plan_id),
            )
        conn.commit()

    with_conn(_do)


def cancel_subscription(account_id: str = DEFAULT_ACCOUNT_ID) -> str | None:
    """"Turunkan ke Free" — doesn't downgrade immediately. Sets
    cancel_at_period_end so the user keeps what they already paid for until
    current_period_end (get_subscription() is what actually reports it as
    Free once that passes). Returns the xendit_plan_id that needs
    deactivating on Xendit's side right away, so no further charge ever
    lands (the caller makes that HTTP call — this module only touches our
    own DB) — or None if there was nothing active to cancel."""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT xendit_plan_id FROM subscriptions WHERE id = %s", (account_id,))
            row = cur.fetchone()
            if row and row[0]:
                cur.execute(
                    "UPDATE subscriptions SET cancel_at_period_end = TRUE, updated_at = %s WHERE id = %s",
                    (datetime.now(), account_id),
                )
        conn.commit()
        return row[0] if row else None

    return with_conn(_do)
