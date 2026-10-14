import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv

# muat .env sebelum import modul lokal, sebagian membaca env var saat import
load_dotenv()

import psycopg2.errors
import requests
from flask import Flask, Response, jsonify, redirect, request, session
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.exceptions import RequestEntityTooLarge

from bots.google_meet import GoogleMeetBot
from bots.zoom import ZoomBot
from pipeline import admin_stats, artifacts, auth_store, billing_store, job_queue, knowledge_base, mailer, report_pdf, report_stats, storage, team_store
from pipeline.meetings_store import (
    add_viewer,
    count_own_this_month,
    delete_meeting,
    find_meeting_by_url,
    get_meeting,
    is_viewer,
    list_meetings,
    recorded_minutes_since,
    start_meeting,
    update_meeting,
)
from pipeline.process import process_recording
from pipeline.summarize import compare_meetings, short_summary, summarize
from pipeline.xendit_client import create_subscription_session, deactivate_recurring_plan

app = Flask(__name__)
# menandatangani cookie sesi, wajib ada supaya tidak ada default yang gampang ditebak
app.secret_key = os.environ["SECRET_KEY"]
# kosong atau 0 = tanpa batas, rekaman berhenti sendiri (host keluar, bot sendirian, hening)
MAX_DURATION_MIN = float(os.getenv("MAX_RECORDING_DURATION_MINUTES") or 0) or None
# jaga-jaga upload yang terlalu besar, error json supaya frontend bisa membacanya
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1GB


@app.errorhandler(RequestEntityTooLarge)
def _file_too_large(_e):
    return jsonify({"error": "File terlalu besar (maks 1GB)"}), 413


