import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv

# Must run before any local module import below — several of them (e.g.
# pipeline/storage.py's R2 bucket name) read an env var at *import* time,
# not lazily inside a function, so .env has to already be loaded into
# os.environ by the time those imports happen. Learned the hard way: this
# used to sit after the imports and every request failed with a confusing
# "expected string or bytes-like object" from deep inside boto3 (the bucket
# name silently coming through as None).
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
from pipeline.summarize import fix_transcript, summarize
from pipeline.transcribe import transcribe
from pipeline.xendit_client import create_subscription_session, deactivate_recurring_plan

app = Flask(__name__)
# Signs the session cookie (Flask's built-in itsdangerous-based session) —
# auth/login below relies on this being stable across restarts, or every
# user gets logged out each time the backend restarts. Required in .env,
# not defaulted, so a real deployment can't accidentally run with a
# well-known/empty key.
app.secret_key = os.environ["SECRET_KEY"]
# Empty or 0 = no cap (the default). A recording then ends when the host ends the
# meeting, the bot is alone for EMPTY_MEETING_MINUTES, or someone presses Stop Rekam.
MAX_DURATION_MIN = float(os.getenv("MAX_RECORDING_DURATION_MINUTES") or 0) or None
# Safety cap on /upload request bodies, not a meaningful product limit — just
# guards against an accidental huge upload hanging the (single-threaded dev)
# server. Flask's default 413 response is HTML; the errorhandler below makes
# it JSON so the frontend's error parsing doesn't choke on it.
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1GB


@app.errorhandler(RequestEntityTooLarge)
def _file_too_large(_e):
    return jsonify({"error": "File terlalu besar (maks 1GB)"}), 413


