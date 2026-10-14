"""Aggregates everything the super admin dashboard shows — one function,
one round of (mostly cheap) queries, rather than the frontend making 5
separate calls. See app.py's GET /admin/stats.
"""

import psycopg2.extras

from . import auth_store, billing_store, storage, usage_store
from .db import with_conn
from .meetings_store import counts_by_period, daily_counts


def teams_usage() -> list[dict]:
    """Per team: members and how much its members' meetings add up to (failed
    joins excluded, same counting as report_stats.team_usage), busiest first."""
    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT t.id, t.name, o.name AS owner_name,
                       COUNT(DISTINCT u.id) AS members,
                       COUNT(m.id) AS meetings,
                       COUNT(m.id) FILTER (WHERE m.created_at >= date_trunc('month', CURRENT_DATE)) AS this_month,
                       COUNT(m.id) FILTER (WHERE m.shared_with_team) AS shared,
                       COALESCE(SUM(m.duration_minutes), 0) AS minutes
                FROM teams t
                LEFT JOIN users o ON o.id = t.owner_id
                LEFT JOIN users u ON u.team_id = t.id
                LEFT JOIN meetings m ON m.user_id = u.id AND m.status <> 'failed'
                GROUP BY t.id, t.name, o.name
                ORDER BY meetings DESC, t.name
                """
            )
            return [{**r, "minutes": round(float(r["minutes"]), 1)} for r in cur.fetchall()]

    return with_conn(_do)


def get_stats() -> dict:
    meetings = counts_by_period()
    meetings_daily = daily_counts()
    plan_counts = billing_store.count_active_by_plan()
    mrr_idr = sum(billing_store.PLAN_PRICES.get(plan, 0) * n for plan, n in plan_counts.items())

    try:
        storage_bytes = storage.total_size_bytes()
    except Exception as e:
        # R2 being briefly unreachable shouldn't blank the whole dashboard —
        # every other figure here comes from Postgres, a separate dependency.
        print(f"[admin_stats] failed to get R2 storage size: {e}")
        storage_bytes = None

    return {
        "meetings": meetings,
        "meetings_daily": meetings_daily,
        "teams": teams_usage(),
        "users_total": auth_store.count_users(),
        "plan_counts": plan_counts,
        "mrr_idr": mrr_idr,
        "openai_cost": usage_store.total_cost(),
        "storage_bytes": storage_bytes,
    }
