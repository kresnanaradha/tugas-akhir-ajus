"""Aggregates everything the regular (non-admin) Laporan page shows — one
user's own meetings only, unlike admin_stats.py's system-wide view. See
app.py's GET /reports/stats.
"""

from .meetings_store import counts_by_period, daily_counts, platform_counts, total_duration_minutes


def get_stats(user_id: str) -> dict:
    return {
        "meetings": counts_by_period(user_id),
        "meetings_daily": daily_counts(user_id=user_id),
        "platform_counts": platform_counts(user_id),
        "total_duration_minutes": total_duration_minutes(user_id),
    }