@app.after_request
def _add_cors_headers(response):
    # supaya dev server Expo (port lain) bisa memanggil kita dengan cookie. Hanya untuk dev, pakai
    # daftar izin, bukan memantulkan origin apa saja, sebelum dirilis ke publik
    origin = request.headers.get("Origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


# user_id -> (aktif, waktu_cek). Menghemat satu query db per request, jadi sesi user yang dinonaktifkan
# mati dalam 30 detik. ponytail: cache per proses
_active_cache: dict = {}


def _user_is_active(user_id: str) -> bool:
    cached = _active_cache.get(user_id)
    if cached and time.time() - cached[1] < 30:
        return cached[0]
    active = auth_store.is_active(user_id)
    _active_cache[user_id] = (active, time.time())
    return active


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error": "Belum login"}), 401
        if not _user_is_active(session["user_id"]):
            session.clear()
            return jsonify({"error": "Akun dinonaktifkan"}), 401
        return view(*args, **kwargs)

    return wrapped


def _can_view_meeting(record: dict) -> bool:
    """Pemilik, super admin, penonton lewat tautan, atau teman satu team kalau pemilik membagikannya ke team."""
    uid = session["user_id"]
    if session.get("role") == "super_admin" or record.get("user_id") == uid:
        return True
    if is_viewer(record["id"], uid):
        return True
    if record.get("shared_with_team") and record.get("user_id"):
        owner, me = auth_store.get_user(record["user_id"]), auth_store.get_user(uid)
        return bool(owner and me and owner["team_id"] and owner["team_id"] == me["team_id"])
    return False


def _can_edit_meeting(record: dict) -> bool:
    return session.get("role") == "super_admin" or record.get("user_id") == session["user_id"]


_NOT_FOUND = ({"error": "Meeting not found"}, 404)
_NOT_OWNER = ({"error": "Hanya pemilik rapat yang bisa mengubahnya"}, 403)


def _load_meeting(meeting_id, edit=False):
    """(record, None), atau (None, respons error). edit=True juga butuh pemilik atau super admin."""
    record = get_meeting(meeting_id)
    if record is None or not _can_view_meeting(record):
        return None, (jsonify(_NOT_FOUND[0]), _NOT_FOUND[1])
    if edit and not _can_edit_meeting(record):
        return None, (jsonify(_NOT_OWNER[0]), _NOT_OWNER[1])
    return record, None


def _pdf(data, filename):
    return Response(data, mimetype="application/pdf", headers={"Content-Disposition": f"attachment; filename={filename}"})


def super_admin_required(view):
    @login_required
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "super_admin":
            return jsonify({"error": "Butuh akses super admin"}), 403
        return view(*args, **kwargs)

    return wrapped


@app.post("/auth/register")
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


@app.post("/auth/login")
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


@app.post("/auth/logout")
def auth_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/auth/me")
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


@app.patch("/auth/me")
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


@app.post("/auth/me/deactivate")
@login_required
def deactivate_own_account():
    """Nonaktifkan, bukan hapus (rapat menunjuk ke baris user), lalu logout."""
    auth_store.update_user(session["user_id"], active=False)
    session.clear()
    return jsonify({"ok": True})


_RESET_TTL_S = 3600
_reset_serializer = lambda: URLSafeTimedSerializer(app.secret_key, salt="password-reset")


@app.post("/auth/forgot")
def forgot_password():
    """Selalu menjawab ok supaya tidak bisa dipakai mencari email yang terdaftar. Token ditandatangani dan terikat ke
    hash password saat ini, jadi hanya berlaku sekali."""
    email = ((request.get_json(silent=True) or {}).get("email") or "").strip().lower()
    row = auth_store.get_row_by_email(email) if email else None
    if row and row["active"]:
        token = _reset_serializer().dumps({"u": row["id"], "h": row["password_hash"][-16:]})
        try:
            mailer.send_password_reset_email(row["email"], row["name"], f"{LOCAL_FRONTEND_URL}/reset-password/{token}")
        except Exception as e:
            print(f"[auth] reset email to {row['email']} failed: {e}")
    return jsonify({"ok": True})


@app.post("/auth/reset")
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


@app.post("/auth/me/password")
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


# format yang bisa didecode ffmpeg
UPLOAD_EXTENSIONS = {".webm", ".mp4", ".mp3", ".wav", ".m4a", ".ogg"}

# sengaja longgar, hanya menangkap tautan yang bukan rapat sebelum browser dijalankan (frontend juga mengecek)
MEETING_URL_PATTERNS = {
    "google_meet": re.compile(r"^https?://meet\.google\.com/[a-z0-9-]+", re.I),
    "zoom": re.compile(r"^https?://([a-z0-9-]+\.)?zoom\.us/(j|wc/join)/\d+", re.I),
}
MEETING_PLATFORM_LABEL = {"google_meet": "Google Meet", "zoom": "Zoom"}


# job join yang sedang jalan, di memori (hilang saat restart). phase: starting | processing | failed
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _run_join_job(job_id: str, bot, platform: str, title: str, num_speakers: int | None):
    started_at = time.time()
    try:
        local_recording_path = bot.join()
    except Exception as e:
        with _jobs_lock:
            _jobs[job_id].update(phase="failed", error=str(e))
        update_meeting(job_id, status="failed")
        return
    # waktu yang dipakai merekam, bukan seluruh proses join (browser mulai, menunggu di lobi)
    if bot.record_started_at and bot.record_ended_at:
        duration_minutes = round((bot.record_ended_at - bot.record_started_at) / 60, 1)
    else:
        duration_minutes = round((time.time() - started_at) / 60, 1)

    with _jobs_lock:
        _jobs[job_id]["phase"] = "processing"

    # unggah, lalu serahkan ke transkriber lewat Redis (whisper satu container dengan chrome
    # kehabisan memori)
    recording_key = storage.upload_recording(local_recording_path, job_id)
    # Menit mingguan Free untuk pemrosesan AI, bukan batas rekaman. Rekaman yang lebih panjang dari sisa
    # disimpan tapi tidak diproses (semua atau tidak sama sekali). Dicek sebelum menit rapat ini disimpan
    # supaya tidak terhitung terhadap dirinya sendiri.
    owner_id = (get_meeting(job_id) or {}).get("user_id")
    weekly = _weekly_quota(owner_id) if owner_id else None
    if weekly and duration_minutes > weekly["remaining"]:
        update_meeting(job_id, status="limited", recording=recording_key, duration_minutes=duration_minutes)
        _send_unprocessed_email(owner_id, job_id, title, duration_minutes, weekly)
    else:
        update_meeting(job_id, status="processing", recording=recording_key, duration_minutes=duration_minutes)
        job_queue.enqueue_transcription(job_id, recording_key, num_speakers)

    # buang job-nya supaya GET /jobs/<id> 404, frontend lalu memantau baris rapatnya
    with _jobs_lock:
        _jobs.pop(job_id, None)


def _send_unprocessed_email(owner_id: str, meeting_id: str, title: str, duration_minutes: float, weekly: dict) -> None:
    """Beri tahu pemilik bahwa rekaman disimpan tapi belum diproses AI (sebisanya)."""
    try:
        owner = auth_store.get_user(owner_id)
        if not owner["email_notifications"]:
            return  # toggle di Pengaturan berlaku untuk semua email kecuali reset password dan undangan
        mailer.send_meeting_unprocessed_email(
            owner["email"], owner["name"], title, duration_minutes, weekly["remaining"], weekly["limit"],
            f"{LOCAL_FRONTEND_URL}/rapat/{meeting_id}", f"{LOCAL_FRONTEND_URL}/billing",
        )
    except Exception as e:
        print(f"[quota] unprocessed-meeting email failed: {e}")


def _plan_limits(user_id: str) -> dict:
    plan = billing_store.effective_plan(user_id)[0]
    return billing_store.PLAN_LIMITS.get(plan, billing_store.PLAN_LIMITS["free"])


def _week_start() -> datetime:
    """Minggu terakhir pukul 08:00 waktu server (WITA), saat kuota mingguan di-reset."""
    now = datetime.now()
    start = (now - timedelta(days=(now.weekday() + 1) % 7)).replace(hour=8, minute=0, second=0, microsecond=0)
    return start if start <= now else start - timedelta(days=7)


def _weekly_quota(user_id: str) -> dict | None:
    """None kalau paketnya tidak punya batas mingguan, selain itu {limit, used, remaining, resets_at}."""
    limit = _plan_limits(user_id)["minutes_per_week"]
    if limit is None:
        return None
    start = _week_start()
    used = recorded_minutes_since(user_id, start)
    return {
        "limit": limit,
        "used": round(used, 1),
        "remaining": round(max(limit - used, 0), 1),
        "resets_at": (start + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _kb_allowed(user_id: str) -> bool:
    """Knowledge Base hanya untuk Pro/Team."""
    return billing_store.effective_plan(user_id)[0] != "free"


def _check_meeting_quota(user_id: str) -> str | None:
    """Pesan error kalau user ini kehabisan jatah rapat bulan ini, selain itu None. Upload ikut dihitung."""
    limit = _plan_limits(user_id)["meetings_per_month"]
    if limit is None:
        return None
    used = count_own_this_month(user_id)
    if used >= limit:
        return f"Paket Free dibatasi {limit} rapat per bulan (sudah terpakai {used}). Upgrade ke Pro untuk rapat tanpa batas."
    return None


def _join(bot_cls, platform: str, title: str):
    data = request.get_json(force=True) or {}
    url = data.get("url")
    name = data.get("name") or "Notulis Bot"
    # tebakan opsional untuk diarization, abaikan kalau aneh
    try:
        num_speakers = int(data["num_speakers"]) if data.get("num_speakers") else None
    except (TypeError, ValueError):
        num_speakers = None
    if not url:
        return jsonify({"error": "url is required"}), 400
    url = url.strip()
    if not MEETING_URL_PATTERNS[platform].match(url):
        return jsonify({"error": f"'{url}' bukan tautan {MEETING_PLATFORM_LABEL[platform]} yang valid"}), 400

    # sudah ada bot di tautan ini (atau pernah direkam): bagikan rapat itu, jangan
    # kirim bot kedua
    existing = find_meeting_by_url(url)
    if existing:
        if existing.get("user_id") != session["user_id"]:
            add_viewer(existing["id"], session["user_id"])
        return jsonify({"job_id": existing["id"], "shared": True})

    quota_error = _check_meeting_quota(session["user_id"])
    if quota_error:
        return jsonify({"error": quota_error}), 402

    # di sini hanya batas teknis. Menit mingguan tidak menghentikan rekaman, hanya menentukan
    # setelahnya apakah dapat AI (lihat _run_join_job)
    plan_cap = _plan_limits(session["user_id"])["max_duration_minutes"]
    caps = [c for c in (MAX_DURATION_MIN, plan_cap) if c is not None]
    max_duration = min(caps) if caps else None

    job_id = uuid.uuid4().hex
    # perubahan status disimpan ke baris rapat supaya daftar bisa menampilkan "Sedang Merekam"
    bot = bot_cls(url, name, max_duration, on_status_change=lambda status: update_meeting(job_id, status=status))
    with _jobs_lock:
        # satu bot per display, dua bot akan merekam jendela satu sama lain
        if any(j["phase"] in ("starting", "processing") for j in _jobs.values()):
            return jsonify({"error": "Rapat lain sedang direkam. Tunggu sampai selesai sebelum memulai yang baru."}), 409
        _jobs[job_id] = {"phase": "starting", "bot": bot, "error": None}

    start_meeting(job_id, platform, title, estimated_participants=num_speakers, url=url, user_id=session["user_id"])

    # join() menunggu sampai rapat selesai, jadi dijalankan di thread dan frontend memantau /jobs/<id>
    threading.Thread(target=_run_join_job, args=(job_id, bot, platform, title, num_speakers), daemon=True).start()

    return jsonify({"job_id": job_id})


@app.get("/jobs/<job_id>")
@login_required
def job_status(job_id):
    record = get_meeting(job_id)
    if record is not None and not _can_view_meeting(record):
        return jsonify({"error": "Job not found"}), 404
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return jsonify({"error": "Job not found"}), 404
        phase = job["phase"]

        if phase == "starting":
            bot = job["bot"]
            resp = {"status": bot.status}  # "joining" | "recording" | "stopping"
            if bot.status == "recording" and bot.record_started_at:
                resp["elapsed_seconds"] = int(time.time() - bot.record_started_at)
            return jsonify(resp)

        if phase == "processing":
            return jsonify({"status": "processing"})
        return jsonify({"status": "failed", "error": job["error"]})


@app.post("/jobs/<job_id>/stop")
@login_required
def job_stop(job_id):
    """Hentikan rekaman lebih awal. Yang sudah terekam tetap diproses seperti biasa."""
    record = get_meeting(job_id)
    if record is not None and not _can_edit_meeting(record):
        return jsonify(_NOT_OWNER[0]), _NOT_OWNER[1]
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None or job["phase"] != "starting":
            return jsonify({"error": "Job not found or no longer recording"}), 404
        job["bot"].stop_event.set()
    return jsonify({"status": "stopping"})


@app.post("/google/join")
@login_required
def google_join():
    return _join(GoogleMeetBot, "google_meet", "Rapat Google Meet")


@app.post("/zoom/join")
@login_required
def zoom_join():
    return _join(ZoomBot, "zoom", "Rapat Zoom")


@app.get("/meetings")
@login_required
def meetings():
    return jsonify(list_meetings(session["user_id"]))


@app.get("/knowledge-base/search")
@login_required
def knowledge_base_search():
    """Pencarian semantik di rapat yang dimasukkan user ke Knowledge Base, plus satu jawaban singkat dari
    GPT-4o mini. `results` tetap dikembalikan walau jawabannya gagal."""
    if not _kb_allowed(session["user_id"]):
        return jsonify({"error": "Knowledge Base adalah fitur paket Pro/Team. Upgrade untuk memakainya."}), 402

    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"error": "q is required"}), 400

    # hanya rapat yang bisa dilihat user ini dan sudah di-opt in
    allowed = [m["id"] for m in list_meetings(session["user_id"]) if m.get("in_kb")]
    matches = knowledge_base.search(query, allowed)
    results = []
    for m in matches:
        meeting = get_meeting(m["meeting_id"])
        if meeting is None:
            continue  # potongan basi dari rapat yang sudah dihapus, lewati saja jangan error
        results.append(
            {
                "meeting_id": m["meeting_id"],
                "meeting_title": meeting["title"],
                "meeting_created_at": meeting["created_at"],
                "meeting_platform": meeting["platform"],
                "kind": m["kind"],
                "text": m["text"],
                "similarity": m["similarity"],
            }
        )
    return jsonify({"answer": knowledge_base.answer(query, results), "results": results})


@app.get("/meetings/<meeting_id>")
@login_required
def meeting_detail(meeting_id):
    record, error = _load_meeting(meeting_id)
    if error:
        return error

    # rapat yang masih direkam belum punya apa-apa di R2
    if record["recording"]:
        record["transcript"] = artifacts.load_transcript(meeting_id)
        record["fixed_transcript"] = artifacts.load_fixed_transcript(meeting_id)
        record["summary"] = artifacts.load_summary(meeting_id)
        record["segments"] = artifacts.load_segments(meeting_id)  # tidak ada untuk rekaman lama

        info = storage.head(record["recording"])
        if info:
            record["file_size_bytes"] = info["size"]
            record["file_extension"] = os.path.splitext(record["recording"])[1].lstrip(".")

    return jsonify(record)


@app.post("/meetings/<meeting_id>/transcript")
@login_required
def update_transcript(meeting_id):
    """Simpan transkrip yang diedit (dan perbaikan pembicara/teks per baris, urutan sama dengan segments.json),
    lalu buat ulang ringkasan dari situ."""
    record, error = _load_meeting(meeting_id, edit=True)
    if error:
        return error
    if not record["recording"]:
        return jsonify({"error": "Recording not available yet"}), 404

    body = request.get_json(force=True) or {}
    transcript = body.get("transcript")
    line_speakers = body.get("line_speakers") or []
    line_texts = body.get("line_texts") or []
    if not transcript or not transcript.strip():
        return jsonify({"error": "transcript is required"}), 400

    artifacts.save_fixed_transcript(meeting_id, transcript)

    result = {"fixed_transcript": transcript}

    if line_speakers or line_texts:
        segments = artifacts.load_segments(meeting_id)
        if segments:
            changed = False
            if line_speakers and len(segments) == len(line_speakers):
                for seg, label in zip(segments, line_speakers):
                    if label:
                        seg["speaker"] = label
                changed = True
            if line_texts and len(segments) == len(line_texts):
                for seg, text in zip(segments, line_texts):
                    seg["text"] = text
                changed = True
            if changed:
                artifacts.save_segments(meeting_id, segments)
                result["segments"] = segments

    try:
        result["summary"] = summarize(transcript, meeting_id)
    except Exception as e:
        result["summary_error"] = str(e)
    return jsonify(result)


_summary_lock = threading.Lock()


@app.post("/meetings/<meeting_id>/knowledge-base")
@login_required
def meeting_knowledge_base(meeting_id):
    """Masukkan atau keluarkan rapat dari Knowledge Base ({"enabled": bool})."""
    _, error = _load_meeting(meeting_id, edit=True)
    if error:
        return error
    enabled = bool((request.get_json(silent=True) or {}).get("enabled"))
    if enabled:
        # menyalakan butuh Pro/Team, mematikan selalu boleh (turun paket tidak membuat rapat tersangkut)
        if not _kb_allowed(session["user_id"]):
            return jsonify({"error": "Knowledge Base adalah fitur paket Pro/Team. Upgrade untuk memakainya."}), 402
        summary = artifacts.load_summary(meeting_id)
        if summary is None:
            return jsonify({"error": "No summary for this meeting yet"}), 404
        knowledge_base.index_meeting(meeting_id, summary)
    else:
        knowledge_base.remove_meeting(meeting_id)
    update_meeting(meeting_id, in_kb=enabled)
    return jsonify({"in_kb": enabled})


@app.post("/meetings/<meeting_id>/short-summary")
@login_required
def meeting_short_summary(meeting_id):
    """Tambahkan ringkasan singkat ke rapat yang diringkas sebelum kolom itu ada."""
    _, error = _load_meeting(meeting_id, edit=True)
    if error:
        return error
    transcript = artifacts.load_fixed_transcript(meeting_id) or artifacts.load_transcript(meeting_id)
    if not transcript or artifacts.load_summary(meeting_id) is None:
        return jsonify({"error": "Rapat ini belum punya transkrip dan ringkasan"}), 404

    text = short_summary(transcript, meeting_id)
    with _summary_lock:
        summary = artifacts.load_summary(meeting_id) or {}
        summary["short_summary"] = text
        artifacts.save_summary(meeting_id, summary)
    return jsonify(summary)


@app.post("/meetings/<meeting_id>/action-items/<int:index>/toggle")
@login_required
def toggle_action_item(meeting_id, index):
    """Atur status selesai satu action item tanpa membuat ulang ringkasan."""
    record, error = _load_meeting(meeting_id, edit=True)
    if error:
        return error
    if not record["recording"]:
        return jsonify({"error": "Recording not available yet"}), 404

    # baca-ubah-tulis summary.json: lock mencegah dua klik cepat saling menghapus.
    # ponytail: satu lock untuk semua, per rapat kalau suatu saat berebut
    with _summary_lock:
        summary = artifacts.load_summary(meeting_id)
        if summary is None:
            return jsonify({"error": "No summary for this meeting yet"}), 404

        items = summary.get("action_items") or []
        if index < 0 or index >= len(items):
            return jsonify({"error": "Invalid action item index"}), 400

        done = (request.get_json(silent=True) or {}).get("done")
        items[index]["done"] = bool(done) if done is not None else not items[index].get("done", False)
        artifacts.save_summary(meeting_id, summary)
    report_stats.invalidate_action_item_cache(session["user_id"])
    return jsonify(summary)


@app.put("/meetings/<meeting_id>/action-items")
@login_required
def replace_action_items(meeting_id):
    """Ganti seluruh daftar action item ({"items": [{task, assignee, due, done}]})."""
    _, error = _load_meeting(meeting_id, edit=True)
    if error:
        return error
    raw = (request.get_json(silent=True) or {}).get("items")
    if not isinstance(raw, list):
        return jsonify({"error": "items must be a list"}), 400

    def text(value):
        return (value.strip() or None) if isinstance(value, str) else None

    items = []
    for it in raw:
        task = text(it.get("task")) if isinstance(it, dict) else None
        if not task:
            return jsonify({"error": "Setiap action item butuh isi tugas"}), 400
        items.append(
            {"task": task, "assignee": text(it.get("assignee")), "due": text(it.get("due")), "done": bool(it.get("done"))}
        )

    with _summary_lock:
        summary = artifacts.load_summary(meeting_id)
        if summary is None:
            return jsonify({"error": "No summary for this meeting yet"}), 404
        summary["action_items"] = items
        artifacts.save_summary(meeting_id, summary)
    report_stats.invalidate_action_item_cache(session["user_id"])
    return jsonify(summary)


_LIVE_STATUSES = ("joining", "recording", "stopping", "processing")


@app.delete("/meetings/<meeting_id>")
@login_required
def delete_meeting_route(meeting_id):
    """Hapus folder R2, potongan Knowledge Base, dan baris db. Hanya pemilik atau super admin, dan tidak saat rapat
    masih berjalan. Baris usage tetap ada supaya total biaya admin tidak menyusut."""
    record = get_meeting(meeting_id)
    if record is None:
        return jsonify({"error": "Meeting not found"}), 404
    if session.get("role") != "super_admin" and record.get("user_id") != session["user_id"]:
        return jsonify({"error": "Hanya pemilik rapat yang bisa menghapusnya"}), 403
    if record["status"] in _LIVE_STATUSES:
        return jsonify({"error": "Rapat masih berjalan, tunggu sampai selesai"}), 409

    # R2 dulu: kalau gagal tidak ada yang lain disentuh dan hapus bisa diulang.
    storage.delete_prefix(f"{meeting_id}/")
    try:
        knowledge_base.remove_meeting(meeting_id)
    except Exception as e:
        print(f"[knowledge_base] failed to remove meeting {meeting_id}: {e}")
    delete_meeting(meeting_id)
    return jsonify({"deleted": meeting_id})


@app.get("/meetings/<meeting_id>/recording")
@login_required
def meeting_recording(meeting_id):
    """Redirect ke url R2 bertanda tangan (scrubbing tetap jalan). Lewat rapat supaya tidak ada yang bisa
    meminta key sembarang."""
    record, error = _load_meeting(meeting_id)
    if error:
        return error
    if not record["recording"]:
        return jsonify({"error": "Recording not available yet"}), 404
    if storage.head(record["recording"]) is None:
        return jsonify({"error": "Recording file not found"}), 404
    return redirect(storage.presigned_url(record["recording"]))


@app.post("/upload")
@login_required
def upload():
    """Transkripsi dan ringkas rekaman yang tidak dibuat oleh bot."""
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "file is required (multipart/form-data field 'file')"}), 400

    quota_error = _check_meeting_quota(session["user_id"])
    if quota_error:
        return jsonify({"error": quota_error}), 402

    ext = Path(file.filename).suffix.lower()
    if ext not in UPLOAD_EXTENSIONS:
        return jsonify({"error": f"unsupported file type '{ext}', expected one of {sorted(UPLOAD_EXTENSIONS)}"}), 400

    # file disimpan lokal dulu (whisperx lokal butuh file), lalu naik ke R2 sebelum diproses supaya Replicate bisa membacanya
    out_dir = Path(os.getenv("RECORDINGS_DIR", "recordings")) / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    meeting_id = f"Upload_{int(time.time())}"
    local_recording_path = str(out_dir / f"{meeting_id}{ext}")
    file.save(local_recording_path)

    num_speakers = request.form.get("num_speakers", type=int)  # opsional, diisi user

    # buat barisnya dulu supaya daftar menampilkan "Memproses..." selagi ini berjalan
    start_meeting(
        meeting_id, "upload", f"Upload: {file.filename}", estimated_participants=num_speakers, user_id=session["user_id"]
    )
    # durasi dibiarkan null, kita harus mendecode file lagi untuk mendapatkannya
    recording_key = storage.upload_recording(local_recording_path, meeting_id, keep_local=True)
    update_meeting(meeting_id, status="processing", recording=recording_key)

    result = process_recording(local_recording_path, meeting_id, num_speakers, recording_key)
    try:
        os.remove(local_recording_path)
    except OSError:
        pass
    result["status"] = "done"
    result["recording"] = recording_key
    final_status = "failed" if result.get("transcript_error") else "completed"
    update_meeting(meeting_id, status=final_status, recording=recording_key)
    return jsonify(result)


