"""Angka untuk halaman Laporan: rapat milik satu user saja (admin_stats.py adalah versi seluruh sistem)."""

import time
from concurrent.futures import ThreadPoolExecutor

import psycopg2.extras

from . import artifacts, auth_store, team_store
from .db import with_conn
from .meetings_store import counts_by_period, daily_counts, list_meetings, platform_counts, total_duration_minutes

# user_id -> (waktu_hitung, rekap). Membaca semua summary.json dari R2 itu lambat, jadi dibaca
# paralel dan di-cache. ponytail: cache 60 detik per proses, dibersihkan saat action item berubah
_rollup_cache: dict = {}
_OPEN_ITEMS_LIMIT = 40


def action_item_rollup(user_id: str) -> dict:
    """Semua action item di seluruh rapat selesai milik user: total, per penanggung jawab, dan yang masih terbuka."""
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
                    # posisi di action_items rapat itu, endpoint toggle membutuhkannya
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


def invalidate_action_item_cache(user_id: str) -> None:
    """Dipanggil saat action item berubah, supaya halaman Laporan tidak menampilkan hitungan lama."""
    _rollup_cache.pop(user_id, None)


def team_usage(user_id: str) -> dict | None:
    """Pemakaian team user (None kalau tidak punya team): rapat, bulan ini, dibagikan, dan menit, total
    dan per anggota. Join gagal dikecualikan, dan yang keluar membawa rapatnya keluar dari angka."""
    user = auth_store.get_user(user_id)
    team = team_store.get_team(user["team_id"]) if user and user.get("team_id") else None
    if team is None:
        return None

    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT u.id, u.name, u.team_role AS role,
                       COUNT(m.id) AS meetings,
                       COUNT(m.id) FILTER (WHERE m.created_at >= date_trunc('month', CURRENT_DATE)) AS this_month,
                       COUNT(m.id) FILTER (WHERE m.shared_with_team) AS shared,
                       COALESCE(SUM(m.duration_minutes), 0) AS minutes
                FROM users u
                LEFT JOIN meetings m ON m.user_id = u.id AND m.status <> 'failed'
                WHERE u.team_id = %s
                GROUP BY u.id, u.name, u.team_role
                ORDER BY meetings DESC, u.name
                """,
                (team["id"],),
            )
            return [dict(r) for r in cur.fetchall()]

    members = [{**r, "minutes": round(float(r["minutes"]), 1)} for r in with_conn(_do)]
    return {
        "team": {"id": team["id"], "name": team["name"]},
        "totals": {
            "meetings": sum(m["meetings"] for m in members),
            "this_month": sum(m["this_month"] for m in members),
            "shared": sum(m["shared"] for m in members),
            "minutes": round(sum(m["minutes"] for m in members), 1),
        },
        "members": members,
    }


def get_stats(user_id: str) -> dict:
    return {
        "meetings": counts_by_period(user_id),
        "meetings_daily": daily_counts(user_id=user_id),
        "platform_counts": platform_counts(user_id),
        "total_duration_minutes": total_duration_minutes(user_id),
    }
