import os
import threading

import psycopg2

# Shared by every store module (meetings_store.py, billing_store.py, ...) —
# one connection, one lock, instead of each module opening its own (Supabase
# is remote, ~1.7s per fresh connect — not something to pay per module).
_conn = None
_lock = threading.Lock()
_schemas: list[str] = []
_schemas_applied = False


def register_schema(sql: str) -> None:
    """Call at import time with a module's CREATE TABLE IF NOT EXISTS / ALTER
    TABLE ADD COLUMN IF NOT EXISTS statements. Applied once per connection
    (and again after a reconnect) by with_conn() below, so no caller has to
    manage table setup itself."""
    _schemas.append(sql)


def _apply_schemas(conn) -> None:
    global _schemas_applied
    if _schemas_applied:
        return
    with conn.cursor() as cur:
        for sql in _schemas:
            cur.execute(sql)
    _schemas_applied = True


def with_conn(fn):
    """Runs fn(conn) against the shared connection (one caller at a time),
    reconnecting once and retrying if it turned out to be dead (Supabase's
    pooler can close connections that sit idle for a while). autocommit is
    on so a SELECT-only caller never leaves an idle-in-transaction session
    open (that bug — see git history — is why this isn't optional)."""
    global _conn, _schemas_applied
    with _lock:
        if _conn is None:
            _conn = psycopg2.connect(os.environ["DATABASE_URL"])
            _conn.autocommit = True
            _apply_schemas(_conn)
        try:
            return fn(_conn)
        except psycopg2.OperationalError:
            _conn = psycopg2.connect(os.environ["DATABASE_URL"])
            _conn.autocommit = True
            _schemas_applied = False
            _apply_schemas(_conn)
            return fn(_conn)