@app.after_request
def _add_cors_headers(response):
    # Local-dev CORS so the Expo web dev server (a different port = a
    # different origin) can call this API directly. Reflects the request's
    # own Origin (rather than "*") and sets Allow-Credentials — required for
    # the session cookie auth/login sets below to actually be sent/read
    # cross-origin at all; "*" and credentialed requests are mutually
    # exclusive per the fetch/CORS spec. Still permissive about *which*
    # origins (any origin gets reflected back) — fine for local dev only,
    # tighten to an explicit allowlist before this is ever exposed publicly.
    origin = request.headers.get("Origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


# user_id -> (active, checked_at). A deactivated user's existing session must
# stop working, but hitting the DB on every request would double latency, so
# the check is cached. ponytail: up to 30s stale, per process.
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
    """Owner, super admin, someone handed this meeting through the same-link
    sharing (meeting_viewers), or a teammate of the owner when the owner
    toggled "Bagikan ke Team". Rows from before login existed have no owner,
    so only a super admin sees those."""
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


def super_admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error": "Belum login"}), 401
        if not _user_is_active(session["user_id"]):
            session.clear()
            return jsonify({"error": "Akun dinonaktifkan"}), 401
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
        # The session cookie outlived the user row (e.g. manually deleted
        # from the DB) — clear it rather than keep 401-ing forever with a
        # cookie the client has no way to know is now invalid.
        session.clear()
        return jsonify({"error": "Belum login"}), 401
    return jsonify(user)


@app.patch("/auth/me")
@login_required
def update_own_profile():
    """Self-service profile edit (name, email, phone, email notification
    preference) — unlike PATCH /admin/users/<id>, this only ever touches
    the caller's own row, so no super_admin_required and no id in the URL
    to mix up. Every field is optional; only the ones present in the body
    get changed."""
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
    """Self-service "delete account" — deactivates rather than actually
    deleting the row, same reasoning as the admin-side version: old
    meetings still point at users.id. Clears the session immediately
    afterward (same as logout) so the now-deactivated session can't keep
    being used."""
    auth_store.update_user(session["user_id"], active=False)
    session.clear()
    return jsonify({"ok": True})


_RESET_TTL_S = 3600
_reset_serializer = lambda: URLSafeTimedSerializer(app.secret_key, salt="password-reset")


@app.post("/auth/forgot")
def forgot_password():
    """Always answers ok, whether or not the email exists, so it can't be used
    to find out who is registered. The token is signed (no table) and carries a
    slice of the current password hash, so it stops working once the password
    changes (single use)."""
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
    """Self-service password change — requires the current password (unlike
    the admin's reset-password, which doesn't, since that's an intentional
    override for a locked-out user by someone who's already trusted)."""
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

# Whatever ffmpeg (whisperx's loader) can decode — covers both bot output
# (.webm) and typical uploads.
UPLOAD_EXTENSIONS = {".webm", ".mp4", ".mp3", ".wav", ".m4a", ".ogg"}

# Mirrors frontend/lib/validate.js — deliberately permissive (Zoom has many
# subdomains, personal meeting room URLs, etc.), just enough to catch "this
# isn't a meeting link at all" before wasting a Playwright launch on it. The
# frontend already checks this too; re-checked here since a client-side
# check alone is never trustworthy.
MEETING_URL_PATTERNS = {
    "google_meet": re.compile(r"^https?://meet\.google\.com/[a-z0-9-]+", re.I),
    "zoom": re.compile(r"^https?://([a-z0-9-]+\.)?zoom\.us/(j|wc/join)/\d+", re.I),
}
MEETING_PLATFORM_LABEL = {"google_meet": "Google Meet", "zoom": "Zoom"}


def _process_recording(local_recording_path: str, meeting_id: str, num_speakers: int | None = None) -> dict:
    """Runs transcribe -> fix -> summarize on a recording still sitting on
    local disk (whisperx needs a real local file to decode audio from) —
    the resulting transcript/fixed_transcript/summary/segments all get
    saved to R2 under meeting_id (see pipeline/artifacts.py), not next to
    the video file. Each step's failure is reported separately instead of
    failing the whole request — a bad transcription/summarization shouldn't
    erase a recording that's already been captured. Shared by the join
    endpoints and /upload so all three drive the exact same pipeline.

    num_speakers is just the user's best guess entered before starting the
    meeting/upload (there's no reliable way to scrape the real participant
    count from Google Meet/Zoom's web client) — still a meaningfully better
    hint for diarization than none at all, see "Transcription/summarization
    notes" in CLAUDE.md."""
    result = {}
    try:
        transcript = transcribe(local_recording_path, meeting_id, num_speakers=num_speakers)
        result["transcript"] = transcript
    except Exception as e:
        result["transcript_error"] = str(e)
        return result

    # Summarize the LLM-corrected transcript when that step succeeds, since
    # otherwise ASR mistakes (e.g. misheard words) just carry straight into
    # the summary. Fall back to the raw transcript rather than failing the
    # whole request if only the fix step breaks.
    to_summarize = transcript
    try:
        to_summarize = fix_transcript(transcript, meeting_id)
        result["fixed_transcript"] = to_summarize
    except Exception as e:
        result["fix_transcript_error"] = str(e)

    try:
        result["summary"] = summarize(to_summarize, meeting_id)
    except Exception as e:
        result["summary_error"] = str(e)

    if "summary" in result:
        _notify_meeting_ready(meeting_id, result["summary"])

    return result


def _notify_meeting_ready(meeting_id: str, summary: dict) -> None:
    """Best-effort email to the meeting's owner once a summary exists — a
    mail hiccup (or SMTP not configured at all, see mailer._config) must
    never fail the pipeline that already produced a real result."""
    try:
        record = get_meeting(meeting_id)
        user = auth_store.get_user(record["user_id"]) if record and record.get("user_id") else None
        if not user:
            return  # no owner to notify (pre-auth meeting, or upload with no session)
        if not user["email_notifications"]:
            return  # opted out on the Pengaturan page
        excerpt = (summary.get("executive_summary") or "").split("\n\n")[0]
        mailer.send_meeting_ready_email(
            to_email=user["email"],
            title=record["title"],
            summary_excerpt=excerpt,
            meeting_url=f"{LOCAL_FRONTEND_URL}/rapat/{meeting_id}",
        )
    except Exception as e:
        print(f"[mailer] failed to notify for meeting {meeting_id}: {e}")


# In-memory job registry for the join endpoints below — POC-scale only (lost
# on restart, not shared across processes), matches everything else here
# still being single-process. Keyed by a uuid job_id.
#   phase: "starting" (bot.join() in progress — check bot.status for
#          "joining"/"recording"/"stopping"), "processing", "done", "failed"
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
    # Recording length only, not wall-clock around bot.join() -- that also
    # counts browser launch, joining, waiting to be admitted and leaving
    # (a 1.25 min recording showed as 2.4 min). Falls back to the old
    # wall-clock figure if the bot never got as far as recording.
    if bot.record_started_at and bot.record_ended_at:
        duration_minutes = round((bot.record_ended_at - bot.record_started_at) / 60, 1)
    else:
        duration_minutes = round((time.time() - started_at) / 60, 1)

    with _jobs_lock:
        _jobs[job_id]["phase"] = "processing"

    # Recorder's job ends here now -- upload, then hand off to a transcriber
    # container over Redis instead of running transcribe/fix/summarize
    # in-process (see pipeline/job_queue.py). Recording+transcription
    # sharing one container's memory limit is exactly what OOM-killed a
    # live test (worker-test-2, mem_limit=3g) -- see CLAUDE.md.
    recording_key = storage.upload_recording(local_recording_path, job_id)
    update_meeting(job_id, status="processing", recording=recording_key, duration_minutes=duration_minutes)
    job_queue.enqueue_transcription(job_id, recording_key, num_speakers)
    if not getattr(bot, "quota_notified", False):  # the live notice already went out when the cap hit
        _notify_if_quota_exhausted(job_id, duration_minutes)

    # Drop this job from _jobs (rather than marking it "done") so a later
    # GET /jobs/<id> 404s -- the frontend already falls back to polling
    # GET /meetings/<id> on a 404 (see rapat/[id].jsx's pollMeeting()), which
    # DOES reflect the transcriber's eventual status update since that comes
    # from Postgres, not this process's memory. This process has no way to
    # truthfully report "done" any more; the transcriber is a separate
    # process that finishes the job later, possibly in another container.
    with _jobs_lock:
        _jobs.pop(job_id, None)


def _send_quota_exhausted(owner_id: str, limit: float, cut_off: bool) -> None:
    owner = auth_store.get_user(owner_id)
    mailer.send_quota_exhausted_email(owner['email'], owner['name'], limit, f"{LOCAL_FRONTEND_URL}/pengaturan", cut_off)


def _notify_if_quota_exhausted(meeting_id: str, duration_minutes: float) -> None:
    """Email the owner once, on the recording that used up the week's quota."""
    try:
        owner_id = (get_meeting(meeting_id) or {}).get("user_id")
        weekly = _weekly_quota(owner_id) if owner_id else None
        if not weekly or weekly["remaining"] >= _QUOTA_EXHAUSTED_BELOW_MIN:
            return
        if weekly["limit"] - (weekly["used"] - duration_minutes) < _QUOTA_EXHAUSTED_BELOW_MIN:
            return  # was already used up before this recording
        _send_quota_exhausted(owner_id, weekly["limit"], cut_off=False)
    except Exception as e:
        print(f"[quota] exhausted email failed: {e}")


def _plan_limits(user_id: str) -> dict:
    plan = billing_store.get_subscription(user_id)["plan"]
    return billing_store.PLAN_LIMITS.get(plan, billing_store.PLAN_LIMITS["free"])


def _week_start() -> datetime:
    """Most recent Sunday 08:00 (server local time, WITA) -- when the weekly
    recording quota last reset."""
    now = datetime.now()
    start = (now - timedelta(days=(now.weekday() + 1) % 7)).replace(hour=8, minute=0, second=0, microsecond=0)
    return start if start <= now else start - timedelta(days=7)


def _weekly_quota(user_id: str) -> dict | None:
    """None if this plan has no weekly recording cap, else
    {limit, used, remaining (minutes), resets_at}."""
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


# Counts as used up once less than this is left -- a recording cut at the cap
# lands a rounding hair short of the limit.
_QUOTA_EXHAUSTED_BELOW_MIN = 0.5


def _kb_allowed(user_id: str) -> bool:
    """Knowledge Base (opt-in + search) is a Pro/Team feature — see the
    "Knowledge Base pencarian semantik" bullet on the Pengaturan page's
    Pro/Team plans, absent from Free's."""
    return billing_store.get_subscription(user_id)["plan"] != "free"


def _check_meeting_quota(user_id: str) -> str | None:
    """None if this user can start another meeting right now, else a
    user-facing error message — see billing_store.PLAN_LIMITS. Counts
    joins and uploads together (both consume a "rapat" slot)."""
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
    # Optional, user-entered estimate — silently ignored if missing/garbage
    # rather than failing the request over what's just a diarization hint.
    try:
        num_speakers = int(data["num_speakers"]) if data.get("num_speakers") else None
    except (TypeError, ValueError):
        num_speakers = None
    if not url:
        return jsonify({"error": "url is required"}), 400
    url = url.strip()
    if not MEETING_URL_PATTERNS[platform].match(url):
        return jsonify({"error": f"'{url}' bukan tautan {MEETING_PLATFORM_LABEL[platform]} yang valid"}), 400

    # Someone (anyone — not just the same user, there's no auth to tell them
    # apart yet) already has a bot on this exact link, or already recorded
    # it. Share that meeting instead of joining a second bot into the same
    # call: the frontend's existing polling/detail-view logic already
    # handles a still-live vs. already-completed job_id the same way it
    # would handle one this call just started, so no extra branching is
    # needed on that end.
    existing = find_meeting_by_url(url)
    if existing:
        if existing.get("user_id") != session["user_id"]:
            add_viewer(existing["id"], session["user_id"])
        return jsonify({"job_id": existing["id"], "shared": True})

    quota_error = _check_meeting_quota(session["user_id"])
    if quota_error:
        return jsonify({"error": quota_error}), 402

    # Free's recording length cap (see billing_store.PLAN_LIMITS) is a
    # tighter ceiling on top of MAX_DURATION_MIN, not a replacement for it —
    # a Pro/Team user is still bounded by that env var, just not by a plan.
    plan_cap = _plan_limits(session["user_id"])["max_duration_minutes"]
    weekly = _weekly_quota(session["user_id"])
    if weekly and weekly["remaining"] < _QUOTA_EXHAUSTED_BELOW_MIN:
        return jsonify({"error": f"Kuota rekaman Free minggu ini ({weekly['limit']} menit) sudah habis. Reset Minggu pukul 08.00, atau upgrade ke Pro."}), 402
    caps = [c for c in (MAX_DURATION_MIN, plan_cap, weekly["remaining"] if weekly else None) if c is not None]
    max_duration = min(caps) if caps else None

    job_id = uuid.uuid4().hex
    # bot.status transitions (joining -> recording -> stopping) get persisted
    # to the meetings row live, via start_meeting()/update_meeting() below —
    # that's what lets the Rapat list show "Sedang Merekam" instead of the
    # row only appearing once the whole pipeline is done.
    bot = bot_cls(url, name, max_duration, on_status_change=lambda status: update_meeting(job_id, status=status))
    if weekly and max_duration == weekly["remaining"]:
        # The weekly quota is what will stop this recording: tell the owner the
        # moment it does, not after the upload finishes.
        owner_id, limit = session["user_id"], weekly["limit"]

        def _on_limit_reached():
            bot.quota_notified = True
            try:
                _send_quota_exhausted(owner_id, limit, cut_off=True)
            except Exception as e:
                print(f"[quota] live exhausted email failed: {e}")

        bot.on_limit_reached = _on_limit_reached
    with _jobs_lock:
        # Recording relies on capturing the whole (virtual) display, not just
        # the meeting tab (see CLAUDE.md's "Known accepted limitation") — that
        # was only ever safe with one bot in progress at a time. Blocking used
        # to enforce that as a side effect; running joins in background
        # threads (below) removes that side effect, so it has to be enforced
        # here explicitly instead, until jobs actually get real per-job
        # display isolation.
        if any(j["phase"] in ("starting", "processing") for j in _jobs.values()):
            return jsonify({"error": "Rapat lain sedang direkam. Tunggu sampai selesai sebelum memulai yang baru."}), 409
        _jobs[job_id] = {"phase": "starting", "bot": bot, "result": None, "error": None}

    start_meeting(job_id, platform, title, estimated_participants=num_speakers, url=url, user_id=session["user_id"])

    # bot.join() blocks for as long as the meeting runs (it calls record()
    # internally) — that used to block this whole HTTP request. Running it
    # in a background thread instead lets the frontend poll GET /jobs/<id>
    # for live status (joining/recording + elapsed seconds) and hit
    # POST /jobs/<id>/stop to end the recording early via bot.stop_event,
    # instead of only finding out anything once the entire pipeline is done.
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
        if phase == "done":
            return jsonify({"status": "done", "result": job["result"]})
        return jsonify({"status": "failed", "error": job["error"]})


@app.post("/jobs/<job_id>/stop")
@login_required
def job_stop(job_id):
    """Ends the recording early (still runs the full transcribe/summarize
    pipeline afterward on whatever got recorded) — sets the same stop_event
    record()'s wait loop already checks every second."""
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
    """RAG search: matches summary chunks (executive summary / key decision /
    topic / action item) by embedding similarity, each joined with its
    meeting's title/date/platform, then has GPT-4o mini write one short
    answer grounded only in those matches. Still not a chatbot — one query
    in, one answer + its sources out, no conversation state kept anywhere
    (see pipeline/knowledge_base.py's module docstring). `results` is always
    populated even if the answer synthesis fails, so the UI can fall back to
    showing just the raw matches."""
    if not _kb_allowed(session["user_id"]):
        return jsonify({"error": "Knowledge Base adalah fitur paket Pro/Team. Upgrade untuk memakainya."}), 402

    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"error": "q is required"}), 400

    # Only meetings this user can see AND opted into the KB (in_kb): scoping
    # it in the vector query itself, so other users' chunks can't crowd out
    # the top results.
    allowed = [m["id"] for m in list_meetings(session["user_id"]) if m.get("in_kb")]
    matches = knowledge_base.search(query, allowed)
    results = []
    for m in matches:
        meeting = get_meeting(m["meeting_id"])
        if meeting is None:
            continue  # stale chunk from a deleted meeting — skip rather than error
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
    """Reads back a past meeting's transcript/fixed transcript/summary/
    per-segment timing from R2 (see pipeline/artifacts.py) — the meetings
    table only stores the recording's R2 key, not that (potentially large)
    content itself, so this is where that content actually gets read."""
    record = get_meeting(meeting_id)
    if record is None:
        return jsonify({"error": "Meeting not found"}), 404
    if not _can_view_meeting(record):
        return jsonify(_NOT_FOUND[0]), _NOT_FOUND[1]

    recording_key = record["recording"]
    # No recording yet for a still-in-progress meeting (start_meeting()
    # inserts the row before any file exists) — nothing to read back yet in
    # that case, the frontend uses GET /jobs/<id> for live status instead.
    # A recording that's mid-pipeline (still the local scratch path, not
    # yet uploaded — see _run_join_job) also has nothing in R2 yet; the
    # loads below just come back empty for that window, same as before.
    if recording_key:
        record["transcript"] = artifacts.load_transcript(meeting_id)
        record["fixed_transcript"] = artifacts.load_fixed_transcript(meeting_id)
        record["summary"] = artifacts.load_summary(meeting_id)
        # Per-segment {speaker, start, end, text} — only present for
        # recordings transcribed after this was added; older ones just
        # won't have it, so the frontend falls back to plain transcript
        # display for those.
        record["segments"] = artifacts.load_segments(meeting_id)

        info = storage.head(recording_key)
        if info:
            record["file_size_bytes"] = info["size"]
            record["file_extension"] = os.path.splitext(recording_key)[1].lstrip(".")

    return jsonify(record)


