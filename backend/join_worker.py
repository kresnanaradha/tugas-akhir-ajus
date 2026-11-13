"""Sisi perekam: ambil tugas join dari antrean Redis satu per satu, jalankan bot, lalu serahkan rekamannya ke
transkriber. Dijalankan app.py di thread latar (kecuali RECORDER=0)."""

import threading
import time

from bots import google_session_keepalive
from bots.google_meet import GoogleMeetBot
from bots.zoom import ZoomBot
from pipeline import auth_store, job_queue, join_queue, mailer, meetings_store, storage
from routes import common


# status job (queued, joining, recording, stopping, processing, failed) ada di Redis, lihat pipeline/join_queue.py
_BOT_CLASSES = {"google_meet": GoogleMeetBot, "zoom": ZoomBot}


def run_join_job(job_id: str, bot, platform: str, title: str, num_speakers: int | None):
    started_at = time.time()
    try:
        local_recording_path = bot.join()
    except Exception as e:
        join_queue.set_job(job_id, status="failed", error=str(e))
        meetings_store.update_meeting(job_id, status="failed")
        return
    # waktu yang dipakai merekam, bukan seluruh proses join (browser mulai, menunggu di lobi)
    if bot.record_started_at and bot.record_ended_at:
        duration_minutes = round((bot.record_ended_at - bot.record_started_at) / 60, 1)
    else:
        duration_minutes = round((time.time() - started_at) / 60, 1)

    join_queue.set_job(job_id, status="processing")

    # unggah, lalu serahkan ke transkriber lewat Redis (whisper satu container dengan chrome
    # kehabisan memori)
    recording_key = storage.upload_recording(local_recording_path, job_id)
    # Menit mingguan Free untuk pemrosesan AI, bukan batas rekaman. Rekaman yang lebih panjang dari sisa
    # disimpan tapi tidak diproses (semua atau tidak sama sekali). Dicek sebelum menit rapat ini disimpan
    # supaya tidak terhitung terhadap dirinya sendiri.
    owner_id = (meetings_store.get_meeting(job_id) or {}).get("user_id")
    weekly = common.weekly_quota(owner_id) if owner_id else None
    if weekly and duration_minutes > weekly["remaining"]:
        meetings_store.update_meeting(job_id, status="limited", recording=recording_key, duration_minutes=duration_minutes)
        send_unprocessed_email(owner_id, job_id, title, duration_minutes, weekly)
    else:
        meetings_store.update_meeting(job_id, status="processing", recording=recording_key, duration_minutes=duration_minutes)
        job_queue.enqueue_transcription(job_id, recording_key, num_speakers)

    # buang job-nya supaya GET /jobs/<id> 404, frontend lalu memantau baris rapatnya
    join_queue.finish(job_id)


def send_unprocessed_email(owner_id: str, meeting_id: str, title: str, duration_minutes: float, weekly: dict) -> None:
    """Beri tahu pemilik bahwa rekaman disimpan tapi belum diproses AI (sebisanya)."""
    try:
        owner = auth_store.get_user(owner_id)
        if not owner["email_notifications"]:
            return  # toggle di Pengaturan berlaku untuk semua email kecuali reset password dan undangan
        mailer.send_meeting_unprocessed_email(
            owner["email"], owner["name"], title, duration_minutes, weekly["remaining"], weekly["limit"],
            f"{common.LOCAL_FRONTEND_URL}/rapat/{meeting_id}", f"{common.LOCAL_FRONTEND_URL}/billing",
        )
    except Exception as e:
        print(f"[quota] unprocessed-meeting email failed: {e}")


def _on_bot_status(job_id: str, status: str) -> None:
    meetings_store.update_meeting(job_id, status=status)  # supaya daftar rapat bisa menampilkan "Sedang Merekam"
    fields = {"status": status}
    if status == "recording":
        fields["started_at"] = time.time()
    join_queue.set_job(job_id, **fields)


def _reap_dead_jobs(include_self: bool = False) -> None:
    """Rapat yang worker perekamnya mati di tengah jalan: tandai gagal (job di Redis dan barisnya), supaya tidak
    "merekam" selamanya. Aman dijalankan oleh banyak worker sekaligus."""
    for job_id in join_queue.orphans(include_self):
        join_queue.set_job(job_id, status="failed", error="Worker perekam berhenti di tengah rapat")
        meetings_store.update_meeting(job_id, status="failed")
        print(f"[join-worker] rapat {job_id} ditandai gagal, worker perekamnya mati")


