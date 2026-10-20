"""Antrean join: urutan tugas per platform, status, sinyal Stop, deteksi worker mati, dan /join /jobs di app.py. Redis
dipalsukan (dict), tidak menyentuh database, R2, atau bot sungguhan.

Jalankan: python -m tests.test_join_queue   (dari backend/)"""
import json
import time

import app as server
from pipeline import join_queue as q


class FakeRedis:
    def __init__(self):
        self.kv, self.hashes, self.lists, self.ttl = {}, {}, {}, {}

    def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update({k: str(v) for k, v in mapping.items()})

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def expire(self, key, seconds):
        self.ttl[key] = seconds

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def blpop(self, keys, timeout):
        for key in keys:
            if self.lists.get(key):
                return key, self.lists[key].pop(0)
        return None

    def set(self, key, value, ex=None):
        self.kv[key] = str(value)

    def get(self, key):
        return self.kv.get(key)

    def exists(self, key):
        return int(key in self.kv or key in self.hashes)

    def delete(self, *keys):
        for key in keys:
            self.kv.pop(key, None)
            self.hashes.pop(key, None)

    def scan_iter(self, pattern):
        prefix = pattern.rstrip("*")
        return [k for k in list(self.kv) + list(self.hashes) if k.startswith(prefix)]


fake = FakeRedis()
q._get_client = lambda: fake
job = {"job_id": "a", "platform": "zoom", "url": "u", "name": "n", "max_duration": None, "title": "T", "num_speakers": None}

# tugas diambil sesuai platform worker: worker khusus Zoom tidak mengambil tugas Meet
q.PLATFORMS = ["zoom"]
q.enqueue({**job, "job_id": "m", "platform": "google_meet"})
q.enqueue(job)
assert q.get_job("a")["status"] == "queued"
assert q.claim()["job_id"] == "a" and q.claim() is None

# status dan sinyal Stop (worker w1 hidup: detaknya ada)
q.WORKER_ID = "w1"
q.heartbeat(True)
q.set_job("a", status="recording", started_at=123.0, worker="w1")
assert q.get_job("a")["status"] == "recording"
assert q.has_worker("zoom") and not q.has_worker("google_meet")
assert not q.stop_requested("a")
q.request_stop("a")
assert q.stop_requested("a")

# worker yang merekam mati (detak hilang): job tampil gagal, bukan "merekam" selamanya
fake.delete("notulis:worker:w1")
assert q.get_job("a")["status"] == "failed"
q.heartbeat(True)

# selesai: job dan flag stop hilang
q.finish("a")
assert q.get_job("a") is None and not q.stop_requested("a")

# job yatim: worker pemiliknya mati, atau worker ini sendiri baru start (include_self)
q.set_job("o1", status="recording", worker="mati")  # tidak ada detak "mati"
q.set_job("o2", status="recording", worker="w1")  # w1 hidup
q.set_job("o3", status="processing", worker="mati")  # bukan status hidup
q.set_job("o4", status="queued", worker="")
assert q.orphans() == ["o1"]
assert sorted(q.orphans(include_self=True)) == ["o1", "o2"]
for oid in ("o1", "o2", "o3", "o4"):
    q.finish(oid)

# sesi Google habis: Meet tidak diiklankan dan tidak diambil, Zoom tetap
q.PLATFORMS = ["google_meet", "zoom"]
q.enqueue({**job, "job_id": "g", "platform": "google_meet"})
q.google_expired = True
assert q.active_platforms() == ["zoom"] and q.claim() is None
q.heartbeat(False)
assert q.has_worker("zoom") and not q.has_worker("google_meet")
assert [w for w in q.workers() if w["id"] == "w1"][0]["google_expired"] is True
q.google_expired = False
assert q.claim()["job_id"] == "m" and q.claim()["job_id"] == "g"  # "m" tertunda sejak awal tes
q.PLATFORMS = ["zoom"]
q.heartbeat(True)

# endpoint /jobs dan stop, dipalsukan lewat job di Redis palsu
server.auth_store.is_active = lambda uid: True
server.get_meeting = lambda mid: None
server.update_meeting = lambda *a, **k: None
c = server.app.test_client()
with c.session_transaction() as s:
    s["user_id"], s["role"] = "owner", "user"

q.enqueue({**job, "job_id": "b"})
assert c.get("/jobs/b").get_json() == {"status": "queued"}
q.set_job("b", status="recording", started_at=time.time() - 30, worker="w1")
resp = c.get("/jobs/b").get_json()
assert resp["status"] == "recording" and 29 <= resp["elapsed_seconds"] <= 31
assert c.post("/jobs/b/stop").status_code == 200 and q.stop_requested("b")
q.set_job("b", status="processing")
assert c.post("/jobs/b/stop").status_code == 404  # sudah tidak merekam
assert c.get("/jobs/nope").status_code == 404

# join: ditolak (503) kalau tidak ada worker untuk platform itu, selain itu tugasnya masuk antrean
server.start_meeting = lambda *a, **k: None
server.find_meeting_by_url = lambda url: None
server._check_meeting_quota = lambda uid: None
server._plan_limits = lambda uid: {"max_duration_minutes": None}
meet_url = {"url": "https://meet.google.com/abc-defg-hij"}
assert c.post("/google/join", json=meet_url).status_code == 503
assert c.post("/zoom/join", json={"url": "https://us02web.zoom.us/j/123456789"}).status_code == 200
queued = json.loads(fake.lists["notulis:join_jobs:zoom"][-1])
assert queued["platform"] == "zoom" and queued["title"] == "Rapat Zoom"
print("ok")