@app.get("/admin/stats")
@super_admin_required
def admin_stats_route():
    """Jumlah rapat, MRR, biaya OpenAI, penyimpanan R2, dan jumlah user untuk dashboard admin."""
    return jsonify(admin_stats.get_stats())


@app.get("/admin/users")
@super_admin_required
def admin_users_list():
    plans = billing_store.plans_by_user()
    team_plans = billing_store.team_plans()

    def plan_of(uid):
        own = plans.get(uid, "free")
        return own if own != "free" else team_plans.get(uid, "free")

    return jsonify([{**u, "plan": plan_of(u["id"])} for u in auth_store.list_users()])


@app.post("/admin/users")
@super_admin_required
def admin_users_create():
    data = request.get_json(silent=True) or {}
    email, password, name = data.get("email"), data.get("password"), data.get("name")
    role = data.get("role") or "user"
    if not email or not password or not name:
        return jsonify({"error": "email, password, dan nama wajib diisi"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password minimal 8 karakter"}), 400
    if role not in auth_store.ROLES:
        return jsonify({"error": "Peran tidak dikenal"}), 400
    try:
        return jsonify(auth_store.create_user(email, password, name, role))
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "Email sudah terdaftar"}), 409


@app.patch("/admin/users/<user_id>")
@super_admin_required
def admin_users_update(user_id):
    """Ganti nama, ubah peran, atau (non)aktifkan. Menonaktifkan menggantikan menghapus:
    rapat tetap menunjuk ke users.id. Admin tidak bisa mengunci dirinya sendiri
    (menonaktifkan atau menurunkan akunnya sendiri)."""
    data = request.get_json(silent=True) or {}
    name, role, active = data.get("name"), data.get("role"), data.get("active")
    if name is not None and not str(name).strip():
        return jsonify({"error": "Nama tidak boleh kosong"}), 400
    if role is not None and role not in auth_store.ROLES:
        return jsonify({"error": "Peran tidak dikenal"}), 400
    if user_id == session["user_id"] and (active is False or (role is not None and role != "super_admin")):
        return jsonify({"error": "Kamu tidak bisa menonaktifkan atau menurunkan akunmu sendiri"}), 400
    target = auth_store.get_user(user_id)
    if target is None:
        return jsonify({"error": "Pengguna tidak ditemukan"}), 404
    if role is not None and target["role"] == "super_admin" and role != "super_admin":
        return jsonify({"error": "Super Admin tidak bisa diturunkan menjadi User"}), 400
    user = auth_store.update_user(user_id, name=str(name).strip() if name is not None else None, role=role, active=active)
    _active_cache.pop(user_id, None)
    return jsonify(user)


