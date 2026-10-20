"""Uji manual (butuh Redis sungguhan dari docker compose, tidak menyentuh database atau R2): antrean join dari ujung ke
ujung. Kunci diberi akhiran uji dan dibersihkan di akhir.

Jalankan: docker compose up -d redis && docker compose run --rm --no-deps -T -v ./pipeline:/app/pipeline -v ./tests:/app/tests worker-1 python -m tests.try_join_queue_redis"""
import time

from pipeline import join_queue as q
from pipeline.job_queue import _get_client

q.WORKER_ID = "uji-worker"
q.PLATFORMS = ["zoom"]
job = {"job_id": "uji1", "platform": "zoom", "url": "u", "name": "n", "max_duration": None, "title": "T", "num_speakers": None}

q.enqueue(job)
assert q.get_job("uji1")["status"] == "queued"
t0 = time.time()
got = q.claim(timeout=2)
assert got["job_id"] == "uji1" and q.claim(timeout=1) is None
print("claim ok, selang", round(time.time() - t0, 2), "detik")

assert not q.has_worker("zoom")
q.heartbeat(False)
assert q.has_worker("zoom") and not q.has_worker("google_meet")
print("worker terdaftar:", q.workers())

q.set_job("uji1", status="recording", started_at=time.time(), worker="uji-worker")
assert q.get_job("uji1")["status"] == "recording"
q.request_stop("uji1")
assert q.stop_requested("uji1")

r = _get_client()
r.delete(f"notulis:worker:uji-worker")
assert q.get_job("uji1")["status"] == "failed"  # worker mati
q.finish("uji1")
assert q.get_job("uji1") is None and not q.stop_requested("uji1")
print("ok")
