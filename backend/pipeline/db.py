import os
import threading

import psycopg2

# satu koneksi dan lock bersama untuk semua modul store (Supabase jauh, koneksi baru ~1,7 detik)
_conn = None
_lock = threading.Lock()
_schemas: list[str] = []
_schemas_applied = False


def register_schema(sql: str) -> None:
    """Panggil saat import dengan perintah CREATE TABLE / ALTER TABLE ... IF NOT EXISTS milik sebuah modul,
    with_conn() menjalankannya sekali per koneksi."""
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
    """Jalankan fn(conn) di koneksi bersama, satu pemanggil sekali waktu. Menyambung ulang dan mencoba lagi sekali kalau
    koneksi mati (pooler Supabase menutup koneksi yang menganggur). autocommit menyala supaya SELECT tidak pernah
    meninggalkan sesi idle-in-transaction."""
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