@app.post("/admin/users/<user_id>/reset-password")
@super_admin_required
def admin_users_reset_password(user_id):
    password = (request.get_json(silent=True) or {}).get("password") or ""
    if len(password) < 8:
        return jsonify({"error": "Password minimal 8 karakter"}), 400
    if auth_store.get_user(user_id) is None:
        return jsonify({"error": "Pengguna tidak ditemukan"}), 404
    auth_store.set_password(user_id, password)
    return jsonify({"ok": True})


@app.get("/admin/export")
@super_admin_required
def admin_export():
    """PDF resmi dengan angka yang sama seperti di dashboard."""
    admin = auth_store.get_user(session["user_id"])
    pdf_bytes = report_pdf.generate_report(admin_stats.get_stats(), list_meetings(), generated_by=admin["name"])
    return _pdf(pdf_bytes, "notulis-laporan-sistem.pdf")


@app.get("/reports/stats")
@login_required
def reports_stats_route():
    """Seperti /admin/stats tapi hanya rapat user ini (halaman Laporan)."""
    return jsonify(report_stats.get_stats(session["user_id"]))


@app.get("/reports/team")
@login_required
def reports_team():
    """Pemakaian team si pemanggil (null kalau tidak punya team) untuk halaman Laporan."""
    return jsonify(report_stats.team_usage(session["user_id"]))


