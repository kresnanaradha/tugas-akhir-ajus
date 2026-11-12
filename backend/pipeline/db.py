import os
import threading
import time

import psycopg2
import psycopg2.extras

# satu koneksi dan lock bersama untuk semua modul store (Supabase jauh, koneksi baru ~1,7 detik)
_conn = None
_lock = threading.Lock()
_schemas: list[str] = []
_schemas_applied = False

# pooler Supabase menutup koneksi yang menganggur, dan koneksi baru ke Supabase 1,7 sampai 3 detik. Ping ringan tiap
# _KEEPALIVE_S detik menjaganya tetap hidup, jadi permintaan user tidak membayar sambungan ulang itu
_KEEPALIVE_S = 90
_keepalive_started = False


def _keepalive_loop() -> None:
    def _ping(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT 1")

    while True:
        time.sleep(_KEEPALIVE_S)
        try:
            with_conn(_ping)
        except Exception as e:
            print(f"[db] keepalive gagal: {e}")


def register_schema(sql: str) -> None:
    """Panggil saat import dengan perintah CREATE TABLE / ALTER TABLE ... IF NOT EXISTS milik sebuah modul,
    with_conn() menjalankannya sekali per koneksi."""
    _schemas.append(sql)


# Foreign key dan RLS, dijalankan setelah semua CREATE TABLE supaya database baru (proyek Supabase lain, VPS) langsung
# sama dengan produksi. Daftar yang sama ada di migrations/001_fk_rls.sql, ubah keduanya bersamaan. Aman dijalankan tiap
# start: constraint dan RLS dilewati kalau sudah ada, tabel yang belum dibuat proses ini dilewati (transkriber tidak
# memuat tabel team, proses berikutnya yang menyusul), dan NOT VALID tidak memindai baris lama jadi baris yatim tidak
# membuat start gagal (VALIDATE tetap lewat migrasi). Kegagalan hanya dicatat, tidak menghentikan aplikasi.
_INTEGRITY_SQL = """
DO $$
DECLARE
    fk record;
    t text;
BEGIN
    FOR fk IN
        SELECT * FROM (VALUES
            ('fk_meetings_user',      'meetings',        'user_id',    'users',    'id', 'NO ACTION'),
            ('fk_viewers_meeting',    'meeting_viewers', 'meeting_id', 'meetings', 'id', 'CASCADE'),
            ('fk_viewers_user',       'meeting_viewers', 'user_id',    'users',    'id', 'CASCADE'),
            ('fk_subscriptions_user', 'subscriptions',   'id',         'users',    'id', 'CASCADE'),
            ('fk_users_team',         'users',           'team_id',    'teams',    'id', 'SET NULL'),
            ('fk_teams_owner',        'teams',           'owner_id',   'users',    'id', 'NO ACTION'),
            ('fk_invites_team',       'team_invites',    'team_id',    'teams',    'id', 'CASCADE'),
            ('fk_invites_creator',    'team_invites',    'created_by', 'users',    'id', 'NO ACTION'),
            ('fk_api_usage_meeting',  'api_usage',       'meeting_id', 'meetings', 'id', 'SET NULL'),
            ('fk_replicate_meeting',  'replicate_usage', 'meeting_id', 'meetings', 'id', 'SET NULL')
        ) AS v(name, tbl, col, ref_tbl, ref_col, on_delete)
    LOOP
        IF to_regclass('public.' || fk.tbl) IS NOT NULL
           AND to_regclass('public.' || fk.ref_tbl) IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = fk.name) THEN
            BEGIN
                EXECUTE format(
                    'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES %I (%I) ON DELETE %s NOT VALID',
                    fk.tbl, fk.name, fk.col, fk.ref_tbl, fk.ref_col, fk.on_delete);
            EXCEPTION WHEN OTHERS THEN
                RAISE WARNING 'FK % dilewati: %', fk.name, SQLERRM;
            END;
        END IF;
    END LOOP;
    FOREACH t IN ARRAY ARRAY['users', 'meetings', 'meeting_viewers', 'subscriptions',
                             'teams', 'team_invites', 'api_usage', 'replicate_usage']
    LOOP
        IF to_regclass('public.' || t) IS NOT NULL
           AND NOT (SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass('public.' || t)) THEN
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        END IF;
    END LOOP;
END $$;
"""


def _apply_schemas(conn) -> None:
    global _schemas_applied
    if _schemas_applied:
        return
    with conn.cursor() as cur:
        for sql in _schemas:
            cur.execute(sql)
        try:
            cur.execute(_INTEGRITY_SQL)
        except Exception as e:
            print(f"[db] FK/RLS tidak terpasang: {e}")
    _schemas_applied = True


def _query(sql: str, params, fetch):
    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return fetch(cur)

    return with_conn(_do)


# pembantu untuk query tunggal, dipakai semua modul store. Baris keluar sebagai dict (nama kolom -> nilai)
def execute(sql: str, params=None) -> None:
    _query(sql, params, lambda cur: None)


def fetch_one(sql: str, params=None) -> dict | None:
    return _query(sql, params, lambda cur: dict(row) if (row := cur.fetchone()) else None)


def fetch_all(sql: str, params=None) -> list[dict]:
    return _query(sql, params, lambda cur: [dict(r) for r in cur.fetchall()])


def fetch_value(sql: str, params=None):
    """Kolom pertama baris pertama (COUNT, SUM, RETURNING id), None kalau tidak ada baris."""
    row = fetch_one(sql, params)
    return next(iter(row.values())) if row else None


def with_conn(fn):
    """Jalankan fn(conn) di koneksi bersama, satu pemanggil sekali waktu. Menyambung ulang dan mencoba lagi sekali kalau
    koneksi mati (pooler Supabase menutup koneksi yang menganggur). autocommit menyala supaya SELECT tidak pernah
    meninggalkan sesi idle-in-transaction."""
    global _conn, _schemas_applied, _keepalive_started
    with _lock:
        if _conn is None:
            _conn = psycopg2.connect(os.environ["DATABASE_URL"])
            _conn.autocommit = True
            _apply_schemas(_conn)
            if not _keepalive_started:
                _keepalive_started = True
                threading.Thread(target=_keepalive_loop, daemon=True, name="db-keepalive").start()
        try:
            return fn(_conn)
        except psycopg2.OperationalError:
            _conn = psycopg2.connect(os.environ["DATABASE_URL"])
            _conn.autocommit = True
            _schemas_applied = False
            _apply_schemas(_conn)
            return fn(_conn)
