from datetime import datetime
from pathlib import Path

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
-- CREATE TABLE IF NOT EXISTS only helps on a fresh database — this table
-- already existed in Supabase before this column was added, so it needs its
-- own idempotent statement too.
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS estimated_participants INTEGER;
-- The meeting link itself — join()'s only way to notice "someone already
-- has a bot on this exact link" and share that instead of starting a
-- second one (see find_meeting_by_url()). NULL for /upload, which has no
-- link at all.
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS url TEXT;
"""
register_schema(_TABLE_SQL)
# recording stays NOT NULL — ALTER TABLE ... DROP NOT NULL turned out to hang
# and time out against Supabase's pooler (tested in isolation, consistently
# ~120s then QueryCanceled; not worth chasing why). start_meeting() below
# uses '' (empty string) as the "no recording yet" sentinel for a live join
# instead of NULL — every truthiness check on this column elsewhere
# (`if recording_path:` etc.) already treats '' the same as None/null, in
# both Python and JS, so nothing downstream needed to change for this.


def add_meeting(
    platform: str,
    title: str,
    recording_path: str,
    duration_minutes: float | None,
    result: dict,
    created_at: datetime | None = None,
    estimated_participants: int | None = None,
) -> dict:
    """Inserts one meeting record. `result` is whatever _process_recording()
    returned — reused here just to derive a simple status, not duplicated
    logic. `created_at` defaults to now; only overridden when backfilling
    older recordings that predate this table. `estimated_participants` is
    the same user-entered diarization hint passed to transcribe()'s
    num_speakers — stored too so the meeting detail page can show it as a
    real (labeled-as-estimated) number instead of omitting it."""
    record = {
        "id": Path(recording_path).stem,
        "platform": platform,
        "title": title,
        "created_at": created_at or datetime.now(),
        "duration_minutes": duration_minutes,
        "status": "failed" if result.get("transcript_error") else "completed",
        "recording": recording_path,
        "estimated_participants": estimated_participants,
    }

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meetings (id, platform, title, created_at, duration_minutes, status, recording, estimated_participants)
                VALUES (%(id)s, %(platform)s, %(title)s, %(created_at)s, %(duration_minutes)s, %(status)s, %(recording)s, %(estimated_participants)s)
                ON CONFLICT (id) DO NOTHING
                """,
                record,
            )
        conn.commit()

    with_conn(_do)
    record["created_at"] = record["created_at"].strftime("%Y-%m-%dT%H:%M:%S")
    return record


def start_meeting(
    meeting_id: str, platform: str, title: str, estimated_participants: int | None = None, url: str | None = None
) -> None:
    """Inserts a row the moment a live join starts, with no recording file
    yet — so the Rapat list can show it as in-progress (status "joining",
    then "recording", etc. via update_meeting()) instead of only appearing
    once the whole pipeline is done. `meeting_id` is the job_id from
    app.py's _join(), reused as the row's id so the same id works for both
    GET /jobs/<id> (live polling) and GET /meetings/<id> (once finished).
    `url` is the meeting link itself — see find_meeting_by_url()."""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meetings (id, platform, title, created_at, status, recording, estimated_participants, url)
                VALUES (%s, %s, %s, %s, %s, '', %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (meeting_id, platform, title, datetime.now(), "joining", estimated_participants, url),
            )
        conn.commit()

    with_conn(_do)


# Many meeting links are recurring (a standing weekly call, someone's
# personal Zoom room reused constantly) — without a time window, sharing by
# link alone would hand someone a transcript from a completely different
# occasion weeks ago instead of starting a bot for the one happening now.
# A meeting rarely runs longer than this, so anything older genuinely is a
# different occurrence of the same link, not the same meeting.
_SHARE_WINDOW_HOURS = 6


def find_meeting_by_url(url: str) -> dict | None:
    """The most recent meeting already joining/recording/processing/done for
    this exact link, started within the last _SHARE_WINDOW_HOURS — lets
    app.py's _join() share that meeting (its live status if still in
    progress, or straight to its transcript if already done) instead of
    spawning a second bot into the same meeting. A prior 'failed' attempt on
    the same link doesn't count, so retrying after a failure still starts a
    fresh bot rather than reusing the broken one — and neither does a match
    outside the time window, so a recurring link reused next week starts
    its own fresh bot instead of resurfacing an old transcript."""

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
    """Updates arbitrary columns on an existing row — status as a live join
    progresses (joining -> recording -> ... -> completed/failed), plus
    recording/duration_minutes once those become known. No-op if `fields`
    is empty."""
    if not fields:
        return

    def _do(conn):
        set_clause = ", ".join(f"{col} = %s" for col in fields)
        with conn.cursor() as cur:
            cur.execute(f"UPDATE meetings SET {set_clause} WHERE id = %s", (*fields.values(), meeting_id))
        conn.commit()

    with_conn(_do)


def list_meetings() -> list[dict]:
    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM meetings ORDER BY created_at DESC")
            return [dict(row) for row in cur.fetchall()]

    rows = with_conn(_do)
    for row in rows:
        row["created_at"] = row["created_at"].strftime("%Y-%m-%dT%H:%M:%S")
    return rows


def counts_by_period() -> dict:
    """{"today", "this_week", "this_month", "total", "completed", "failed"} —
    for the super admin dashboard. date_trunc('week', ...) starts weeks on
    Monday (Postgres default), matching Indonesian convention."""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE) AS today,
                    COUNT(*) FILTER (WHERE created_at >= date_trunc('week', CURRENT_DATE)) AS this_week,
                    COUNT(*) FILTER (WHERE created_at >= date_trunc('month', CURRENT_DATE)) AS this_month,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                    COUNT(*) FILTER (WHERE status = 'failed') AS failed
                FROM meetings
                """
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


def daily_counts(days: int = 14) -> list[dict]:
    """[{"date": "YYYY-MM-DD", "count": N}, ...] for the last `days` days,
    oldest first — for the super admin dashboard's meetings-per-day chart.
    generate_series fills in zero-count days (a plain GROUP BY would silently
    skip them, which would make the chart's x-axis skip days instead of
    showing a real gap)."""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT d::date, COALESCE(COUNT(m.id), 0)
                FROM generate_series(CURRENT_DATE - (%s - 1) * INTERVAL '1 day', CURRENT_DATE, INTERVAL '1 day') d
                LEFT JOIN meetings m ON date_trunc('day', m.created_at) = d
                GROUP BY d
                ORDER BY d
                """,
                (days,),
            )
            return cur.fetchall()

    rows = with_conn(_do)
    return [{"date": d.strftime("%Y-%m-%d"), "count": n} for d, n in rows]


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
