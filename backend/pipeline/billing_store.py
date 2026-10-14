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
-- "Turunkan ke Free" menghentikan tagihan berikutnya langsung tapi paket berbayar tetap sampai current_period_end
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE;
"""
register_schema(_TABLE_SQL)

# apa yang boleh tiap paket, None = tanpa batas. Dijalankan di app.py (_check_meeting_quota, _join). max_duration_minutes
# Free hanya batas teknis untuk bot yang nyangkut, menit mingguan yang menentukan pemrosesan AI
PLAN_LIMITS = {
    "free": {"meetings_per_month": 5, "max_duration_minutes": 180, "minutes_per_week": 60},
    "pro": {"meetings_per_month": None, "max_duration_minutes": None, "minutes_per_week": None},
    "team": {"meetings_per_month": None, "max_duration_minutes": None, "minutes_per_week": None},
}

# IDR per bulan, Free tidak punya checkout. Ada di sini supaya admin_stats bisa memakainya untuk MRR
PLAN_PRICES = {"pro": 99_000, "team": 299_000}


def count_active_by_plan() -> dict:
    """{"pro": N, "team": N} langganan aktif per paket, untuk MRR. Seperti get_subscription(), baris yang periode
    batalnya sudah lewat tidak aktif walau kolom status-nya belum diperbarui."""

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
    """Paket yang berlaku saat ini: pembatalan terjadwal berlaku saat periode berbayar selesai (dihitung saat dibaca,
    tanpa cron), dan checkout yang belum dibayar ('pending') belum mendapat apa-apa."""
    period_end = row.get("current_period_end")
    if row["cancel_at_period_end"] and period_end and period_end < datetime.now():
        row["plan"] = "free"
        row["status"] = "canceled"
    if row["status"] == "pending":
        row["plan"] = "free"


def get_subscription(account_id: str) -> dict:
    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM subscriptions WHERE id = %s", (account_id,))
            row = cur.fetchone()
        return dict(row) if row else None

    row = with_conn(_do)
    if row is None:
        # tanpa baris = belum pernah bayar apa pun, itu Free
        return {"id": account_id, "plan": "free", "status": "active", "current_period_end": None, "cancel_at_period_end": False}
    _apply_effective_state(row)
    period_end = row.get("current_period_end")
    if period_end:
        row["current_period_end"] = period_end.strftime("%Y-%m-%dT%H:%M:%S")
    return row


def team_plans(user_id: str | None = None) -> dict[str, str]:
    """{user_id: paket} untuk user yang pemilik team-nya punya paket Team aktif (anggota berbagi paketnya). Satu query, atau
    isi user_id untuk satu user."""

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
    """(paket, diwarisi_dari_team): paket berbayar milik user sendiri, kalau tidak paket Team milik pemilik team-nya."""
    own = get_subscription(user_id)["plan"]
    if own != "free":
        return own, False
    return ("team", True) if user_id in team_plans(user_id) else ("free", False)


def plans_by_user() -> dict[str, str]:
    """{user_id: paket} untuk semua yang punya baris langganan, dalam satu query. Tanpa baris berarti Free."""

    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, plan, status, cancel_at_period_end, current_period_end FROM subscriptions")
            return [dict(r) for r in cur.fetchall()]

    rows = with_conn(_do)
    for r in rows:
        _apply_effective_state(r)
    return {r["id"]: r["plan"] for r in rows}


def start_checkout(plan: str, session_id: str, account_id: str) -> None:
    """Catat checkout yang dimulai. Statusnya tetap 'pending' sampai webhook payment_session.completed bilang
    user sudah menautkan metode pembayaran."""

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
    """Buang checkout yang belum dibayar (status 'pending') -- kembali ke Free biasa."""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute("DELETE FROM subscriptions WHERE id = %s AND status = 'pending'", (account_id,))
        conn.commit()

    with_conn(_do)


def activate_subscription(session_id: str, plan_id: str, period_days: int = 30) -> str | None:
    """webhook payment_session.completed: ubah baris pending (dicocokkan lewat id sesi) jadi aktif dan simpan
    id plan berulang untuk webhook per siklus. Mengembalikan id akun, None kalau tidak ada yang cocok."""

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
    """recurring.cycle.succeeded: majukan current_period_end satu siklus dan hapus past_due."""

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
    """recurring.cycle.failed - semua percobaan ulang untuk siklus ini habis."""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE subscriptions SET status = 'past_due', updated_at = %s WHERE xendit_plan_id = %s",
                (datetime.now(), plan_id),
            )
        conn.commit()

    with_conn(_do)


def cancel_subscription(account_id: str) -> str | None:
    """"Turunkan ke Free": user tetap punya paket berbayar sampai current_period_end (get_subscription melaporkan
    Free setelah itu). Mengembalikan id plan Xendit yang harus dinonaktifkan pemanggil sekarang supaya tidak ada tagihan lagi,
    None kalau tidak ada yang dibatalkan."""

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