@app.post("/meetings/<meeting_id>/transcript")
@login_required
def update_transcript(meeting_id):
    """Saves a user-edited transcript (the editor's per-line, per-speaker
    editor) as this meeting's fixed_transcript, then re-runs summarize() on
    it — the summary shown afterward reflects whatever correction the user
    actually approved, not the model's first pass. Optional line_speakers /
    line_texts (one entry per line, same order as segments.json, from the
    frontend's per-line editor) also patch segments.json's speaker/text when
    their length matches, so the synced Transkrip tab (which reads that
    file, not the transcript text) shows the same correction instead of
    just the original ASR output."""
    record = get_meeting(meeting_id)
    if record is None:
        return jsonify({"error": "Meeting not found"}), 404
    if not _can_edit_meeting(record):
        return jsonify(_NOT_OWNER[0]), _NOT_OWNER[1]
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
    """Opt this meeting in/out of the Knowledge Base ({"enabled": bool}).
    Only the executive summary + key decisions get indexed."""
    record = get_meeting(meeting_id)
    if record is None:
        return jsonify({"error": "Meeting not found"}), 404
    if not _can_edit_meeting(record):
        return jsonify(_NOT_OWNER[0]), _NOT_OWNER[1]
    enabled = bool((request.get_json(silent=True) or {}).get("enabled"))
    if enabled:
        # Opting IN needs Pro/Team; opting a meeting back OUT is always
        # allowed regardless of plan, so a downgrade never strands someone
        # unable to remove their own meeting from the index.
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


