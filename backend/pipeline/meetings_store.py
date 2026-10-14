from datetime import datetime

import psycopg2.extras

from .db import register_schema, with_conn

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    duration_minutes REAL,
    status TEXT NOT NULL,
    recording TEXT NOT NULL
);
-- CREATE TABLE IF NOT EXISTS tidak menambah kolom ke database yang sudah ada, jadi kolom berikutnya dapat ALTER sendiri
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS estimated_participants INTEGER;
-- tautan rapat, supaya permintaan kedua untuk tautan live yang sama bisa berbagi rapat (NULL untuk upload)
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS url TEXT;
-- pemilik rapat (users.id berupa string hex). NULL untuk rapat dari sebelum login ada
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS user_id TEXT;
-- di-opt in ke Knowledge Base
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS in_kb BOOLEAN DEFAULT FALSE;
-- pemilik membagikannya ke team-nya (opt in per rapat)
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS shared_with_team BOOLEAN DEFAULT FALSE;
-- orang yang boleh melihat rapat yang bukan miliknya: mereka mengirim tautan live yang sama dan diberi rapat yang sudah ada
CREATE TABLE IF NOT EXISTS meeting_viewers (
    meeting_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    PRIMARY KEY (meeting_id, user_id)
);
"""
register_schema(_TABLE_SQL)
# recording NOT NULL (menghapusnya membuat Supabase macet), jadi '' berarti "belum ada rekaman"


def start_meeting(
    meeting_id: str,
    platform: str,
    title: str,
    estimated_participants: int | None = None,
    url: str | None = None,
    user_id: str | None = None,
) -> None:
    """Masukkan baris saat join dimulai (belum ada rekaman) supaya daftar bisa menampilkannya sedang berjalan.
    meeting_id adalah id job, jadi /jobs/<id> dan /meetings/<id> memakai id yang sama."""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meetings (id, platform, title, created_at, status, recording, estimated_participants, url, user_id)
                VALUES (%s, %s, %s, %s, %s, '', %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (meeting_id, platform, title, datetime.now(), "joining", estimated_participants, url, user_id),
            )
        conn.commit()

    with_conn(_do)


# tautan berulang (rapat mingguan, ruang Zoom pribadi) tidak boleh memberi seseorang transkrip lama, jadi
# berbagi hanya melihat rapat dari beberapa jam terakhir
_SHARE_WINDOW_HOURS = 6


def find_meeting_by_url(url: str) -> dict | None:
    """Rapat non-gagal terbaru untuk tautan ini di dalam jendela berbagi, supaya _join() bisa membagikannya
    dan tidak memulai bot kedua. Percobaan yang gagal tidak dihitung, jadi mencoba ulang mulai dari awal."""

    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM meetings
                WHERE url = %s AND status != 'failed'
                    AND created_at > NOW() - make_interval(hours => %s)
                ORDER BY created_at DESC LIMIT 1
                """,
                (url, _SHARE_WINDOW_HOURS),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    row = with_conn(_do)
    if row is None:
        return None
    row["created_at"] = row["created_at"].strftime("%Y-%m-%dT%H:%M:%S")
    return row


def update_meeting(meeting_id: str, **fields) -> None:
    """Ubah kolom pada baris yang sudah ada (status selama join berjalan, rekaman, durasi...)."""
    if not fields:
        return

    def _do(conn):
        set_clause = ", ".join(f"{col} = %s" for col in fields)
        with conn.cursor() as cur:
            cur.execute(f"UPDATE meetings SET {set_clause} WHERE id = %s", (*fields.values(), meeting_id))
        conn.commit()

    with_conn(_do)


def add_viewer(meeting_id: str, user_id: str) -> None:
    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO meeting_viewers (meeting_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (meeting_id, user_id),
            )
        conn.commit()

    with_conn(_do)