def _check_google_session() -> None:
    """Cek sesi Google worker ini (hanya saat menganggur). Habis: Meet berhenti diambil dan super admin diberi email
    sekali. Pulih (google_login.py dijalankan lagi): Meet diambil lagi."""
    try:
        expired = not google_session_keepalive.session_alive()  # menulis cookie yang baru dirotasi Google ke file sesi
    except Exception as e:
        print(f"[join-worker] cek sesi Google gagal, dilewati: {e}")  # jaringan atau file, belum tentu sesi habis
        return
    if expired and not join_queue.google_expired:
        print(f"[join-worker] sesi Google {join_queue.WORKER_ID} habis, Meet berhenti diambil")
        for admin in auth_store.list_users():
            if admin["role"] == "super_admin" and admin["active"]:
                try:
                    mailer.send_google_session_expired_email(admin["email"], join_queue.WORKER_ID)
                except Exception as e:
                    print(f"[join-worker] email sesi Google gagal: {e}")
    elif not expired and join_queue.google_expired:
        print(f"[join-worker] sesi Google {join_queue.WORKER_ID} pulih")
    join_queue.google_expired = expired


def join_worker_loop() -> None:
    """Ambil tugas join dari Redis satu per satu: satu bot per display, dua bot akan merekam jendela satu sama lain.
    Thread kecil menjaga detak worker dan meneruskan sinyal Stop (di Redis) ke bot yang sedang merekam."""
    current = {"job_id": None, "bot": None}

    def keep_alive():
        ticks = 0
        while True:
            try:
                join_queue.heartbeat(current["job_id"] is not None)
                bot = current["bot"]
                if bot is not None and join_queue.stop_requested(current["job_id"]):
                    bot.stop_event.set()
                ticks += 1
                if ticks % 30 == 0:  # tiap ~60 detik
                    _reap_dead_jobs()
            except Exception as e:
                print(f"[join-worker] heartbeat failed: {e}")  # gangguan Redis tidak boleh mematikan worker
            time.sleep(2)

    try:
        _reap_dead_jobs(include_self=True)  # job milik worker ini sebelum restart tidak mungkin masih jalan
    except Exception as e:
        print(f"[join-worker] reap saat start gagal: {e}")
    threading.Thread(target=keep_alive, daemon=True).start()
    print(f"[join-worker] {join_queue.WORKER_ID} menunggu tugas untuk {', '.join(join_queue.PLATFORMS)}")
    next_session_check = 0.0
    while True:
        # sesi Google dicek antar tugas (bukan saat merekam): 30 menit sekali, 5 menit sekali selagi habis
        if "google_meet" in join_queue.PLATFORMS and time.time() >= next_session_check:
            _check_google_session()
            next_session_check = time.time() + (300 if join_queue.google_expired else 1800)
        try:
            job = join_queue.claim(timeout=5)
        except Exception as e:
            print(f"[join-worker] queue read failed, retrying: {e}")
            time.sleep(2)
            continue
        if job is None:
            continue
        job_id = job["job_id"]
        try:
            if join_queue.stop_requested(job_id):
                join_queue.set_job(job_id, status="failed", error="Dibatalkan sebelum bot bergabung")
                meetings_store.update_meeting(job_id, status="failed")
            elif time.time() - job["enqueued_at"] > join_queue.MAX_WAIT_S:
                join_queue.set_job(job_id, status="failed", error="Tidak ada perekam yang kosong, coba lagi")
                meetings_store.update_meeting(job_id, status="failed")
            else:
                bot = _BOT_CLASSES[job["platform"]](
                    job["url"], job["name"], job["max_duration"], on_status_change=lambda s, j=job_id: _on_bot_status(j, s)
                )
                current.update(job_id=job_id, bot=bot)
                join_queue.set_job(job_id, status="joining", worker=join_queue.WORKER_ID)
                run_join_job(job_id, bot, job["platform"], job["title"], job["num_speakers"])
        except Exception as e:
            print(f"[join-worker] unhandled error on {job_id}: {e}")
            try:
                join_queue.set_job(job_id, status="failed", error=str(e))
                meetings_store.update_meeting(job_id, status="failed")
            except Exception as inner:
                print(f"[join-worker] could not mark {job_id} failed: {inner}")
        finally:
            current.update(job_id=None, bot=None)
