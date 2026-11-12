"""Dipakai banyak route: konfigurasi, cek login, hak lihat/ubah rapat, dan kuota paket."""

import os
import time
from datetime import datetime, timedelta
from functools import wraps

from flask import Response, jsonify, session

from pipeline import auth_store, billing_store, meetings_store


# kosong atau 0 = tanpa batas, rekaman berhenti sendiri (host keluar, bot sendirian, hening)
MAX_DURATION_MIN = float(os.getenv("MAX_RECORDING_DURATION_MINUTES") or 0) or None


# tempat frontend Expo berjalan, dipakai untuk redirect dan tautan di email
LOCAL_FRONTEND_URL = os.getenv("LOCAL_FRONTEND_URL", "http://localhost:8081")


# Xendit hanya menerima url kembali https, jadi checkout kembali ke /billing/return milik kita
# (lewat tunnel publik seperti ngrok), yang lalu mengarahkan ke frontend
PUBLIC_URL = os.getenv("PUBLIC_URL")


# user_id -> (aktif, waktu_cek). Menghemat satu query db per request, jadi sesi user yang dinonaktifkan
# mati dalam 30 detik. ponytail: cache per proses
active_cache: dict = {}


def user_is_active(user_id: str) -> bool:
    cached = active_cache.get(user_id)
    if cached and time.time() - cached[1] < 30:
        return cached[0]
    active = auth_store.is_active(user_id)
    active_cache[user_id] = (active, time.time())
    return active


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error": "Belum login"}), 401
        if not user_is_active(session["user_id"]):
            session.clear()
            return jsonify({"error": "Akun dinonaktifkan"}), 401
        return view(*args, **kwargs)

    return wrapped


def super_admin_required(view):
    @login_required
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "super_admin":
            return jsonify({"error": "Butuh akses super admin"}), 403
        return view(*args, **kwargs)

    return wrapped


def can_view_meeting(record: dict) -> bool:
    """Pemilik, super admin, penonton lewat tautan, atau teman satu team kalau pemilik membagikannya ke team."""
    uid = session["user_id"]
    if session.get("role") == "super_admin" or record.get("user_id") == uid:
        return True
    if meetings_store.is_viewer(record["id"], uid):
        return True
    if record.get("shared_with_team") and record.get("user_id"):
        owner, me = auth_store.get_user(record["user_id"]), auth_store.get_user(uid)
        return bool(owner and me and owner["team_id"] and owner["team_id"] == me["team_id"])
    return False


def can_edit_meeting(record: dict) -> bool:
    return session.get("role") == "super_admin" or record.get("user_id") == session["user_id"]


NOT_FOUND = ({"error": "Meeting not found"}, 404)


NOT_OWNER = ({"error": "Hanya pemilik rapat yang bisa mengubahnya"}, 403)


def load_meeting(meeting_id, edit=False):
    """(record, None), atau (None, respons error). edit=True juga butuh pemilik atau super admin."""
    record = meetings_store.get_meeting(meeting_id)
    if record is None or not can_view_meeting(record):
        return None, (jsonify(NOT_FOUND[0]), NOT_FOUND[1])
    if edit and not can_edit_meeting(record):
        return None, (jsonify(NOT_OWNER[0]), NOT_OWNER[1])
    return record, None


def pdf(data, filename):
    return Response(data, mimetype="application/pdf", headers={"Content-Disposition": f"attachment; filename={filename}"})


def plan_limits(user_id: str) -> dict:
    plan = billing_store.effective_plan(user_id)[0]
    return billing_store.PLAN_LIMITS.get(plan, billing_store.PLAN_LIMITS["free"])


def week_start() -> datetime:
    """Minggu terakhir pukul 08:00 waktu server (WITA), saat kuota mingguan di-reset."""
    now = datetime.now()
    start = (now - timedelta(days=(now.weekday() + 1) % 7)).replace(hour=8, minute=0, second=0, microsecond=0)
    return start if start <= now else start - timedelta(days=7)


def weekly_quota(user_id: str) -> dict | None:
    """None kalau paketnya tidak punya batas mingguan, selain itu {limit, used, remaining, resets_at}."""
    limit = plan_limits(user_id)["minutes_per_week"]
    if limit is None:
        return None
    start = week_start()
    used = meetings_store.recorded_minutes_since(user_id, start)
    return {
        "limit": limit,
        "used": round(used, 1),
        "remaining": round(max(limit - used, 0), 1),
        "resets_at": (start + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S"),
    }


def kb_allowed(user_id: str) -> bool:
    """Knowledge Base hanya untuk Pro/Team."""
    return billing_store.effective_plan(user_id)[0] != "free"


def check_meeting_quota(user_id: str) -> str | None:
    """Pesan error kalau user ini kehabisan jatah rapat bulan ini, selain itu None. Upload ikut dihitung."""
    limit = plan_limits(user_id)["meetings_per_month"]
    if limit is None:
        return None
    used = meetings_store.count_own_this_month(user_id)
    if used >= limit:
        return f"Paket Free dibatasi {limit} rapat per bulan (sudah terpakai {used}). Upgrade ke Pro untuk rapat tanpa batas."
    return None