@app.post("/meetings/<meeting_id>/action-items/<int:index>/toggle")
@login_required
def toggle_action_item(meeting_id, index):
    """Flips one action item's done flag — the only mutable field on a
    summary, so this patches the saved summary directly rather than going
    through summarize() again (that would cost an OpenAI call and could
    reword everything else for no reason)."""
    record = get_meeting(meeting_id)
    if record is None:
        return jsonify({"error": "Meeting not found"}), 404
    if not _can_edit_meeting(record):
        return jsonify(_NOT_OWNER[0]), _NOT_OWNER[1]
    if not record["recording"]:
        return jsonify({"error": "Recording not available yet"}), 404

    # Read-modify-write of the whole summary file: two quick clicks used to
    # both read the same old copy and the second save erased the first
    # check, so serialize it. The client sends the wanted `done` value
    # (idempotent) instead of relying on a blind flip.
    # ponytail: one process-wide lock, per-meeting locks if it ever contends.
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
    """Replaces the whole action item list ({"items": [{task, assignee, due,
    done}]}) — one endpoint covers edit, add and remove. Same lock as the
    toggle so the two can't overwrite each other's write."""
    record = get_meeting(meeting_id)
    if record is None:
        return jsonify({"error": "Meeting not found"}), 404
    if not _can_edit_meeting(record):
        return jsonify(_NOT_OWNER[0]), _NOT_OWNER[1]
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
    """Permanently deletes a meeting: its R2 folder (recording, transcripts,
    segments, summary), its Knowledge Base chunks and its database row. Only
    the owner or a super admin (rows from before user_id existed have no
    owner, so only a super admin can remove those). Refused while the meeting
    is still being recorded/processed. Usage/cost rows are kept on purpose so
    the admin cost totals don't shrink."""
    record = get_meeting(meeting_id)
    if record is None:
        return jsonify({"error": "Meeting not found"}), 404
    if session.get("role") != "super_admin" and record.get("user_id") != session["user_id"]:
        return jsonify({"error": "Hanya pemilik rapat yang bisa menghapusnya"}), 403
    if record["status"] in _LIVE_STATUSES:
        return jsonify({"error": "Rapat masih berjalan, tunggu sampai selesai"}), 409

    # R2 first: if it fails nothing else is touched and the delete can be retried.
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
    """Redirects to a time-limited R2 URL for the actual video/audio file —
    looked up through the meeting record rather than taking a raw key, so
    this can't be used to read arbitrary objects out of the bucket. The
    browser talks to R2 directly from here (still supports Range requests
    for <video> scrubbing), not proxied through Flask."""
    record = get_meeting(meeting_id)
    if record is None:
        return jsonify({"error": "Meeting not found"}), 404
    if not _can_view_meeting(record):
        return jsonify(_NOT_FOUND[0]), _NOT_FOUND[1]
    if not record["recording"]:
        return jsonify({"error": "Recording not available yet"}), 404
    if storage.head(record["recording"]) is None:
        return jsonify({"error": "Recording file not found"}), 404
    return redirect(storage.presigned_url(record["recording"]))


