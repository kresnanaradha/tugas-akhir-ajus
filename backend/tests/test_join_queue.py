"""Antrean join: urutan tugas per platform, status, sinyal Stop, deteksi worker mati, dan /join /jobs di app.py. Redis
dipalsukan (dict), tidak menyentuh database, R2, atau bot sungguhan.

Jalankan: python -m tests.test_join_queue   (dari backend/)"""
import json
import time

import app as server
from pipeline import auth_store, meetings_store
from pipeline import join_queue as q
from routes import common


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
auth_store.is_active = lambda uid: True
meetings_store.get_meeting = lambda mid: None
meetings_store.update_meeting = lambda *a, **k: None
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
meetings_store.start_meeting = lambda *a, **k: None
meetings_store.find_meeting_by_url = lambda url: None
common.check_meeting_quota = lambda uid: None
common.plan_limits = lambda uid: {"max_duration_minutes": None}
meet_url = {"url": "https://meet.google.com/abc-defg-hij"}
assert c.post("/google/join", json=meet_url).status_code == 503
assert c.post("/zoom/join", json={"url": "https://us02web.zoom.us/j/123456789"}).status_code == 200
queued = json.loads(fake.lists["notulis:join_jobs:zoom"][-1])
assert queued["platform"] == "zoom" and queued["title"] == "Rapat Zoom"

# tautan yang sama dengan rapat orang lain: tanpa bot kedua. User kedua mendapat rapat salinan sendiri (id baru). Yang sumbernya
# sudah selesai tersalin sekarang, yang masih berjalan tersalin nanti oleh transkriber
from routes import recording  # noqa: E402

created, finished = [], []
meetings_store.find_follower = lambda src, uid: None
meetings_store.create_follower = lambda src, uid: created.append((src["id"], uid)) or "copy1"
recording.followers.finish_follower = lambda fid, src: finished.append((fid, src["id"]))


class Inline:  # menjalankan thread langsung supaya hasilnya bisa diperiksa
    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


recording.threading.Thread = Inline
n_jobs = len(fake.lists["notulis:join_jobs:zoom"])
zoom_url = {"url": "https://us02web.zoom.us/j/123456789"}

meetings_store.find_meeting_by_url = lambda url: {"id": "old", "user_id": "someone-else", "status": "completed"}
resp = c.post("/zoom/join", json=zoom_url).get_json()
assert resp == {"job_id": "copy1", "shared": True}  # id rapat salinan, bukan id rapat orang lain
assert created == [("old", "owner")] and finished == [("copy1", "old")]
assert len(fake.lists["notulis:join_jobs:zoom"]) == n_jobs  # tidak ada bot kedua

created.clear(); finished.clear()
meetings_store.find_meeting_by_url = lambda url: {"id": "old", "user_id": "someone-else", "status": "recording"}
c.post("/zoom/join", json=zoom_url)
assert created == [("old", "owner")] and finished == []  # masih berjalan: hasilnya disalin nanti saat sumber selesai

created.clear()
meetings_store.find_follower = lambda src, uid: "copy1"  # ditempel dua kali: tetap rapat salinan yang sama
assert c.post("/zoom/join", json=zoom_url).get_json() == {"job_id": "copy1", "shared": True} and created == []

meetings_store.find_follower = lambda src, uid: None
meetings_store.find_meeting_by_url = lambda url: {"id": "mine", "user_id": "owner", "status": "completed"}
assert c.post("/zoom/join", json=zoom_url).get_json() == {"job_id": "mine", "shared": True} and created == []  # rapat sendiri

# salinan ikut jatah rapat bulanan: kuota habis ditolak, rapat tidak dibuat
meetings_store.find_meeting_by_url = lambda url: {"id": "old", "user_id": "someone-else", "status": "recording"}
common.check_meeting_quota = lambda uid: "Jatah rapat bulan ini habis"
assert c.post("/zoom/join", json=zoom_url).status_code == 402 and created == []
print("ok")
