"""Pipeline transcribe -> fix -> summarize -> email untuk satu rekaman, dipakai bersama oleh container transkriber
dan endpoint /upload."""

import os

from . import auth_store, mailer
from .meetings_store import get_meeting
from .summarize import fix_transcript, summarize
from .transcribe import transcribe


def process_recording(local_recording_path: str, meeting_id: str, num_speakers: int | None = None, recording_key: str | None = None) -> dict:
    """Jalankan pipeline pada file lokal (whisperx butuh file). Tiap langkah melaporkan errornya sendiri di
    hasil, jadi langkah yang gagal tidak membuang rekaman. num_speakers adalah tebakan user dan membantu
    diarization. recording_key (rekaman di R2) dipakai kalau transkripsi lewat Replicate. Kunci hasil: transcript,
    fixed_transcript, summary, dan *_error untuk yang gagal."""
    result = {}
    try:
        transcript = transcribe(local_recording_path, meeting_id, num_speakers=num_speakers, recording_key=recording_key)
        result["transcript"] = transcript
    except Exception as e:
        result["transcript_error"] = str(e)
        return result

    # ringkas transkrip yang sudah diperbaiki kalau langkah itu berhasil, kalau tidak yang mentah
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
    """Email pemilik bahwa ringkasan siap, kecuali mereka mematikannya. Tidak pernah melempar error."""
    try:
        record = get_meeting(meeting_id)
        user = auth_store.get_user(record["user_id"]) if record and record.get("user_id") else None
        if not user or not user["email_notifications"]:
            return
        frontend = os.getenv("LOCAL_FRONTEND_URL", "http://localhost:8081")
        mailer.send_meeting_ready_email(
            to_email=user["email"],
            title=record["title"],
            summary_excerpt=(summary.get("executive_summary") or "").split("\n\n")[0],
            meeting_url=f"{frontend}/rapat/{meeting_id}",
        )
    except Exception as e:
        print(f"[mailer] failed to notify for meeting {meeting_id}: {e}")
