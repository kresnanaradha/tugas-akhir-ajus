"""Memulai rekaman: bot bergabung (/google/join, /zoom/join), status dan Stop Rekam (/jobs/<id>), dan unggah file
(/upload). Bot-nya sendiri dijalankan worker perekam, lihat join_worker.py."""

import os
import re
import time
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, request, session

from pipeline import join_queue, meetings_store, storage
from pipeline.process import process_recording

from . import common
from .common import login_required

bp = Blueprint("recording", __name__)


# format yang bisa didecode ffmpeg
UPLOAD_EXTENSIONS = {".webm", ".mp4", ".mp3", ".wav", ".m4a", ".ogg"}


# sengaja longgar, hanya menangkap tautan yang bukan rapat sebelum browser dijalankan (frontend juga mengecek)
MEETING_URL_PATTERNS = {
    "google_meet": re.compile(r"^https?://meet\.google\.com/[a-z0-9-]+", re.I),
    "zoom": re.compile(r"^https?://([a-z0-9-]+\.)?zoom\.us/(j|wc/join)/\d+", re.I),
}


MEETING_PLATFORM_LABEL = {"google_meet": "Google Meet", "zoom": "Zoom"}


def _join(platform: str, title: str):
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
    existing = meetings_store.find_meeting_by_url(url)
    if existing:
        if existing.get("user_id") != session["user_id"]:
            meetings_store.add_viewer(existing["id"], session["user_id"])
        return jsonify({"job_id": existing["id"], "shared": True})

    quota_error = common.check_meeting_quota(session["user_id"])
    if quota_error:
        return jsonify({"error": quota_error}), 402

    # di sini hanya batas teknis. Menit mingguan tidak menghentikan rekaman, hanya menentukan
    # setelahnya apakah dapat AI (lihat run_join_job)
    plan_cap = common.plan_limits(session["user_id"])["max_duration_minutes"]
    caps = [c for c in (common.MAX_DURATION_MIN, plan_cap) if c is not None]
    max_duration = min(caps) if caps else None

    # tolak langsung kalau tidak ada worker hidup untuk platform ini, daripada menunggu sampai tugasnya kedaluwarsa
    if not join_queue.has_worker(platform):
        return jsonify({"error": f"Tidak ada perekam {MEETING_PLATFORM_LABEL[platform]} yang aktif. Coba lagi sebentar lagi."}), 503

    job_id = uuid.uuid4().hex
    meetings_store.start_meeting(job_id, platform, title, estimated_participants=num_speakers, url=url, user_id=session["user_id"])
    # worker kosong yang mengambilnya (join_worker_loop), frontend memantau /jobs/<id>
    try:
        join_queue.enqueue({
            "job_id": job_id, "platform": platform, "url": url, "name": name, "max_duration": max_duration,
            "title": title, "num_speakers": num_speakers,
        })
    except Exception as e:
        meetings_store.update_meeting(job_id, status="failed")
        print(f"[join] could not queue {job_id}: {e}")
        return jsonify({"error": "Antrean join tidak bisa dijangkau. Coba lagi sebentar lagi."}), 503

    return jsonify({"job_id": job_id})


@bp.post("/google/join")
@login_required
def google_join():
    return _join("google_meet", "Rapat Google Meet")


@bp.post("/zoom/join")
@login_required
def zoom_join():
    return _join("zoom", "Rapat Zoom")


@bp.get("/jobs/<job_id>")
@login_required
def job_status(job_id):
    record = meetings_store.get_meeting(job_id)
    if record is not None and not common.can_view_meeting(record):
        return jsonify({"error": "Job not found"}), 404
    job = join_queue.get_job(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] == "failed":
        return jsonify({"status": "failed", "error": job.get("error")})
    resp = {"status": job["status"]}  # queued | joining | recording | stopping | processing
    if job["status"] == "recording" and job.get("started_at"):
        resp["elapsed_seconds"] = int(time.time() - float(job["started_at"]))
    return jsonify(resp)


@bp.post("/jobs/<job_id>/stop")
@login_required
def job_stop(job_id):
    """Hentikan rekaman lebih awal. Yang sudah terekam tetap diproses seperti biasa."""
    record = meetings_store.get_meeting(job_id)
    if record is not None and not common.can_edit_meeting(record):
        return jsonify(common.NOT_OWNER[0]), common.NOT_OWNER[1]
    job = join_queue.get_job(job_id)
    if job is None or job["status"] not in ("queued", *join_queue.LIVE):
        return jsonify({"error": "Job not found or no longer recording"}), 404
    join_queue.request_stop(job_id)  # worker yang merekam membacanya, lihat join_worker_loop
    return jsonify({"status": "stopping"})


@bp.post("/upload")
@login_required
def upload():
    """Transkripsi dan ringkas rekaman yang tidak dibuat oleh bot."""
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "file is required (multipart/form-data field 'file')"}), 400

    quota_error = common.check_meeting_quota(session["user_id"])
    if quota_error:
        return jsonify({"error": quota_error}), 402

    ext = Path(file.filename).suffix.lower()
    if ext not in UPLOAD_EXTENSIONS:
        return jsonify({"error": f"unsupported file type '{ext}', expected one of {sorted(UPLOAD_EXTENSIONS)}"}), 400

    # file disimpan lokal dulu (dipakai untuk memetakan waktu), lalu naik ke R2 sebelum diproses supaya Replicate bisa membacanya
    out_dir = Path(os.getenv("RECORDINGS_DIR", "recordings")) / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    meeting_id = f"Upload_{int(time.time())}"
    local_recording_path = str(out_dir / f"{meeting_id}{ext}")
    file.save(local_recording_path)

    num_speakers = request.form.get("num_speakers", type=int)  # opsional, diisi user

    # buat barisnya dulu supaya daftar menampilkan "Memproses..." selagi ini berjalan
    meetings_store.start_meeting(
        meeting_id, "upload", f"Upload: {file.filename}", estimated_participants=num_speakers, user_id=session["user_id"]
    )
    # durasi dibiarkan null, kita harus mendecode file lagi untuk mendapatkannya
    recording_key = storage.upload_recording(local_recording_path, meeting_id, keep_local=True)
    meetings_store.update_meeting(meeting_id, status="processing", recording=recording_key)

    result = process_recording(local_recording_path, meeting_id, num_speakers, recording_key)
    try:
        os.remove(local_recording_path)
    except OSError:
        pass
    result["status"] = "done"
    result["recording"] = recording_key
    final_status = "failed" if result.get("transcript_error") else "completed"
    meetings_store.update_meeting(meeting_id, status=final_status, recording=recording_key)
    return jsonify(result)