@app.get("/reports/action-items")
@login_required
def reports_action_items():
    """Semua action item di seluruh rapat user ini. Dipisah dari /reports/stats karena membaca
    tiap ringkasan dari R2 dan lambat saat cache dingin."""
    return jsonify(report_stats.action_item_rollup(session["user_id"]))


@app.get("/reports/export")
@login_required
def reports_export():
    """Versi PDF halaman Laporan."""
    user = auth_store.get_user(session["user_id"])
    pdf_bytes = report_pdf.generate_user_report(
        report_stats.get_stats(session["user_id"]),
        list_meetings(session["user_id"]),
        generated_by=user["name"],
    )
    return _pdf(pdf_bytes, "notulis-laporan-rapat.pdf")


_comparison_cache: dict = {}


def _load_two_meetings():
    """Dua rapat dalam permintaan perbandingan beserta ringkasannya, atau respons error."""
    a_id, b_id = request.args.get("a"), request.args.get("b")
    if not a_id or not b_id:
        return None, (jsonify({"error": "Parameter a dan b (id rapat) wajib diisi"}), 400)
    meeting_a, meeting_b = get_meeting(a_id), get_meeting(b_id)
    if meeting_a is None or meeting_b is None or not (_can_view_meeting(meeting_a) and _can_view_meeting(meeting_b)):
        return None, (jsonify({"error": "Salah satu rapat tidak ditemukan"}), 404)
    for m in (meeting_a, meeting_b):
        m["summary"] = artifacts.load_summary(m["id"]) if m["recording"] else None
    return (meeting_a, meeting_b), None


