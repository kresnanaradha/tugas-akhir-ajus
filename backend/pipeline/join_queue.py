"""Antrean join lewat Redis: API menaruh tugas, worker perekam yang kosong mengambilnya. Status job dan sinyal Stop
rekam juga disimpan di Redis (bukan di memori satu proses), jadi API mana pun bisa melayani /jobs/<id> dan Stop, dan
worker bisa jalan di VPS lain asal memakai Redis yang sama.

Satu antrean per platform, worker hanya mengambil dari platform yang ia dukung (WORKER_PLATFORMS): Meet butuh sesi Google
yang sudah login, Zoom tidak butuh akun. Worker mendaftar dengan detak ber-TTL supaya API tahu ada yang hidup."""

import json
import os
import socket
import time

from pipeline.job_queue import _get_client

WORKER_ID = os.getenv("WORKER_ID", socket.gethostname())
PLATFORMS = [p.strip() for p in os.getenv("WORKER_PLATFORMS", "google_meet,zoom").split(",") if p.strip()]
# tugas yang menunggu lebih lama dari ini dibatalkan, rapatnya sudah keburu berjalan tanpa bot
MAX_WAIT_S = float(os.getenv("JOIN_QUEUE_MAX_WAIT_SECONDS", "600"))
LIVE = ("joining", "recording", "stopping")
_JOB_TTL_S = 6 * 3600
_WORKER_TTL_S = 15
# sesi Google worker ini habis (diatur loop worker di app.py): Meet tidak lagi diambil maupun diiklankan,
# supaya API menjawab 503 dengan jelas, bukan menerima join yang pasti gagal
google_expired = False


def active_platforms() -> list[str]:
    return [p for p in PLATFORMS if not (p == "google_meet" and google_expired)]


def _queue_key(platform: str) -> str:
    return f"notulis:join_jobs:{platform}"


def _job_key(job_id: str) -> str:
    return f"notulis:job:{job_id}"


def _stop_key(job_id: str) -> str:
    return f"notulis:job_stop:{job_id}"


def _worker_key(worker_id: str) -> str:
    return f"notulis:worker:{worker_id}"


def enqueue(job: dict) -> None:
    """job: job_id, platform, url, name, max_duration, title, num_speakers."""
    client = _get_client()
    job = {**job, "enqueued_at": time.time()}
    client.hset(_job_key(job["job_id"]), mapping={"status": "queued", "error": "", "worker": "", "started_at": ""})
    client.expire(_job_key(job["job_id"]), _JOB_TTL_S)
    client.rpush(_queue_key(job["platform"]), json.dumps(job))


def claim(timeout: int = 5) -> dict | None:
    """Tunggu sampai `timeout` detik untuk tugas di platform yang didukung worker ini. Jangan pakai 0 (menunggu selamanya)."""
    platforms = active_platforms()
    if not platforms:  # hanya Meet dan sesinya habis: BLPOP tanpa kunci error, jadi tunggu saja
        time.sleep(timeout)
        return None
    got = _get_client().blpop([_queue_key(p) for p in platforms], timeout)
    return json.loads(got[1]) if got else None


def set_job(job_id: str, **fields) -> None:
    client = _get_client()
    client.hset(_job_key(job_id), mapping={k: "" if v is None else v for k, v in fields.items()})
    client.expire(_job_key(job_id), _JOB_TTL_S)


def get_job(job_id: str) -> dict | None:
    client = _get_client()
    job = client.hgetall(_job_key(job_id))
    if not job:
        return None
    # worker yang merekam mati (detaknya hilang): jangan biarkan job "merekam" selamanya
    if job.get("status") in LIVE and job.get("worker") and not client.exists(_worker_key(job["worker"])):
        job.update(status="failed", error="Worker perekam berhenti di tengah rapat")
    return job


def orphans(include_self: bool = False) -> list[str]:
    """Job yang masih berstatus hidup tapi worker pemiliknya sudah mati (detak hilang). include_self juga mengambil
    job milik worker ini sendiri: dipanggil saat start, worker yang baru nyala tidak mungkin sedang memegang job."""
    client = _get_client()
    found = []
    for key in client.scan_iter("notulis:job:*"):
        job = client.hgetall(key)
        worker = job.get("worker")
        if job.get("status") in LIVE and worker and (
            not client.exists(_worker_key(worker)) or (include_self and worker == WORKER_ID)
        ):
            found.append(key.split(":", 2)[2])
    return found


def finish(job_id: str) -> None:
    """Rekaman selesai dan diserahkan: hapus job supaya /jobs/<id> 404 dan frontend memantau baris rapatnya."""
    _get_client().delete(_job_key(job_id), _stop_key(job_id))


def request_stop(job_id: str) -> None:
    _get_client().set(_stop_key(job_id), 1, ex=_JOB_TTL_S)


def stop_requested(job_id: str) -> bool:
    return bool(_get_client().exists(_stop_key(job_id)))


def heartbeat(busy: bool) -> None:
    info = {"platforms": active_platforms(), "busy": busy, "google_expired": google_expired}
    _get_client().set(_worker_key(WORKER_ID), json.dumps(info), ex=_WORKER_TTL_S)


def workers() -> list[dict]:
    client = _get_client()
    found = []
    for key in client.scan_iter("notulis:worker:*"):
        raw = client.get(key)
        if raw:
            found.append({"id": key.split(":", 2)[2], **json.loads(raw)})
    return found


def has_worker(platform: str) -> bool:
    return any(platform in w["platforms"] for w in workers())