@app.post("/upload")
@login_required
def upload():
    """Transcribe + summarize an already-recorded audio/video file, for
    meetings that weren't captured by the bot. Reuses the exact same
    transcribe()/summarize() pipeline as the join endpoints — those already
    take a plain file path, so this is just a file-upload wrapper around it."""
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "file is required (multipart/form-data field 'file')"}), 400

    quota_error = _check_meeting_quota(session["user_id"])
    if quota_error:
        return jsonify({"error": quota_error}), 402

    ext = Path(file.filename).suffix.lower()
    if ext not in UPLOAD_EXTENSIONS:
        return jsonify({"error": f"unsupported file type '{ext}', expected one of {sorted(UPLOAD_EXTENSIONS)}"}), 400

    # Local scratch space, same as a bot recording — transcribe() needs a
    # real local file to decode, uploaded to R2 (and deleted locally) once
    # the pipeline's done with it.
    out_dir = Path(os.getenv("RECORDINGS_DIR", "recordings")) / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    meeting_id = f"Upload_{int(time.time())}"
    local_recording_path = str(out_dir / f"{meeting_id}{ext}")
    file.save(local_recording_path)

    num_speakers = request.form.get("num_speakers", type=int)  # optional, user-entered

    # Insert the row before processing starts (not after, via add_meeting())
    # — same reasoning as start_meeting() for the join endpoints: otherwise
    # the Rapat list shows nothing at all for however long transcribe/fix/
    # summarize take, instead of "Memproses...".
    start_meeting(
        meeting_id, "upload", f"Upload: {file.filename}", estimated_participants=num_speakers, user_id=session["user_id"]
    )
    # No cheap way to get audio/video duration here without decoding the file
    # again (ffprobe isn't guaranteed to be on PATH) — duration_minutes stays
    # null rather than adding that dependency just for a display number.
    update_meeting(meeting_id, status="processing", recording=local_recording_path)

    result = _process_recording(local_recording_path, meeting_id, num_speakers)
    recording_key = storage.upload_recording(local_recording_path, meeting_id)
    result["status"] = "done"
    result["recording"] = recording_key
    final_status = "failed" if result.get("transcript_error") else "completed"
    update_meeting(meeting_id, status=final_status, recording=recording_key)
    return jsonify(result)


