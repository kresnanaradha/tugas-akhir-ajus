"""/auth/*: daftar, masuk, keluar, profil sendiri, lupa dan ganti password."""

import psycopg2.errors
from flask import Blueprint, current_app, jsonify, request, session
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from pipeline import auth_store, mailer

from . import common
from .common import login_required

bp = Blueprint("auth", __name__)


@bp.post("/auth/register")
def auth_register():
    data = request.get_json(force=True) or {}
    email, password, name = data.get("email"), data.get("password"), data.get("name")
    if not email or not password or not name:
        return jsonify({"error": "email, password, dan name wajib diisi"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password minimal 8 karakter"}), 400

    try:
        user = auth_store.create_user(email, password, name)
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "Email sudah terdaftar"}), 409

    session["user_id"] = user["id"]
    session["role"] = user["role"]
    return jsonify(user)


@bp.post("/auth/login")
def auth_login():
    data = request.get_json(force=True) or {}
    email, password = data.get("email"), data.get("password")
    if not email or not password:
        return jsonify({"error": "email dan password wajib diisi"}), 400

    user = auth_store.verify_login(email, password)
    if user is None:
        return jsonify({"error": "Email atau password salah"}), 401
    if not user["active"]:
        return jsonify({"error": "Akun dinonaktifkan. Hubungi admin."}), 403

    session["user_id"] = user["id"]
    session["role"] = user["role"]
    return jsonify(user)


@bp.post("/auth/logout")
def auth_logout():
    session.clear()
    return jsonify({"ok": True})


@bp.get("/auth/me")
def auth_me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Belum login"}), 401
    user = auth_store.get_user(user_id)
    if user is None or not user["active"]:
        # baris user sudah hilang atau dinonaktifkan, buang cookie yang basi
        session.clear()
        return jsonify({"error": "Belum login"}), 401
    return jsonify(user)


@bp.patch("/auth/me")
@login_required
def update_own_profile():
    """Ubah profil sendiri. Hanya kolom yang dikirim yang berubah."""
    data = request.get_json(silent=True) or {}
    name, email, phone = data.get("name"), data.get("email"), data.get("phone")
    if name is not None and not str(name).strip():
        return jsonify({"error": "Nama tidak boleh kosong"}), 400
    if email is not None and not str(email).strip():
        return jsonify({"error": "Email tidak boleh kosong"}), 400
    try:
        user = auth_store.update_user(
            session["user_id"],
            name=str(name).strip() if name is not None else None,
            email=str(email).strip() if email is not None else None,
            phone=str(phone).strip() if phone is not None else None,
            email_notifications=data["email_notifications"] if "email_notifications" in data else None,
        )
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "Email sudah dipakai akun lain"}), 409
    return jsonify(user)


@bp.post("/auth/me/deactivate")
@login_required
def deactivate_own_account():
    """Nonaktifkan, bukan hapus (rapat menunjuk ke baris user), lalu logout."""
    auth_store.update_user(session["user_id"], active=False)
    session.clear()
    return jsonify({"ok": True})


_RESET_TTL_S = 3600


_reset_serializer = lambda: URLSafeTimedSerializer(current_app.secret_key, salt="password-reset")


@bp.post("/auth/forgot")
def forgot_password():
    """Selalu menjawab ok supaya tidak bisa dipakai mencari email yang terdaftar. Token ditandatangani dan terikat ke
    hash password saat ini, jadi hanya berlaku sekali."""
    email = ((request.get_json(silent=True) or {}).get("email") or "").strip().lower()
    row = auth_store.get_row_by_email(email) if email else None
    if row and row["active"]:
        token = _reset_serializer().dumps({"u": row["id"], "h": row["password_hash"][-16:]})
        try:
            mailer.send_password_reset_email(row["email"], row["name"], f"{common.LOCAL_FRONTEND_URL}/reset-password/{token}")
        except Exception as e:
            print(f"[auth] reset email to {row['email']} failed: {e}")
    return jsonify({"ok": True})


@bp.post("/auth/reset")
def reset_password():
    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""
    if len(password) < 8:
        return jsonify({"error": "Password baru minimal 8 karakter"}), 400
    try:
        payload = _reset_serializer().loads(data.get("token") or "", max_age=_RESET_TTL_S)
    except (BadSignature, SignatureExpired):
        return jsonify({"error": "Tautan tidak valid atau sudah kedaluwarsa. Minta tautan baru."}), 400
    row = auth_store.get_row(payload["u"])
    if not row or not row["active"] or row["password_hash"][-16:] != payload["h"]:
        return jsonify({"error": "Tautan tidak valid atau sudah kedaluwarsa. Minta tautan baru."}), 400
    auth_store.set_password(row["id"], password)
    return jsonify({"ok": True})


@bp.post("/auth/me/password")
@login_required
def change_own_password():
    """Butuh password saat ini, beda dengan reset oleh admin."""
    data = request.get_json(silent=True) or {}
    current_password, new_password = data.get("current_password"), data.get("new_password")
    if not current_password or not new_password:
        return jsonify({"error": "Password saat ini dan password baru wajib diisi"}), 400
    if len(new_password) < 8:
        return jsonify({"error": "Password baru minimal 8 karakter"}), 400
    me = auth_store.get_user(session["user_id"])
    if auth_store.verify_login(me["email"], current_password) is None:
        return jsonify({"error": "Password saat ini salah"}), 403
    auth_store.set_password(session["user_id"], new_password)
    return jsonify({"ok": True})