def _comparison_analysis(meeting_a, meeting_b):
    """Perbandingan AI dua rapat, None kalau salah satu belum punya ringkasan. Di-cache supaya membuka halaman lagi atau
    ekspor PDF tidak memanggil model lagi. ponytail: dict di dalam proses, hilang saat restart"""
    if not meeting_a["summary"] or not meeting_b["summary"]:
        return None
    key = (meeting_a["id"], meeting_b["id"], hash(str(meeting_a["summary"]) + str(meeting_b["summary"])))
    if key not in _comparison_cache:
        _comparison_cache[key] = compare_meetings(meeting_a, meeting_a["summary"], meeting_b, meeting_b["summary"])
    return _comparison_cache[key]


@app.get("/perbandingan/analisis")
@login_required
def perbandingan_analisis():
    """Perbandingan AI yang tampil di bagian atas halaman Perbandingan."""
    pair, error = _load_two_meetings()
    if error:
        return error
    try:
        return jsonify(_comparison_analysis(*pair))
    except Exception as e:
        print(f"[perbandingan] AI comparison failed: {e}")
        return jsonify({"error": "Perbandingan AI gagal dibuat"}), 502


@app.post("/meetings/<meeting_id>/process")
@login_required
def meeting_process_now(meeting_id):
    """Kirim rekaman yang disimpan tanpa AI (status "limited") ke transkriber, kalau paket atau minggu ini
    sekarang cukup untuk seluruh rapat."""
    record, error = _load_meeting(meeting_id, edit=True)
    if error:
        return error
    if record["status"] != "limited":
        return jsonify({"error": "Rapat ini tidak menunggu pemrosesan"}), 409
    weekly = _weekly_quota(record["user_id"]) if record.get("user_id") else None
    if weekly and (record.get("duration_minutes") or 0) > weekly["remaining"]:
        return jsonify({"error": f"Sisa kuota minggu ini {weekly['remaining']:g} menit, rapat ini {record['duration_minutes']:g} menit. Upgrade ke Pro untuk memprosesnya."}), 402
    update_meeting(meeting_id, status="processing")
    job_queue.enqueue_transcription(meeting_id, record["recording"], record.get("estimated_participants"))
    return jsonify({"status": "processing"})