@app.get("/admin/stats")
@super_admin_required
def admin_stats_route():
    """Meeting volume (today/this week/this month), active subscriptions +
    MRR, OpenAI cost (real token usage tracked since pipeline/usage_store.py
    was added — not retroactively estimated for older meetings), R2 storage
    used, total registered users. See pipeline/admin_stats.py."""
    return jsonify(admin_stats.get_stats())


@app.get("/admin/users")
@super_admin_required
def admin_users_list():
    plans = billing_store.plans_by_user()
    return jsonify([{**u, "plan": plans.get(u["id"], "free")} for u in auth_store.list_users()])


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
    """Rename, change role, or (de)activate. Deactivating replaces deleting:
    meetings keep pointing at users.id. An admin can't lock themselves out
    (deactivate or demote their own account)."""
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
    """Formal PDF report — letterhead, executive summary, meeting-volume
    breakdown, and a full meeting detail table (see
    pipeline/report_pdf.py) — the "laporan resmi kantor" ask. Reuses
    admin_stats.get_stats() (same numbers the dashboard itself shows) so the
    PDF can never drift from what's on screen."""
    admin = auth_store.get_user(session["user_id"])
    pdf_bytes = report_pdf.generate_report(admin_stats.get_stats(), list_meetings(), generated_by=admin["name"])
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=notulis-laporan-sistem.pdf"},
    )


