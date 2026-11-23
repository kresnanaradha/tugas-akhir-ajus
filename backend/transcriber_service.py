"""Worker untuk container transkriber (Dockerfile.transcriber, transcriber-1/2 di docker-compose.yml).
Mengambil job yang didorong perekam ke Redis, menjalankan pipeline atasnya dan menulis hasilnya ke Postgres dan
R2. Dipisah dari app.py supaya Chrome (merekam) dan whisper tidak pernah berbagi memori satu container, itu yang
membuat tes langsung kena OOM-kill. Tanpa Flask, hanya loop: python transcriber_service.py"""

import os
import socket
import tempfile
import threading
import time

from dotenv import load_dotenv

load_dotenv()

from pipeline import followers, job_queue, storage  # noqa: E402 (setelah load_dotenv)
from pipeline.meetings_store import update_meeting  # noqa: E402
from pipeline.process import process_recording  # noqa: E402

# harus tetap sama saat container ini restart (compose mengisinya per service): itu menamai list Redis
# berisi job worker ini yang belum selesai. Hostname hanya cocok untuk satu kali jalan tanpa Docker.
CONSUMER_ID = os.getenv("TRANSCRIBER_ID", socket.gethostname())


# rapat yang sedang dikerjakan, dibaca utas detak. Satu rapat bisa berpuluh menit, loop utama tidak berdetak selama itu
_current = {"meeting_id": None}
_HEARTBEAT_S = 5


def _heartbeat_loop() -> None:
    while True:
        try:
            job_queue.transcriber_heartbeat(CONSUMER_ID, _current["meeting_id"])
        except Exception as e:
            print(f"[transcriber] heartbeat failed: {e}")
        time.sleep(_HEARTBEAT_S)


def _process_job(job: dict) -> None:
    meeting_id = job["meeting_id"]
    recording_key = job["recording_key"]
    print(f"[transcriber] picked up {meeting_id}")

    fd, local_path = tempfile.mkstemp(suffix=os.path.splitext(recording_key)[1] or ".webm")
    os.close(fd)
    try:
        storage.download_to_file(recording_key, local_path)
        result = process_recording(local_path, meeting_id, job.get("num_speakers"), recording_key)
        for step in ("transcript_error", "fix_transcript_error", "summary_error"):
            if step in result:
                print(f"[transcriber] {meeting_id} {step}: {result[step]}")
        # hanya transkrip yang gagal yang menggagalkan rapat, ringkasan yang hilang bisa dibuat ulang dari editor
        update_meeting(meeting_id, status="failed" if "transcript_error" in result else "completed")
        if "transcript_error" not in result:
            try:
                followers.copy_results(meeting_id)  # salin hasilnya ke rapat User lain yang memakai tautan yang sama
            except Exception as e:
                print(f"[transcriber] {meeting_id} copy to followers failed: {e}")
        print(f"[transcriber] {meeting_id} done")
    finally:
        os.unlink(local_path)


def main():
    # apa pun yang dikerjakan worker ini saat mati (OOM, reboot, docker kill) masih ada di list
    # pemrosesannya: coba lagi, atau setelah MAX_ATTEMPTS crash tandai rapat gagal supaya job yang
    # selalu membunuh worker tidak berputar selamanya
    requeued, exhausted = job_queue.requeue_unfinished(CONSUMER_ID)
    for job in requeued:
        print(f"[transcriber] re-queued unfinished job {job['meeting_id']} (attempt {job['attempts'] + 1})")
    for job in exhausted:
        update_meeting(job["meeting_id"], status="failed")
        print(f"[transcriber] giving up on {job['meeting_id']} after {job['attempts']} crashed attempts")

    threading.Thread(target=_heartbeat_loop, daemon=True).start()
    print(f"[transcriber] {CONSUMER_ID} waiting for jobs...")
    while True:
        try:
            claimed = job_queue.claim(CONSUMER_ID, timeout=5)
        except Exception as e:
            # gangguan Redis tidak boleh mematikan worker yang berjalan lama
            print(f"[transcriber] queue read failed, retrying: {e}")
            time.sleep(2)
            continue
        if claimed is None:
            continue
        job, raw = claimed
        _current["meeting_id"] = job.get("meeting_id")
        try:
            _process_job(job)
        except Exception as e:
            # bukan crash, jadi percobaan ulang akan gagal dengan cara yang sama (misalnya rekaman hilang dari R2):
            # gagalkan rapat dan lanjut daripada membiarkannya "processing" selamanya
            print(f"[transcriber] unhandled error on {job.get('meeting_id')}: {e}")
            try:
                update_meeting(job["meeting_id"], status="failed")
            except Exception as inner:
                print(f"[transcriber] could not mark {job.get('meeting_id')} failed: {inner}")
        finally:
            _current["meeting_id"] = None
            try:
                job_queue.ack(CONSUMER_ID, raw)
            except Exception as e:
                print(f"[transcriber] ack failed for {job.get('meeting_id')}: {e}")


if __name__ == "__main__":
    main()