def is_viewer(meeting_id: str, user_id: str) -> bool:
    def _do(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM meeting_viewers WHERE meeting_id = %s AND user_id = %s", (meeting_id, user_id))
            return cur.fetchone() is not None

    return with_conn(_do)


def delete_meeting(meeting_id: str) -> None:
    def _do(conn):
        with conn.cursor() as cur:
            cur.execute("DELETE FROM meeting_viewers WHERE meeting_id = %s", (meeting_id,))
            cur.execute("DELETE FROM meetings WHERE id = %s", (meeting_id,))
        conn.commit()

    with_conn(_do)


def list_meetings(user_id: str | None = None) -> list[dict]:
    """Semua rapat (user_id=None, hanya admin), atau milik user ini, yang dibagikan ke mereka lewat tautan, dan
    rapat teman yang dibagikan pemiliknya ke team. Baris dari sebelum login (user_id NULL) hanya tampil
    di tampilan tanpa filter."""

    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if user_id is None:
                cur.execute("SELECT * FROM meetings ORDER BY created_at DESC")
            else:
                cur.execute(
                    """
                    SELECT * FROM meetings
                    WHERE user_id = %s
                        OR id IN (SELECT meeting_id FROM meeting_viewers WHERE user_id = %s)
                        OR (shared_with_team AND user_id IN (
                            SELECT id FROM users
                            WHERE team_id IS NOT NULL
                                AND team_id = (SELECT team_id FROM users WHERE id = %s)
                        ))
                    ORDER BY created_at DESC
                    """,
                    (user_id, user_id, user_id),
                )
            return [dict(row) for row in cur.fetchall()]

    rows = with_conn(_do)
    for row in rows:
        row["created_at"] = row["created_at"].strftime("%Y-%m-%dT%H:%M:%S")
    return rows


def count_own_this_month(user_id: str) -> int:
    """Rapat milik user ini yang dimulai bulan ini, untuk batas bulanan Free."""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM meetings WHERE user_id = %s AND created_at >= date_trunc('month', CURRENT_DATE)",
                (user_id,),
            )
            return cur.fetchone()[0]

    return with_conn(_do)


def recorded_minutes_since(user_id: str, since: datetime) -> float:
    """Menit rekaman bot milik user ini sejak `since`, untuk jatah mingguan Free. Upload (tanpa url) dan
    rekaman yang disimpan tanpa diproses (status "limited") tidak dihitung."""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(duration_minutes), 0) FROM meetings WHERE user_id = %s AND url IS NOT NULL AND status <> 'limited' AND created_at >= %s",
                (user_id, since),
            )
            return float(cur.fetchone()[0])

    return with_conn(_do)


def counts_by_period(user_id: str | None = None) -> dict:
    """today / this_week / this_month / total / completed / failed, untuk semua (admin) atau satu user.
    Minggu mulai hari Senin (date_trunc Postgres)."""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE) AS today,
                    COUNT(*) FILTER (WHERE created_at >= date_trunc('week', CURRENT_DATE)) AS this_week,
                    COUNT(*) FILTER (WHERE created_at >= date_trunc('month', CURRENT_DATE)) AS this_month,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                    COUNT(*) FILTER (WHERE status = 'failed') AS failed
                FROM meetings
                {"WHERE user_id = %s" if user_id is not None else ""}
                """,
                (user_id,) if user_id is not None else None,
            )
            return cur.fetchone()

    row = with_conn(_do)
    return {
        "today": row[0],
        "this_week": row[1],
        "this_month": row[2],
        "total": row[3],
        "completed": row[4],
        "failed": row[5],
    }


def daily_counts(days: int = 14, user_id: str | None = None) -> list[dict]:
    """[{"date": "YYYY-MM-DD", "count": N}] untuk `days` hari terakhir, yang terlama dulu. generate_series mempertahankan
    hari tanpa rapat."""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT d::date, COALESCE(COUNT(m.id), 0)
                FROM generate_series(CURRENT_DATE - (%s - 1) * INTERVAL '1 day', CURRENT_DATE, INTERVAL '1 day') d
                LEFT JOIN meetings m ON date_trunc('day', m.created_at) = d
                    {"AND m.user_id = %s" if user_id is not None else ""}
                GROUP BY d
                ORDER BY d
                """,
                (days, user_id) if user_id is not None else (days,),
            )
            return cur.fetchall()

    rows = with_conn(_do)
    return [{"date": d.strftime("%Y-%m-%d"), "count": n} for d, n in rows]


def platform_counts(user_id: str | None = None) -> dict:
    """{"google_meet": N, "zoom": N, "upload": N}"""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT platform, COUNT(*) FROM meetings
                {"WHERE user_id = %s" if user_id is not None else ""}
                GROUP BY platform
                """,
                (user_id,) if user_id is not None else None,
            )
            return dict(cur.fetchall())

    return with_conn(_do)


def total_duration_minutes(user_id: str | None = None) -> float:
    """Total menit rekaman (upload tidak punya durasi dan tidak menambah apa-apa)."""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COALESCE(SUM(duration_minutes), 0) FROM meetings
                {"WHERE user_id = %s" if user_id is not None else ""}
                """,
                (user_id,) if user_id is not None else None,
            )
            return cur.fetchone()[0]

    return float(with_conn(_do))


def get_meeting(meeting_id: str) -> dict | None:
    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM meetings WHERE id = %s", (meeting_id,))
            row = cur.fetchone()
        return dict(row) if row else None

    row = with_conn(_do)
    if row is None:
        return None
    row["created_at"] = row["created_at"].strftime("%Y-%m-%dT%H:%M:%S")
    return row