@app.get("/perbandingan/export")
@login_required
def perbandingan_export():
    """PDF halaman Perbandingan, lengkap dengan perbandingan AI kalau ada."""
    pair, error = _load_two_meetings()
    if error:
        return error
    meeting_a, meeting_b = pair
    try:
        analysis = _comparison_analysis(meeting_a, meeting_b)
    except Exception as e:
        print(f"[perbandingan] AI comparison failed for the PDF: {e}")
        analysis = None  # PDF berdampingan tetap berguna

    user = auth_store.get_user(session["user_id"])
    pdf_bytes = report_pdf.generate_comparison_report(meeting_a, meeting_b, generated_by=user["name"], analysis=analysis)
    return _pdf(pdf_bytes, "notulis-perbandingan-rapat.pdf")


# tempat frontend Expo berjalan, dipakai untuk redirect dan tautan di email
LOCAL_FRONTEND_URL = os.getenv("LOCAL_FRONTEND_URL", "http://localhost:8081")
# Xendit hanya menerima url kembali https, jadi checkout kembali ke /billing/return milik kita
# (lewat tunnel publik seperti ngrok), yang lalu mengarahkan ke frontend
PUBLIC_URL = os.getenv("PUBLIC_URL")


@app.get("/billing/return")
def billing_return():
    status = request.args.get("status", "cancel")
    if status == "success":
        return redirect(f"{LOCAL_FRONTEND_URL}/checkout-sukses")
    return redirect(f"{LOCAL_FRONTEND_URL}/billing?checkout=cancel")


@app.get("/billing/status")
@login_required
def billing_status():
    plan, inherited = billing_store.effective_plan(session["user_id"])
    return jsonify(
        {
            **billing_store.get_subscription(session["user_id"]),
            "plan": plan,
            "inherited_from_team": inherited,
            "weekly_quota": _weekly_quota(session["user_id"]),
        }
    )


@app.post("/billing/checkout")
@login_required
def billing_checkout():
    """Mulai checkout Xendit dan kembalikan url tujuan user. Paket baru berubah saat
    webhook melaporkan payment_session.completed."""
    plan = (request.get_json(force=True) or {}).get("plan")
    if plan not in billing_store.PLAN_PRICES:
        return jsonify({"error": f"unknown plan '{plan}', expected one of {list(billing_store.PLAN_PRICES)}"}), 400

    user_id = session["user_id"]
    reference_id = f"{user_id}-{plan}-{uuid.uuid4().hex[:8]}"
    # placeholder kalau PUBLIC_URL tidak diisi: checkout tetap jalan tapi user tidak kembali ke aplikasi
    return_base = PUBLIC_URL or "https://example.com"
    try:
        # tidak dinamai `session`, itu milik flask
        checkout_session = create_subscription_session(
            reference_id=reference_id,
            plan_amount=billing_store.PLAN_PRICES[plan],
            email=auth_store.get_user(user_id)["email"],
            success_url=f"{return_base}/billing/return?status=success",
            cancel_url=f"{return_base}/billing/return?status=cancel",
        )
    except requests.HTTPError as e:
        return jsonify({"error": f"Xendit error: {e.response.text}"}), 502

    billing_store.start_checkout(plan, checkout_session["payment_session_id"], account_id=user_id)
    return jsonify({"checkout_url": checkout_session["payment_link_url"]})


@app.post("/billing/checkout/cancel")
@login_required
def billing_checkout_cancel():
    """User keluar dari halaman Xendit, lupakan checkout yang belum dibayar."""
    billing_store.clear_pending(session["user_id"])
    return jsonify(billing_store.get_subscription(session["user_id"]))


@app.post("/billing/cancel")
@login_required
def billing_cancel():
    """Turun ke Free di akhir periode berbayar. Menonaktifkan plan Xendit menghentikan tagihan berikutnya,
    jadi ulangi manual kalau itu gagal."""
    plan_id = billing_store.cancel_subscription(session["user_id"])
    if plan_id:
        try:
            deactivate_recurring_plan(plan_id)
        except requests.HTTPError as e:
            print(f"[billing] failed to deactivate Xendit plan {plan_id}: {e}")
    return jsonify(billing_store.get_subscription(session["user_id"]))


@app.post("/billing/webhook")
def billing_webhook():
    """Event siklus Xendit, diverifikasi dengan token statis dari dashboard. Nama field-nya perkiraan dari dokumen mereka,
    event mentahnya dicetak supaya bisa dicek."""
    token = request.headers.get("x-callback-token")
    if not token or token != os.environ.get("XENDIT_WEBHOOK_TOKEN"):
        return jsonify({"error": "invalid webhook token"}), 401

    event = request.get_json(force=True) or {}
    print(f"[billing] webhook received: {event}")
    event_type = event.get("event")
    data = event.get("data", {})

    if event_type == "payment_session.completed":
        session_id = data.get("payment_session_id") or data.get("id")
        plan_id = data.get("recurring_plan_id")
        if session_id and plan_id:
            billing_store.activate_subscription(session_id, plan_id)
    elif event_type == "recurring.cycle.succeeded":
        plan_id = data.get("recurring_plan_id") or data.get("plan_id")
        if plan_id:
            billing_store.extend_subscription(plan_id)
    elif event_type == "recurring.cycle.failed":
        plan_id = data.get("recurring_plan_id") or data.get("plan_id")
        if plan_id:
            billing_store.mark_past_due(plan_id)

    return jsonify({"received": True})


@app.get("/teams/me")
@login_required
def get_my_team():
    """None kalau tidak punya team, selain itu {team, members}."""
    user = auth_store.get_user(session["user_id"])
    if not user["team_id"]:
        return jsonify(None)
    return jsonify({"team": team_store.get_team(user["team_id"]), "members": team_store.list_members(user["team_id"])})