@app.get("/reports/stats")
@login_required
def reports_stats_route():
    """Same shape of aggregation as /admin/stats, but just this one user's
    own meetings — the regular (non-admin) Laporan page. See
    pipeline/report_stats.py."""
    return jsonify(report_stats.get_stats(session["user_id"]))


@app.get("/reports/action-items")
@login_required
def reports_action_items():
    """Rekap of every action item across this user's meetings (see
    report_stats.action_item_rollup) — separate from /reports/stats because it
    reads each meeting's summary from R2 and is slow on a cold cache."""
    return jsonify(report_stats.action_item_rollup(session["user_id"]))


@app.get("/reports/export")
@login_required
def reports_export():
    """PDF version of the Laporan page — same numbers, via
    pipeline/report_pdf.py's generate_user_report()."""
    user = auth_store.get_user(session["user_id"])
    pdf_bytes = report_pdf.generate_user_report(
        report_stats.get_stats(session["user_id"], with_action_items=True),
        list_meetings(session["user_id"]),
        generated_by=user["name"],
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=notulis-laporan-rapat.pdf"},
    )


@app.get("/perbandingan/export")
@login_required
def perbandingan_export():
    """PDF version of the Perbandingan Rapat page — same two meetings side
    by side, via pipeline/report_pdf.py's generate_comparison_report().
    Same read permission as GET /meetings/<id> (login only, no per-meeting
    ownership check — this app doesn't gate reads by owner, only deletes)."""
    a_id, b_id = request.args.get("a"), request.args.get("b")
    if not a_id or not b_id:
        return jsonify({"error": "Parameter a dan b (id rapat) wajib diisi"}), 400

    meeting_a, meeting_b = get_meeting(a_id), get_meeting(b_id)
    if meeting_a is None or meeting_b is None or not (_can_view_meeting(meeting_a) and _can_view_meeting(meeting_b)):
        return jsonify({"error": "Salah satu rapat tidak ditemukan"}), 404
    for m in (meeting_a, meeting_b):
        m["summary"] = artifacts.load_summary(m["id"]) if m["recording"] else None

    user = auth_store.get_user(session["user_id"])
    pdf_bytes = report_pdf.generate_comparison_report(meeting_a, meeting_b, generated_by=user["name"])
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=notulis-perbandingan-rapat.pdf"},
    )


# Where the actual frontend dev server runs — always plain localhost, since
# the browser doing the redirect is the same machine either way.
LOCAL_FRONTEND_URL = os.getenv("LOCAL_FRONTEND_URL", "http://localhost:8081")
# Xendit requires success_return_url/cancel_return_url to be HTTPS — plain
# localhost fails that check, so the checkout instead points back at this
# backend's own /billing/return (over a public HTTPS tunnel, e.g. ngrok —
# same one used for the webhook), which then 302s to LOCAL_FRONTEND_URL.
# One less thing to keep in sync than tunneling the frontend separately.
PUBLIC_URL = os.getenv("PUBLIC_URL")


@app.get("/billing/return")
def billing_return():
    status = request.args.get("status", "cancel")
    if status == "success":
        return redirect(f"{LOCAL_FRONTEND_URL}/checkout-sukses")
    return redirect(f"{LOCAL_FRONTEND_URL}/pengaturan?checkout=cancel")


@app.get("/billing/status")
@login_required
def billing_status():
    return jsonify({**billing_store.get_subscription(session["user_id"]), "weekly_quota": _weekly_quota(session["user_id"])})


