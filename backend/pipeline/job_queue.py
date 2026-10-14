"""Serah terima lewat Redis dari perekam (app.py) ke transkriber (transcriber_service.py), mereka jalan di
container terpisah. Job yang diambil pindah secara atomik (BLMOVE) ke list pemrosesan per konsumen dan hanya
ack() yang menghapusnya, jadi transkriber yang mati di tengah job (OOM, docker kill) memasukkan lagi jobnya sendiri
saat start berikutnya (requeue_unfinished). Tiap requeue menambah percobaan, setelah MAX_ATTEMPTS rapat ditandai gagal
dan job masuk list dead letter.

Id konsumen harus tetap sama antar restart (docker-compose mengisi TRANSCRIBER_ID) atau restart akan
menelantarkan jobnya sendiri yang belum selesai."""

import json
import os

import redis

_QUEUE_KEY = "notulis:transcription_jobs"
_DEAD_KEY = "notulis:transcription_dead"
MAX_ATTEMPTS = 3
_client = None


def _processing_key(consumer_id: str) -> str:
    return f"notulis:transcription_processing:{consumer_id}"


def _get_client():
    global _client
    if _client is None:
        # socket_timeout harus lebih lama dari timeout BLMOVE atau redis-py melempar "Timeout reading from
        # socket" alih-alih menerima nil
        _client = redis.from_url(os.environ["REDIS_URL"], decode_responses=True, socket_timeout=30)
    return _client


def enqueue_transcription(meeting_id: str, recording_key: str, num_speakers: int | None) -> None:
    _get_client().rpush(
        _QUEUE_KEY,
        json.dumps({"meeting_id": meeting_id, "recording_key": recording_key, "num_speakers": num_speakers, "attempts": 0}),
    )


def claim(consumer_id: str, timeout: int = 5) -> tuple[dict, str] | None:
    """Tunggu sampai `timeout` detik untuk sebuah job dan pindahkan ke list pemrosesan konsumen ini. Mengembalikan (job,
    raw), berikan `raw` ke ack() saat selesai, atau None kalau tidak ada yang datang. Jangan pakai 0, itu menunggu selamanya."""
    raw = _get_client().blmove(_QUEUE_KEY, _processing_key(consumer_id), timeout, "LEFT", "RIGHT")
    if raw is None:
        return None
    return json.loads(raw), raw


def ack(consumer_id: str, raw: str) -> None:
    _get_client().lrem(_processing_key(consumer_id), 1, raw)


def requeue_unfinished(consumer_id: str) -> tuple[list[dict], list[dict]]:
    """Panggil sekali saat start: ambil kembali yang sedang dikerjakan konsumen ini saat mati. Mengembalikan (requeued,
    exhausted). Job requeued ke depan antrean dengan attempts + 1, yang exhausted (sudah MAX_ATTEMPTS)
    masuk dead letter supaya pemanggil bisa menandai rapatnya gagal."""
    client = _get_client()
    key = _processing_key(consumer_id)
    requeued, exhausted = [], []
    while True:
        raw = client.lpop(key)
        if raw is None:
            break
        job = json.loads(raw)
        job["attempts"] = job.get("attempts", 0) + 1
        if job["attempts"] >= MAX_ATTEMPTS:
            client.rpush(_DEAD_KEY, json.dumps(job))
            exhausted.append(job)
        else:
            client.lpush(_QUEUE_KEY, json.dumps(job))
            requeued.append(job)
    return requeued, exhausted