@app.post("/teams")
@login_required
def create_team():
    """Buat team dengan pemanggil sebagai admin. Butuh paket Team dan belum punya team."""
    user = auth_store.get_user(session["user_id"])
    if user["team_id"]:
        return jsonify({"error": "Anda sudah tergabung dalam sebuah team"}), 400
    if billing_store.get_subscription(session["user_id"])["plan"] != "team":
        return jsonify({"error": "Membuat team memerlukan paket Team"}), 402
    name = (request.get_json(silent=True) or {}).get("name", "").strip()
    if not name:
        return jsonify({"error": "Nama team wajib diisi"}), 400
    return jsonify(team_store.create_team(name, session["user_id"]))


@app.patch("/teams/<team_id>")
@login_required
def rename_my_team(team_id):
    user = auth_store.get_user(session["user_id"])
    if user["team_id"] != team_id or user["team_role"] != "admin":
        return jsonify({"error": "Hanya admin team yang bisa mengubah ini"}), 403
    name = (request.get_json(silent=True) or {}).get("name", "").strip()
    if not name:
        return jsonify({"error": "Nama team wajib diisi"}), 400
    team_store.rename_team(team_id, name)
    return jsonify(team_store.get_team(team_id))


@app.post("/teams/invite")
@login_required
def invite_to_team():
    """Hanya admin. Tautannya tetap dikembalikan walau email gagal terkirim."""
    user = auth_store.get_user(session["user_id"])
    if not user["team_id"] or user["team_role"] != "admin":
        return jsonify({"error": "Hanya admin team yang bisa mengundang anggota"}), 403
    email = ((request.get_json(silent=True) or {}).get("email") or "").strip() or None
    invite = team_store.create_invite(user["team_id"], user["id"], email=email)
    invite_url = f"{LOCAL_FRONTEND_URL}/team/gabung/{invite['token']}"
    if email:
        try:
            team = team_store.get_team(user["team_id"])
            mailer.send_team_invite_email(email, team["name"], user["name"], invite_url)
        except Exception as e:
            print(f"[team] failed to send invite email to {email}: {e}")
    return jsonify({"token": invite["token"], "invite_url": invite_url, "expires_at": invite["expires_at"].strftime("%Y-%m-%dT%H:%M:%S")})


@app.get("/teams/invite/<token>")
@login_required
def preview_team_invite(token):
    """Supaya halaman gabung bisa menampilkan nama team sebelum user bergabung."""
    invite = team_store.get_invite(token)
    if invite is None:
        return jsonify({"error": "Tautan undangan tidak valid atau sudah kedaluwarsa"}), 404
    team = team_store.get_team(invite["team_id"])
    return jsonify({"team_name": team["name"]})


@app.post("/teams/join")
@login_required
def join_team():
    user = auth_store.get_user(session["user_id"])
    if user["team_id"]:
        return jsonify({"error": "Anda sudah tergabung dalam sebuah team. Keluar dulu untuk gabung team lain."}), 400
    token = (request.get_json(silent=True) or {}).get("token")
    team = team_store.accept_invite(token, session["user_id"])
    if team is None:
        return jsonify({"error": "Tautan undangan tidak valid atau sudah kedaluwarsa"}), 404
    return jsonify(team)


@app.post("/teams/leave")
@login_required
def leave_team():
    user = auth_store.get_user(session["user_id"])
    if not user["team_id"]:
        return jsonify({"error": "Anda belum tergabung dalam team apa pun"}), 400
    team_store.remove_member(session["user_id"])
    return jsonify({"left": True})


@app.delete("/teams/members/<user_id>")
@login_required
def remove_team_member(user_id):
    admin = auth_store.get_user(session["user_id"])
    target = auth_store.get_user(user_id)
    if not admin["team_id"] or admin["team_role"] != "admin":
        return jsonify({"error": "Hanya admin team yang bisa mengeluarkan anggota"}), 403
    if target is None or target["team_id"] != admin["team_id"]:
        return jsonify({"error": "Pengguna bukan anggota team ini"}), 404
    team_store.remove_member(user_id)
    return jsonify({"removed": True})


@app.patch("/teams/members/<user_id>")
@login_required
def update_team_member_role(user_id):
    admin = auth_store.get_user(session["user_id"])
    target = auth_store.get_user(user_id)
    if not admin["team_id"] or admin["team_role"] != "admin":
        return jsonify({"error": "Hanya admin team yang bisa mengubah peran anggota"}), 403
    if target is None or target["team_id"] != admin["team_id"]:
        return jsonify({"error": "Pengguna bukan anggota team ini"}), 404
    role = (request.get_json(silent=True) or {}).get("role")
    if role not in ("admin", "member"):
        return jsonify({"error": "role harus 'admin' atau 'member'"}), 400
    team_store.set_role(user_id, admin["team_id"], role)
    return jsonify({"role": role})


@app.post("/meetings/<meeting_id>/share-team")
@login_required
def share_meeting_with_team(meeting_id):
    """Opt in per rapat ({"enabled": bool}), ada di team tidak otomatis membagikan apa pun."""
    record = get_meeting(meeting_id)
    if record is None:
        return jsonify({"error": "Meeting not found"}), 404
    if record.get("user_id") != session["user_id"]:
        return jsonify({"error": "Hanya pemilik rapat yang bisa membagikannya"}), 403
    enabled = bool((request.get_json(silent=True) or {}).get("enabled"))
    update_meeting(meeting_id, shared_with_team=enabled)
    return jsonify({"shared_with_team": enabled})


if __name__ == "__main__":
    # threaded supaya polling /jobs/<id> jalan saat ada join. 5050 karena ada yang terus memakai
    # 5000, 0.0.0.0 supaya port mapping docker bisa menjangkaunya
    app.run(host="0.0.0.0", port=5050, threaded=True)
