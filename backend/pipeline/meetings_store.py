import uuid
from datetime import datetime, timedelta

from .db import execute, fetch_all, fetch_one, fetch_value, register_schema

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
-- rapat salinan: User kedua yang memasukkan tautan yang sama dengan rapat yang sedang atau baru direkam mendapat rapat sendiri,
-- dan baris ini menunjuk ke rapat sumber (NULL untuk rapat biasa). Hasilnya disalin saat sumber selesai, rekamannya tetap satu berkas
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS source_meeting_id TEXT;
-- saat rekaman berakhir, untuk menentukan berapa lama tautan itu masih dianggap rapat yang sama
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS ended_at TIMESTAMP;
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

    execute(
        """
        INSERT INTO meetings (id, platform, title, created_at, status, recording, estimated_participants, url, user_id)
        VALUES (%s, %s, %s, %s, %s, '', %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (meeting_id, platform, title, datetime.now(), "joining", estimated_participants, url, user_id),
    )


# tautan yang sama dianggap rapat yang sama selama bot masih bergabung atau merekam, ditambah beberapa menit setelah rekaman
# berakhir (untuk yang terlambat memasukkan tautan). Lebih lama dari itu tautan berulang (rapat mingguan, ruang Zoom pribadi)
# adalah rapat baru dan tidak boleh memberi seseorang transkrip lama.
_SHARE_MINUTES_AFTER_END = 30


def find_meeting_by_url(url: str) -> dict | None:
    """Rapat sumber (bukan salinan) non-gagal untuk tautan ini yang masih berjalan atau baru berakhir, supaya _join()
    tidak memulai bot kedua untuk rapat yang sama. Percobaan yang gagal tidak dihitung, jadi mencoba ulang mulai dari awal."""
    row = fetch_one(
        """
        SELECT * FROM meetings
        WHERE url = %s AND source_meeting_id IS NULL AND status != 'failed'
            AND (status IN ('joining', 'recording', 'stopping') OR ended_at > %s)
        ORDER BY created_at DESC LIMIT 1
        """,
        # batasnya dihitung di sini, bukan NOW() database: ended_at ditulis dengan jam server (datetime.now()), sedangkan
        # NOW() mengikuti zona waktu database (Supabase UTC) sehingga jendelanya bisa melebar beberapa jam
        (url, datetime.now() - timedelta(minutes=_SHARE_MINUTES_AFTER_END)),
    )
    return _with_iso_date(row) if row else None


def create_follower(source: dict, user_id: str) -> str:
    """Buat rapat salinan milik user_id untuk rapat sumber dan kembalikan id-nya. Statusnya mengikuti sumber
    (kecuali selesai, itu diisi followers.finish_follower setelah hasilnya tersalin)."""
    follower_id = uuid.uuid4().hex
    status = "processing" if source["status"] == "completed" else source["status"]
    execute(
        """
        INSERT INTO meetings (id, platform, title, created_at, duration_minutes, status, recording, estimated_participants,
                              url, user_id, source_meeting_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (follower_id, source["platform"], source["title"], datetime.now(), source.get("duration_minutes"), status,
         source["recording"], source.get("estimated_participants"), source.get("url"), user_id, source["id"]),
    )
    return follower_id


def find_follower(source_id: str, user_id: str) -> str | None:
    """Id rapat salinan milik user ini untuk rapat sumber, kalau sudah ada (tautan ditempel dua kali)."""
    return fetch_value("SELECT id FROM meetings WHERE source_meeting_id = %s AND user_id = %s", (source_id, user_id))


def list_followers(source_id: str) -> list[dict]:
    """Rapat salinan dari sumber ini yang hasilnya belum tersalin."""
    return fetch_all("SELECT * FROM meetings WHERE source_meeting_id = %s AND status <> 'completed'", (source_id,))


def recording_refs(recording: str, exclude_id: str) -> int:
    """Berapa rapat lain yang memakai berkas rekaman yang sama (sumber dan salinannya berbagi satu berkas)."""
    return fetch_value("SELECT COUNT(*) FROM meetings WHERE recording = %s AND id <> %s", (recording, exclude_id))


# yang ikut disalin ke rapat salinan saat sumbernya berubah. Status "completed" tidak: itu diisi setelah hasilnya tersalin
_MIRRORED = ("recording", "duration_minutes", "ended_at")


def _mirror_to_followers(meeting_id: str, fields: dict) -> None:
    mirror = {col: val for col, val in fields.items() if col in _MIRRORED}
    if fields.get("status") not in (None, "completed"):
        mirror["status"] = fields["status"]
    if mirror:
        set_clause = ", ".join(f"{col} = %s" for col in mirror)
        execute(
            f"UPDATE meetings SET {set_clause} WHERE source_meeting_id = %s AND status <> 'completed'",
            (*mirror.values(), meeting_id),
        )


def update_meeting(meeting_id: str, **fields) -> None:
    """Ubah kolom pada baris yang sudah ada (status selama join berjalan, rekaman, durasi...)."""
    if fields:
        set_clause = ", ".join(f"{col} = %s" for col in fields)
        execute(f"UPDATE meetings SET {set_clause} WHERE id = %s", (*fields.values(), meeting_id))
        _mirror_to_followers(meeting_id, fields)


def delete_meeting(meeting_id: str) -> None:
    execute("UPDATE meetings SET source_meeting_id = NULL WHERE source_meeting_id = %s", (meeting_id,))
    execute("DELETE FROM meetings WHERE id = %s", (meeting_id,))


def list_meetings(user_id: str | None = None) -> list[dict]:
    """Semua rapat (user_id=None, hanya admin), atau milik user ini (termasuk rapat salinan), dan
    rapat teman yang dibagikan pemiliknya ke team. Baris dari sebelum login (user_id NULL) hanya tampil
    di tampilan tanpa filter."""

    if user_id is None:
        rows = fetch_all("SELECT * FROM meetings ORDER BY created_at DESC")
    else:
        rows = fetch_all(
            """
            SELECT * FROM meetings
            WHERE user_id = %s
                OR (shared_with_team AND user_id IN (
                    SELECT id FROM users
                    WHERE team_id IS NOT NULL
                        AND team_id = (SELECT team_id FROM users WHERE id = %s)
                ))
            ORDER BY created_at DESC
            """,
            (user_id, user_id),
        )
    return [_with_iso_date(row) for row in rows]


def count_own_this_month(user_id: str) -> int:
    """Rapat milik user ini yang dimulai bulan ini, untuk batas bulanan Free."""

    return fetch_value(
        "SELECT COUNT(*) FROM meetings WHERE user_id = %s AND created_at >= date_trunc('month', CURRENT_DATE)", (user_id,)
    )


def recorded_minutes_since(user_id: str, since: datetime) -> float:
    """Menit rekaman bot milik user ini sejak `since`, untuk jatah mingguan Free. Upload (tanpa url) dan
    rekaman yang disimpan tanpa diproses (status "limited") tidak dihitung."""

    return float(fetch_value(
        "SELECT COALESCE(SUM(duration_minutes), 0) FROM meetings "
        "WHERE user_id = %s AND url IS NOT NULL AND source_meeting_id IS NULL AND status <> 'limited' AND created_at >= %s",
        (user_id, since),
    ))


def counts_by_period(user_id: str | None = None) -> dict:
    """today / this_week / this_month / total / completed / failed, untuk semua (admin) atau satu user.
    Minggu mulai hari Senin (date_trunc Postgres)."""

    return fetch_one(
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


def daily_counts(days: int = 14, user_id: str | None = None) -> list[dict]:
    """[{"date": "YYYY-MM-DD", "count": N}] untuk `days` hari terakhir, yang terlama dulu. generate_series mempertahankan
    hari tanpa rapat."""

    rows = fetch_all(
        f"""
        SELECT d::date AS day, COALESCE(COUNT(m.id), 0) AS n
        FROM generate_series(CURRENT_DATE - (%s - 1) * INTERVAL '1 day', CURRENT_DATE, INTERVAL '1 day') d
        LEFT JOIN meetings m ON date_trunc('day', m.created_at) = d
            {"AND m.user_id = %s" if user_id is not None else ""}
        GROUP BY d
        ORDER BY d
        """,
        (days, user_id) if user_id is not None else (days,),
    )
    return [{"date": r["day"].strftime("%Y-%m-%d"), "count": r["n"]} for r in rows]


def platform_counts(user_id: str | None = None) -> dict:
    """{"google_meet": N, "zoom": N, "upload": N}"""

    rows = fetch_all(
        f"""
        SELECT platform, COUNT(*) AS n FROM meetings
        {"WHERE user_id = %s" if user_id is not None else ""}
        GROUP BY platform
        """,
        (user_id,) if user_id is not None else None,
    )
    return {r["platform"]: r["n"] for r in rows}


def total_duration_minutes(user_id: str | None = None) -> float:
    """Total menit rekaman (upload tidak punya durasi dan tidak menambah apa-apa)."""

    return float(fetch_value(
        f"""
        SELECT COALESCE(SUM(duration_minutes), 0) FROM meetings
        {"WHERE user_id = %s" if user_id is not None else ""}
        """,
        (user_id,) if user_id is not None else None,
    ))


def get_meeting(meeting_id: str) -> dict | None:
    row = fetch_one("SELECT * FROM meetings WHERE id = %s", (meeting_id,))
    return _with_iso_date(row) if row else None


def _with_iso_date(row: dict) -> dict:
    row["created_at"] = row["created_at"].strftime("%Y-%m-%dT%H:%M:%S")
    return row
