"""Aggregates everything the regular (non-admin) Laporan page shows — one
user's own meetings only, unlike admin_stats.py's system-wide view. See
app.py's GET /reports/stats.
"""

import time
from concurrent.futures import ThreadPoolExecutor

from . import artifacts
from .meetings_store import counts_by_period, daily_counts, list_meetings, platform_counts, total_duration_minutes

# user_id -> (computed_at, rollup). Reading every meeting's summary.json from
# R2 is slow (one round trip each), so it's read in parallel and cached.
# ponytail: 60s per-process cache, invalidate on writes if staleness matters.
_rollup_cache: dict = {}
_OPEN_ITEMS_LIMIT = 40


def _action_item_rollup(user_id: str) -> dict:
    """Every action item across this user's finished meetings: totals, a
    per-assignee breakdown, and the still-open items (newest meeting first)."""
    cached = _rollup_cache.get(user_id)
    if cached and time.time() - cached[0] < 60:
        return cached[1]

    meetings = [m for m in list_meetings(user_id) if m["status"] == "completed" and m["recording"]]

    def load(m):
        try:
            return artifacts.load_summary(m["id"])
        except Exception:
            return None

    with ThreadPoolExecutor(8) as pool:
        summaries = list(pool.map(load, meetings))

    items = []
    for m, summary in zip(meetings, summaries):
        for index, a in enumerate((summary or {}).get("action_items") or []):
            items.append(
                {
                    "meeting_id": m["id"],
                    "meeting_title": m["title"],
                    # Index into that meeting's own action_items array (same order
                    # summary.json stores it in) -- the frontend needs this to call
                    # POST /meetings/<id>/action-items/<index>/toggle from this
                    # cross-meeting list, since a rollup entry doesn't have its own id.
                    "index": index,
                    "task": a.get("task"),
                    "assignee": a.get("assignee"),
                    "due": a.get("due"),
                    "done": bool(a.get("done")),
                }
            )

    by_assignee: dict = {}
    for it in items:
        row = by_assignee.setdefault(it["assignee"] or "Belum ditentukan", {"open": 0, "done": 0})
        row["done" if it["done"] else "open"] += 1
    open_items = [it for it in items if not it["done"]]
    result = {
        "total": len(items),
        "done": len(items) - len(open_items),
        "open": len(open_items),
        "by_assignee": sorted(
            ({"assignee": k, **v} for k, v in by_assignee.items()), key=lambda r: r["open"] + r["done"], reverse=True
        ),
        "open_items": open_items[:_OPEN_ITEMS_LIMIT],
    }
    _rollup_cache[user_id] = (time.time(), result)
    return result


def action_item_rollup(user_id: str) -> dict:
    return _action_item_rollup(user_id)


def invalidate_action_item_cache(user_id: str) -> None:
    """Called after a toggle/edit changes a meeting's action items, so the
    Laporan rollup doesn't keep serving stale done/open counts for up to 60s."""
    _rollup_cache.pop(user_id, None)


def get_stats(user_id: str, with_action_items: bool = False) -> dict:
    """with_action_items reads every summary from R2 (slow on the first call),
    so the Laporan page fetches that part separately and only the PDF asks
    for it here."""
    stats = {
        "meetings": counts_by_period(user_id),
        "meetings_daily": daily_counts(user_id=user_id),
        "platform_counts": platform_counts(user_id),
        "total_duration_minutes": total_duration_minutes(user_id),
    }
    if with_action_items:
        stats["action_items"] = _action_item_rollup(user_id)
    return stats