@app.post("/billing/checkout")
@login_required
def billing_checkout():
    """Starts a Xendit subscription checkout for the given plan — returns a
    hosted checkout URL the frontend redirects the user to. The actual
    upgrade only takes effect once /billing/webhook receives
    payment_session.completed (the user still has to finish linking a
    payment method on Xendit's page first)."""
    plan = (request.get_json(force=True) or {}).get("plan")
    if plan not in billing_store.PLAN_PRICES:
        return jsonify({"error": f"unknown plan '{plan}', expected one of {list(billing_store.PLAN_PRICES)}"}), 400

    user_id = session["user_id"]
    reference_id = f"{user_id}-{plan}-{uuid.uuid4().hex[:8]}"
    # Falls back to a placeholder if PUBLIC_URL isn't set — checkout still
    # completes, the user just lands somewhere unhelpful afterward instead
    # of bouncing back into the app (see /billing/return above).
    return_base = PUBLIC_URL or "https://example.com"
    try:
        # Named checkout_session, not session (Flask's, imported for /auth/*).
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
    """The user backed out of Xendit's page (or abandoned it): forget the
    unpaid checkout instead of leaving "waiting for payment" on screen."""
    billing_store.clear_pending(session["user_id"])
    return jsonify(billing_store.get_subscription(session["user_id"]))


@app.post("/billing/cancel")
@login_required
def billing_cancel():
    """"Turunkan ke Free" — keeps the user on their paid plan until
    current_period_end (billing_store.cancel_subscription() only sets
    cancel_at_period_end; get_subscription() reports the actual downgrade
    once that date passes). Deactivating the Xendit plan here is what
    actually stops future billing, immediately — worth retrying by hand if
    this fails, since otherwise Xendit could still charge one more cycle."""
    plan_id = billing_store.cancel_subscription(session["user_id"])
    if plan_id:
        try:
            deactivate_recurring_plan(plan_id)
        except requests.HTTPError as e:
            print(f"[billing] failed to deactivate Xendit plan {plan_id}: {e}")
    return jsonify(billing_store.get_subscription(session["user_id"]))


@app.post("/billing/webhook")
def billing_webhook():
    """Xendit calls this on session/subscription lifecycle events. Verified
    via the same static token configured in the Xendit dashboard's webhook
    settings (Callbacks -> Verification Token), not a payload signature.
    Field names below are best-effort from Xendit's docs (their webhook
    payload JSON schema isn't fully published) — print the raw event so a
    real test webhook from the dashboard can confirm/correct them."""
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
    """None if the caller isn't on a team, else {team, members} — members
    include role so the frontend can show an admin-only invite/remove UI."""
    user = auth_store.get_user(session["user_id"])
    if not user["team_id"]:
        return jsonify(None)
    return jsonify({"team": team_store.get_team(user["team_id"]), "members": team_store.list_members(user["team_id"])})


@app.post("/teams")
@login_required
def create_team():
    """Starts a team with the caller as its sole admin member. Requires the
    Team plan (same PLAN_LIMITS check used for meeting quotas/KB) and that
    the caller isn't already on a team — leave/get-removed first."""
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
    """Admin-only. Returns the invite link regardless of whether the email
    actually sent (mailer is best-effort) — an admin can always copy/share
    the link by hand if SMTP isn't configured or delivery fails."""
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
    """Lets the join page show "Anda akan bergabung ke team X" before the
    user commits by POSTing /teams/join."""
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
    """Per-meeting opt-in ({"enabled": bool}) — being on a team never shares
    a meeting on its own, see meetings_store.list_meetings()."""
    record = get_meeting(meeting_id)
    if record is None:
        return jsonify({"error": "Meeting not found"}), 404
    if record.get("user_id") != session["user_id"]:
        return jsonify({"error": "Hanya pemilik rapat yang bisa membagikannya"}), 403
    enabled = bool((request.get_json(silent=True) or {}).get("enabled"))
    update_meeting(meeting_id, shared_with_team=enabled)
    return jsonify({"shared_with_team": enabled})


if __name__ == "__main__":
    # threaded=True so status-polling requests (GET /jobs/<id>) get served
    # while a join is running in its own background thread, instead of
    # queuing behind it.
    # 5050, not 5000 — something else on this machine keeps squatting 5000
    # (a stray WSL/other service, going by netstat showing a uvicorn server
    # there that isn't ours), causing requests to land on the wrong process.
    # host="0.0.0.0" -- Flask's default (127.0.0.1) only accepts connections
    # from inside the same network namespace, which inside a Docker
    # container means requests coming in through the container's mapped
    # port never reach it (confirmed: curl from the host got an empty
    # reply even though Flask logged itself as running). Harmless on plain
    # host dev too, it just also listens on the LAN interface, not just
    # loopback -- no different in practice from the CORS policy already
    # being wide open for this POC.
    app.run(host="0.0.0.0", port=5050, threaded=True)
