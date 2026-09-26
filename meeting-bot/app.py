import os
import re
import threading
import time
import uuid
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
from werkzeug.exceptions import RequestEntityTooLarge

from bots.google_meet import GoogleMeetBot
from bots.zoom import ZoomBot
from pipeline import admin_stats, artifacts, auth_store, billing_store, knowledge_base, report_pdf, report_stats, storage
from pipeline.meetings_store import find_meeting_by_url, get_meeting, list_meetings, start_meeting, update_meeting
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
MAX_DURATION_MIN = float(os.getenv("MAX_RECORDING_DURATION_MINUTES", "5"))
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
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error": "Belum login"}), 401
        return view(*args, **kwargs)

    return wrapped


def super_admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error": "Belum login"}), 401
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
    if user is None:
        # The session cookie outlived the user row (e.g. manually deleted
        # from the DB) — clear it rather than keep 401-ing forever with a
        # cookie the client has no way to know is now invalid.
        session.clear()
        return jsonify({"error": "Belum login"}), 401
    return jsonify(user)

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

    return result


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
    # `recording` here is still the local scratch path, just so
    # GET /meetings/<id> and friends see a truthy value while transcribe/fix/
    # summarize run against it below — overwritten with the real R2 key once
    # upload_recording() hands it off further down.
    update_meeting(job_id, status="processing", recording=local_recording_path, duration_minutes=duration_minutes)

    result = _process_recording(local_recording_path, job_id, num_speakers)
    recording_key = storage.upload_recording(local_recording_path, job_id)
    result["status"] = "done"
    result["recording"] = recording_key
    final_status = "failed" if result.get("transcript_error") else "completed"
    update_meeting(job_id, status=final_status, recording=recording_key)

    with _jobs_lock:
        _jobs[job_id].update(phase="done", result=result)


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
        return jsonify({"job_id": existing["id"], "shared": True})

    job_id = uuid.uuid4().hex
    # bot.status transitions (joining -> recording -> stopping) get persisted
    # to the meetings row live, via start_meeting()/update_meeting() below —
    # that's what lets the Rapat list show "Sedang Merekam" instead of the
    # row only appearing once the whole pipeline is done.
    bot = bot_cls(url, name, MAX_DURATION_MIN, on_status_change=lambda status: update_meeting(job_id, status=status))
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
def job_status(job_id):
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
def job_stop(job_id):
    """Ends the recording early (still runs the full transcribe/summarize
    pipeline afterward on whatever got recorded) — sets the same stop_event
    record()'s wait loop already checks every second."""
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
def knowledge_base_search():
    """RAG search: matches summary chunks (executive summary / key decision /
    topic / action item) by embedding similarity, each joined with its
    meeting's title/date/platform, then has GPT-4o mini write one short
    answer grounded only in those matches. Still not a chatbot — one query
    in, one answer + its sources out, no conversation state kept anywhere
    (see pipeline/knowledge_base.py's module docstring). `results` is always
    populated even if the answer synthesis fails, so the UI can fall back to
    showing just the raw matches."""
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"error": "q is required"}), 400

    matches = knowledge_base.search(query)
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
    if not record["recording"]:
        return jsonify({"error": "Recording not available yet"}), 404

    summary = artifacts.load_summary(meeting_id)
    if summary is None:
        return jsonify({"error": "No summary for this meeting yet"}), 404

    items = summary.get("action_items") or []
    if index < 0 or index >= len(items):
        return jsonify({"error": "Invalid action item index"}), 400

    items[index]["done"] = not items[index].get("done", False)
    artifacts.save_summary(meeting_id, summary)
    return jsonify(summary)


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


@app.get("/reports/export")
@login_required
def reports_export():
    """PDF version of the Laporan page — same numbers, via
    pipeline/report_pdf.py's generate_user_report()."""
    user = auth_store.get_user(session["user_id"])
    pdf_bytes = report_pdf.generate_user_report(
        report_stats.get_stats(session["user_id"]), list_meetings(session["user_id"]), generated_by=user["name"]
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=notulis-laporan-rapat.pdf"},
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
def billing_status():
    return jsonify(billing_store.get_subscription())


@app.post("/billing/checkout")
def billing_checkout():
    """Starts a Xendit subscription checkout for the given plan — returns a
    hosted checkout URL the frontend redirects the user to. The actual
    upgrade only takes effect once /billing/webhook receives
    payment_session.completed (the user still has to finish linking a
    payment method on Xendit's page first)."""
    plan = (request.get_json(force=True) or {}).get("plan")
    if plan not in billing_store.PLAN_PRICES:
        return jsonify({"error": f"unknown plan '{plan}', expected one of {list(billing_store.PLAN_PRICES)}"}), 400

    reference_id = f"{billing_store.DEFAULT_ACCOUNT_ID}-{plan}-{uuid.uuid4().hex[:8]}"
    # Falls back to a placeholder if PUBLIC_URL isn't set — checkout still
    # completes, the user just lands somewhere unhelpful afterward instead
    # of bouncing back into the app (see /billing/return above).
    return_base = PUBLIC_URL or "https://example.com"
    try:
        # Named checkout_session, not session — shadowing Flask's `session`
        # (imported for /auth/*) here would be harmless today since this
        # function doesn't touch it, but it's exactly the kind of name that
        # bites later when this function gets scoped to the logged-in user.
        checkout_session = create_subscription_session(
            reference_id=reference_id,
            plan_amount=billing_store.PLAN_PRICES[plan],
            email=os.getenv("BILLING_EMAIL", "demo@notulis.app"),
            success_url=f"{return_base}/billing/return?status=success",
            cancel_url=f"{return_base}/billing/return?status=cancel",
        )
    except requests.HTTPError as e:
        return jsonify({"error": f"Xendit error: {e.response.text}"}), 502

    billing_store.start_checkout(plan, checkout_session["payment_session_id"])
    return jsonify({"checkout_url": checkout_session["payment_link_url"]})


@app.post("/billing/cancel")
def billing_cancel():
    """"Turunkan ke Free" — keeps the user on their paid plan until
    current_period_end (billing_store.cancel_subscription() only sets
    cancel_at_period_end; get_subscription() reports the actual downgrade
    once that date passes). Deactivating the Xendit plan here is what
    actually stops future billing, immediately — worth retrying by hand if
    this fails, since otherwise Xendit could still charge one more cycle."""
    plan_id = billing_store.cancel_subscription()
    if plan_id:
        try:
            deactivate_recurring_plan(plan_id)
        except requests.HTTPError as e:
            print(f"[billing] failed to deactivate Xendit plan {plan_id}: {e}")
    return jsonify(billing_store.get_subscription())


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
