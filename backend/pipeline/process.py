"""Pipeline transcribe -> fix -> summarize -> email untuk satu rekaman, dipakai bersama oleh container transkriber
dan endpoint /upload."""

import os

from . import auth_store, mailer
from .meetings_store import get_meeting, list_viewers
from .summarize import fix_transcript, summarize
from .transcribe import transcribe


def process_recording(local_recording_path: str, meeting_id: str, num_speakers: int | None = None, recording_key: str | None = None) -> dict:
    """Jalankan pipeline pada rekaman. File lokalnya dipakai untuk memetakan waktu ke jam video, transkripsinya lewat
    Replicate dari recording_key (rekaman di R2). Tiap langkah melaporkan errornya sendiri di hasil, jadi langkah
    yang gagal tidak membuang rekaman. num_speakers adalah tebakan user dan membantu diarization. Kunci hasil:
    transcript, fixed_transcript, summary, dan *_error untuk yang gagal."""
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
        notify_meeting_ready(meeting_id, result["summary"])
    return result


def notify_meeting_ready(meeting_id: str, summary: dict, only_user_id: str | None = None) -> None:
    """Email bahwa ringkasan siap ke pemilik dan ke penonton rapat (pengguna yang memasukkan tautan yang sama, mereka dapat
    email berkata lain karena bot tidak dikirim dua kali), kecuali yang mematikan notifikasi. only_user_id: hanya penonton
    itu, untuk yang bergabung setelah rapat selesai diproses. Tidak pernah melempar error, gagal satu tidak menghentikan yang lain."""
    try:
        record = get_meeting(meeting_id)
        if not record:
            return
        if only_user_id:
            recipients = [(auth_store.get_user(only_user_id), True)]
        else:
            owner = auth_store.get_user(record["user_id"]) if record.get("user_id") else None
            recipients = [(owner, False)] + [(v, True) for v in list_viewers(meeting_id)]
        frontend = os.getenv("LOCAL_FRONTEND_URL", "http://localhost:8081")
        mail = dict(
            title=record["title"],
            summary_excerpt=(summary.get("executive_summary") or "").split("\n\n")[0],
            meeting_url=f"{frontend}/rapat/{meeting_id}",
        )
    except Exception as e:
        print(f"[mailer] failed to notify for meeting {meeting_id}: {e}")
        return
    for user, shared in recipients:
        if not user or user.get("email_notifications") is False:  # NULL di database dianggap menyala
            continue
        try:
            mailer.send_meeting_ready_email(to_email=user["email"], shared=shared, **mail)
        except Exception as e:
            print(f"[mailer] failed to notify {user['email']} for meeting {meeting_id}: {e}")
