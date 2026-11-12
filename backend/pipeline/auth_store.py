import uuid
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from .db import execute, fetch_all, fetch_one, fetch_value, register_schema

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMP NOT NULL
);
-- user yang dinonaktifkan tidak bisa login tapi barisnya tetap ada (rapat menunjuk ke users.id). NULL dianggap aktif
ALTER TABLE users ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE;
-- info kontak opsional, diedit di Pengaturan
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT;
-- kirim email ke user saat ringkasan siap. NULL dianggap nyala
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_notifications BOOLEAN DEFAULT TRUE;
-- satu team per user, team_id NULL = tidak punya team. team_role ('admin' atau 'member') hanya bermakna kalau ada team_id
ALTER TABLE users ADD COLUMN IF NOT EXISTS team_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS team_role TEXT;
"""
register_schema(_TABLE_SQL)

# 'super_admin' adalah peran dashboard internal, 'user' semua yang lain
ROLES = ("user", "super_admin")


def _public(row: dict) -> dict:
    """Data user tanpa password_hash, ini yang keluar dari modul."""
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "phone": row.get("phone"),
        "role": row["role"],
        "active": row.get("active") is not False,
        "email_notifications": row.get("email_notifications") is not False,
        "team_id": row.get("team_id"),
        "team_role": row.get("team_role"),
    }


def create_user(email: str, password: str, name: str, role: str = "user") -> dict:
    """Melempar UniqueViolation kalau email sudah dipakai (pemanggil mengubahnya jadi 409)."""
    user_id = uuid.uuid4().hex
    record = {
        "id": user_id,
        "email": email.strip().lower(),
        "password_hash": generate_password_hash(password),
        "name": name.strip(),
        "role": role,
        "created_at": datetime.now(),
    }

    execute(
        "INSERT INTO users (id, email, password_hash, name, role, created_at) "
        "VALUES (%(id)s, %(email)s, %(password_hash)s, %(name)s, %(role)s, %(created_at)s)",
        record,
    )
    return _public(record)


def get_user(user_id: str) -> dict | None:
    row = get_row(user_id)
    return _public(row) if row else None


def list_users() -> list[dict]:
    """Semua user beserta jumlah rapat yang dimiliki, terbaru dulu (UI admin)."""
    rows = fetch_all(
        "SELECT u.*, (SELECT COUNT(*) FROM meetings m WHERE m.user_id = u.id) AS meeting_count "
        "FROM users u ORDER BY u.created_at DESC"
    )
    return [
        {**_public(r), "meeting_count": r["meeting_count"], "created_at": r["created_at"].strftime("%Y-%m-%dT%H:%M:%S")}
        for r in rows
    ]


def update_user(
    user_id: str,
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    role: str | None = None,
    active: bool | None = None,
    email_notifications: bool | None = None,
) -> dict | None:
    """Melempar UniqueViolation kalau email milik akun lain."""
    if email is not None:
        email = email.strip().lower()
    fields = {
        k: v
        for k, v in (
            ("name", name),
            ("email", email),
            ("phone", phone),
            ("role", role),
            ("active", active),
            ("email_notifications", email_notifications),
        )
        if v is not None
    }
    if fields:
        execute(f"UPDATE users SET {', '.join(f'{c} = %s' for c in fields)} WHERE id = %s", (*fields.values(), user_id))
    return get_user(user_id)


def get_row_by_email(email: str) -> dict | None:
    """Baris mentah dengan password_hash, untuk pemakaian internal (token reset, login)."""
    return fetch_one("SELECT * FROM users WHERE email = %s", (email.strip().lower(),))


def get_row(user_id: str) -> dict | None:
    return fetch_one("SELECT * FROM users WHERE id = %s", (user_id,))


def set_password(user_id: str, password: str) -> None:
    execute("UPDATE users SET password_hash = %s WHERE id = %s", (generate_password_hash(password), user_id))


def is_active(user_id: str) -> bool:
    user = get_user(user_id)
    return bool(user and user["active"])


def count_users() -> int:
    return fetch_value("SELECT COUNT(*) FROM users")


def verify_login(email: str, password: str) -> dict | None:
    """User kalau email dan password cocok, selain itu None. Satu fungsi sengaja, supaya pemanggil tidak bisa membedakan
    "user tidak ada" dari "password salah"."""
    row = get_row_by_email(email)
    if row is None or not check_password_hash(row["password_hash"], password):
        return None
    return _public(row)
