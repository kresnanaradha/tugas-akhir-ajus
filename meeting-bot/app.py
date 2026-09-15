import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

from bots.google_meet import GoogleMeetBot
from bots.zoom import ZoomBot
from pipeline import billing_store
from pipeline.meetings_store import find_meeting_by_url, get_meeting, list_meetings, start_meeting, update_meeting
from pipeline.paths import sibling_path
from pipeline.summarize import fix_transcript, summarize
from pipeline.transcribe import transcribe
from pipeline.xendit_client import create_subscription_session, deactivate_recurring_plan

load_dotenv()

app = Flask(__name__)
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
    # Local-dev-only wide-open CORS so the Expo web dev server (a different
    # port = different origin) can call this API directly. Fine for now
    # since there's no auth on these endpoints yet either (documented POC
    # gap) — tighten both together before this is ever exposed publicly.
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

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


def _process_recording(recording_path: str, num_speakers: int | None = None) -> dict:
    """Runs transcribe -> fix -> summarize on a recording already on disk.
    Each step's failure is reported separately instead of failing the whole
    request — a bad transcription/summarization shouldn't erase a recording
    that's already sitting on disk. Shared by the join endpoints and /upload
    so all three drive the exact same pipeline.

    num_speakers is just the user's best guess entered before starting the
    meeting/upload (there's no reliable way to scrape the real participant
    count from Google Meet/Zoom's web client) — still a meaningfully better
    hint for diarization than none at all, see "Transcription/summarization
    notes" in CLAUDE.md."""
    result = {}
    try:
        transcript = transcribe(recording_path, num_speakers=num_speakers)
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
        to_summarize = fix_transcript(transcript, recording_path)
        result["fixed_transcript"] = to_summarize
    except Exception as e:
        result["fix_transcript_error"] = str(e)

    try:
        result["summary"] = summarize(to_summarize, recording_path)
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
        recording_path = bot.join()
    except Exception as e:
        with _jobs_lock:
            _jobs[job_id].update(phase="failed", error=str(e))
        update_meeting(job_id, status="failed")
        return
    duration_minutes = round((time.time() - started_at) / 60, 1)

    with _jobs_lock:
        _jobs[job_id]["phase"] = "processing"
    update_meeting(job_id, status="processing", recording=recording_path, duration_minutes=duration_minutes)

    result = {"status": "done", "recording": recording_path}
    result.update(_process_recording(recording_path, num_speakers))
    final_status = "failed" if result.get("transcript_error") else "completed"
    update_meeting(job_id, status=final_status)

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

    start_meeting(job_id, platform, title, estimated_participants=num_speakers, url=url)

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
def google_join():
    return _join(GoogleMeetBot, "google_meet", "Rapat Google Meet")


@app.post("/zoom/join")
def zoom_join():
    return _join(ZoomBot, "zoom", "Rapat Zoom")


@app.get("/meetings")
def meetings():
    return jsonify(list_meetings())


@app.get("/meetings/<meeting_id>")
def meeting_detail(meeting_id):
    """Reads back a past meeting's transcript/fixed transcript/summary/
    per-segment timing from their sibling files on disk (see
    pipeline/paths.py) — the meetings table only stores the recording path,
    not the (potentially large) content itself, so this is where that
    content actually gets read."""
    record = get_meeting(meeting_id)
    if record is None:
        return jsonify({"error": "Meeting not found"}), 404

    recording_path = record["recording"]
    # No recording yet for a still-in-progress meeting (started_meeting()
    # inserts the row before any file exists) — nothing to read back yet in
    # that case, the frontend uses GET /jobs/<id> for live status instead.
    if recording_path:
        for key, subfolder, suffix, is_json in (
            ("transcript", "transcripts", ".txt", False),
            ("fixed_transcript", "fixed_transcripts", ".txt", False),
            ("summary", "summaries", ".summary.json", True),
            # Per-segment {speaker, start, end, text} — only present for
            # recordings transcribed after this was added; older ones
            # (including the hand-backfilled Google Meet recordings) just
            # won't have it, so the frontend falls back to plain transcript
            # display for those.
            ("segments", "transcripts", ".segments.json", True),
        ):
            path = sibling_path(recording_path, subfolder, suffix)
            if path.exists():
                text = path.read_text(encoding="utf-8")
                record[key] = json.loads(text) if is_json else text

        full_path = Path(recording_path)
        if full_path.exists():
            record["file_size_bytes"] = full_path.stat().st_size
            record["file_extension"] = full_path.suffix.lstrip(".")

    return jsonify(record)


