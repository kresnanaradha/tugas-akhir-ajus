"""Aggregates everything the super admin dashboard shows — one function,
one round of (mostly cheap) queries, rather than the frontend making 5
separate calls. See app.py's GET /admin/stats.
"""

from . import auth_store, billing_store, storage, usage_store
from .meetings_store import counts_by_period, daily_counts


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
        "users_total": auth_store.count_users(),
        "plan_counts": plan_counts,
        "mrr_idr": mrr_idr,
        "openai_cost": usage_store.total_cost(),
        "storage_bytes": storage_bytes,
    }
