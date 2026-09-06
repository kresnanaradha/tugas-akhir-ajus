import os
import threading
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras

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
"""
# recording stays NOT NULL — ALTER TABLE ... DROP NOT NULL turned out to hang
# and time out against Supabase's pooler (tested in isolation, consistently
# ~120s then QueryCanceled; not worth chasing why). start_meeting() below
# uses '' (empty string) as the "no recording yet" sentinel for a live join
# instead of NULL — every truthiness check on this column elsewhere
# (`if recording_path:` etc.) already treats '' the same as None/null, in
# both Python and JS, so nothing downstream needed to change for this.

# Kept alive across calls instead of reconnecting every time — Supabase is a
# remote database (ap-southeast-2), so opening a fresh connection cost ~1.7s
# and re-running _TABLE_SQL on top of that added another ~0.6s, on *every*
# single request. app.py runs Flask with threaded=True (so job-status polling
# doesn't queue behind a running join), so a plain module-level connection
# with no locking would be unsafe — psycopg2 connections aren't safe to use
# from multiple threads at once. _lock serializes access instead of opening
# one connection per thread; at POC request volume that's not a bottleneck,
# and it's a much smaller change than a real connection pool.
_conn = None
_table_ready = False
_lock = threading.Lock()


def _ensure_table(conn):
    global _table_ready
    if _table_ready:
        return
    with conn.cursor() as cur:
        cur.execute(_TABLE_SQL)
    conn.commit()
    _table_ready = True


def _with_conn(fn):
    """Runs fn(conn) against the shared connection (one thread at a time),
    reconnecting once and retrying if it turned out to be dead (Supabase's
    pooler can close connections that sit idle for a while)."""
    global _conn, _table_ready
    with _lock:
        if _conn is None:
            _conn = psycopg2.connect(os.environ["DATABASE_URL"])
            # Without this, a SELECT-only call (list_meetings/get_meeting)
            # still opens an implicit transaction and never closes it, since
            # only the insert/update functions called conn.commit() — found
            # by an idle-in-transaction session left open ~20 minutes from
            # testing, which then blocked a later DDL statement entirely.
            # Every statement committing on its own immediately rules that
            # whole class of bug out; the explicit conn.commit() calls
            # elsewhere in this file are harmless no-ops under autocommit.
            _conn.autocommit = True
            _ensure_table(_conn)
        try:
            return fn(_conn)
        except psycopg2.OperationalError:
            _conn = psycopg2.connect(os.environ["DATABASE_URL"])
            _conn.autocommit = True
            _table_ready = False
            _ensure_table(_conn)
            return fn(_conn)


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

    _with_conn(_do)
    record["created_at"] = record["created_at"].strftime("%Y-%m-%dT%H:%M:%S")
    return record


def start_meeting(meeting_id: str, platform: str, title: str, estimated_participants: int | None = None) -> None:
    """Inserts a row the moment a live join starts, with no recording file
    yet — so the Rapat list can show it as in-progress (status "joining",
    then "recording", etc. via update_meeting()) instead of only appearing
    once the whole pipeline is done. `meeting_id` is the job_id from
    app.py's _join(), reused as the row's id so the same id works for both
    GET /jobs/<id> (live polling) and GET /meetings/<id> (once finished)."""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meetings (id, platform, title, created_at, status, recording, estimated_participants)
                VALUES (%s, %s, %s, %s, %s, '', %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (meeting_id, platform, title, datetime.now(), "joining", estimated_participants),
            )
        conn.commit()

    _with_conn(_do)


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

    _with_conn(_do)


def list_meetings() -> list[dict]:
    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM meetings ORDER BY created_at DESC")
            return [dict(row) for row in cur.fetchall()]

    rows = _with_conn(_do)
    for row in rows:
        row["created_at"] = row["created_at"].strftime("%Y-%m-%dT%H:%M:%S")
    return rows


def get_meeting(meeting_id: str) -> dict | None:
    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM meetings WHERE id = %s", (meeting_id,))
            row = cur.fetchone()
        return dict(row) if row else None

    row = _with_conn(_do)
    if row is None:
        return None
    row["created_at"] = row["created_at"].strftime("%Y-%m-%dT%H:%M:%S")
    return row