@app.post("/meetings/<meeting_id>/transcript")
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

    recording_path = record["recording"]
    sibling_path(recording_path, "fixed_transcripts", ".txt").write_text(transcript, encoding="utf-8")

    result = {"fixed_transcript": transcript}

    if line_speakers or line_texts:
        segments_file = sibling_path(recording_path, "transcripts", ".segments.json")
        if segments_file.exists():
            segments = json.loads(segments_file.read_text(encoding="utf-8"))
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
                segments_file.write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")
                result["segments"] = segments

    try:
        result["summary"] = summarize(transcript, recording_path)
    except Exception as e:
        result["summary_error"] = str(e)
    return jsonify(result)


@app.post("/meetings/<meeting_id>/action-items/<int:index>/toggle")
def toggle_action_item(meeting_id, index):
    """Flips one action item's done flag — the only mutable field on a
    summary, so this patches summaries/*.summary.json directly rather than
    going through summarize() again (that would cost an OpenAI call and
    could reword everything else for no reason)."""
    record = get_meeting(meeting_id)
    if record is None:
        return jsonify({"error": "Meeting not found"}), 404
    if not record["recording"]:
        return jsonify({"error": "Recording not available yet"}), 404

    summary_file = sibling_path(record["recording"], "summaries", ".summary.json")
    if not summary_file.exists():
        return jsonify({"error": "No summary for this meeting yet"}), 404

    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    items = summary.get("action_items") or []
    if index < 0 or index >= len(items):
        return jsonify({"error": "Invalid action item index"}), 400

    items[index]["done"] = not items[index].get("done", False)
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify(summary)


@app.get("/meetings/<meeting_id>/recording")
def meeting_recording(meeting_id):
    """Serves the actual video/audio file for playback — looked up through
    the meeting record rather than taking a raw path, so this can't be used
    to read arbitrary files off disk."""
    record = get_meeting(meeting_id)
    if record is None:
        return jsonify({"error": "Meeting not found"}), 404
    if not record["recording"]:
        return jsonify({"error": "Recording not available yet"}), 404
    recording_path = Path(record["recording"])
    if not recording_path.exists():
        return jsonify({"error": "Recording file missing on disk"}), 404
    return send_file(recording_path)


@app.post("/upload")
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

    out_dir = Path(os.getenv("RECORDINGS_DIR", "recordings")) / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    meeting_id = f"Upload_{int(time.time())}"
    recording_path = str(out_dir / f"{meeting_id}{ext}")
    file.save(recording_path)

    num_speakers = request.form.get("num_speakers", type=int)  # optional, user-entered

    # Insert the row before processing starts (not after, via add_meeting())
    # — same reasoning as start_meeting() for the join endpoints: otherwise
    # the Rapat list shows nothing at all for however long transcribe/fix/
    # summarize take, instead of "Memproses...".
    start_meeting(meeting_id, "upload", f"Upload: {file.filename}", estimated_participants=num_speakers)
    # No cheap way to get audio/video duration here without decoding the file
    # again (ffprobe isn't guaranteed to be on PATH) — duration_minutes stays
    # null rather than adding that dependency just for a display number.
    update_meeting(meeting_id, status="processing", recording=recording_path)

    result = {"status": "done", "recording": recording_path}
    result.update(_process_recording(recording_path, num_speakers))
    final_status = "failed" if result.get("transcript_error") else "completed"
    update_meeting(meeting_id, status=final_status)
    return jsonify(result)


# In IDR — matches the pricing shown on the frontend's Pengaturan page.
# Free has no checkout at all (nothing to charge).
PLAN_PRICES = {"pro": 99_000, "team": 299_000}
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
    if plan not in PLAN_PRICES:
        return jsonify({"error": f"unknown plan '{plan}', expected one of {list(PLAN_PRICES)}"}), 400

    reference_id = f"{billing_store.DEFAULT_ACCOUNT_ID}-{plan}-{uuid.uuid4().hex[:8]}"
    # Falls back to a placeholder if PUBLIC_URL isn't set — checkout still
    # completes, the user just lands somewhere unhelpful afterward instead
    # of bouncing back into the app (see /billing/return above).
    return_base = PUBLIC_URL or "https://example.com"
    try:
        session = create_subscription_session(
            reference_id=reference_id,
            plan_amount=PLAN_PRICES[plan],
            email=os.getenv("BILLING_EMAIL", "demo@notulis.app"),
            success_url=f"{return_base}/billing/return?status=success",
            cancel_url=f"{return_base}/billing/return?status=cancel",
        )
    except requests.HTTPError as e:
        return jsonify({"error": f"Xendit error: {e.response.text}"}), 502

    billing_store.start_checkout(plan, session["payment_session_id"])
    return jsonify({"checkout_url": session["payment_link_url"]})


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
    app.run(port=5050, threaded=True)
