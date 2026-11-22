"""Pengecekan izin dan bentuk untuk route yang memakai common.load_meeting, common.pdf, dan
super_admin_required. Database, R2, dan store lainnya dipalsukan.

Jalankan: python -m tests.test_routes   (dari backend/)"""
import app as server
from routes import auth
from pipeline import admin_stats, artifacts, auth_store, join_queue, knowledge_base, meetings_store, storage
from routes import common

RECORD = {"id": "m1", "user_id": "owner", "recording": "m1/recording.webm", "status": "completed", "title": "T"}


def client_as(user_id, role="user"):
    c = server.app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["role"] = user_id, role
    return c


auth_store.is_active = lambda uid: True
meetings_store.get_meeting = lambda mid: dict(RECORD) if mid == "m1" else None
meetings_store.is_viewer = lambda mid, uid: uid == "viewer"
auth_store.get_user = lambda uid: {"team_id": None, "name": uid}
artifacts.load_summary = lambda mid: {"action_items": []}
artifacts.load_transcript = lambda mid: "t"
artifacts.load_fixed_transcript = lambda mid: "f"
artifacts.load_segments = lambda mid: []
storage.head = lambda key: {"size": 5}
meetings_store.update_meeting = lambda *a, **k: None
knowledge_base.remove_meeting = lambda mid: None

# belum login
assert server.app.test_client().get("/meetings/m1").status_code == 401

# lihat: pemilik, penonton, dan super admin bisa melihat, orang asing dapat 404, rapat yang tidak ada juga
assert client_as("owner").get("/meetings/m1").status_code == 200
assert client_as("viewer").get("/meetings/m1").status_code == 200
assert client_as("boss", "super_admin").get("/meetings/m1").status_code == 200
assert client_as("stranger").get("/meetings/m1").status_code == 404
assert client_as("owner").get("/meetings/nope").status_code == 404

detail = client_as("owner").get("/meetings/m1").get_json()
assert detail["transcript"] == "t" and detail["file_extension"] == "webm" and detail["file_size_bytes"] == 5
# can_edit dipakai frontend untuk menyembunyikan tombol ubah
assert detail["can_edit"] is True and client_as("viewer").get("/meetings/m1").get_json()["can_edit"] is False

# ubah: pemilik dan super admin boleh, penonton tautan dapat 403, orang asing 404
url = "/meetings/m1/knowledge-base"
assert client_as("owner").post(url, json={"enabled": False}).status_code == 200
assert client_as("boss", "super_admin").post(url, json={"enabled": False}).status_code == 200
assert client_as("viewer").post(url, json={"enabled": False}).status_code == 403
assert client_as("stranger").post(url, json={"enabled": False}).status_code == 404

# route khusus super admin
admin_stats.get_stats = lambda: {"ok": 1}
assert client_as("owner").get("/admin/stats").status_code == 403
assert client_as("boss", "super_admin").get("/admin/stats").get_json() == {"ok": 1}

# job yang tidak berjalan (status job ada di Redis, dipalsukan)
join_queue.get_job = lambda job_id: None
assert client_as("owner").get("/jobs/unknown").status_code == 404

with server.app.app_context():
    r = common.pdf(b"%PDF", "x.pdf")
    assert r.mimetype == "application/pdf" and "x.pdf" in r.headers["Content-Disposition"]

# CORS: hanya alamat frontend sendiri yang mendapat izin dengan cookie, origin lain tidak dipantulkan
front = common.LOCAL_FRONTEND_URL.rstrip("/")
anon = server.app.test_client()
ok = anon.get("/auth/me", headers={"Origin": front})
assert ok.headers["Access-Control-Allow-Origin"] == front and ok.headers["Access-Control-Allow-Credentials"] == "true"
evil = anon.get("/auth/me", headers={"Origin": "https://jahat.example"})
assert "Access-Control-Allow-Origin" not in evil.headers and "Access-Control-Allow-Credentials" not in evil.headers
pre = anon.options("/auth/login", headers={"Origin": "https://jahat.example", "Access-Control-Request-Method": "POST"})
assert "Access-Control-Allow-Origin" not in pre.headers
assert "Origin" in ok.headers["Vary"]

# cookie sesi: HttpOnly dan SameSite terpasang (Secure hanya dengan COOKIE_SECURE=1, tidak di tes lokal)
assert server.app.config["SESSION_COOKIE_HTTPONLY"] is True and server.app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


# pembatas percobaan (Redis dipalsukan): 5 login gagal per email, lalu 429 walau password benar. Email lain tidak terpengaruh
class FakeRedis:
    def __init__(self):
        self.kv = {}

    def get(self, k):
        return self.kv.get(k)

    def set(self, k, v, ex=None, nx=False):
        if not (nx and k in self.kv):
            self.kv[k] = v

    def incr(self, k):
        self.kv[k] = int(self.kv[k]) + 1

    def delete(self, k):
        self.kv.pop(k, None)


join_queue._get_client = lambda: FakeRedis_instance
FakeRedis_instance = FakeRedis()
good = {"id": "u1", "email": "a@b.c", "name": "A", "role": "user", "active": True}
auth_store.verify_login = lambda email, pw: good if pw == "benar" else None


def login(email, pw):
    return anon.post("/auth/login", json={"email": email, "password": pw})


for _ in range(5):
    assert login("a@b.c", "salah").status_code == 401
assert login("a@b.c", "benar").status_code == 429  # terkunci walau benar
assert login("A@B.C", "benar").status_code == 429  # huruf besar tidak melewati pembatas
assert login("lain@b.c", "benar").status_code == 200  # email lain tidak terkunci
FakeRedis_instance.kv.clear()
for _ in range(3):
    login("a@b.c", "salah")
assert login("a@b.c", "benar").status_code == 200  # berhasil sebelum terkunci: hitungan email direset
assert FakeRedis_instance.get("notulis:rl:login:email:a@b.c") is None
# lupa password: 3 email per alamat per jam, sesudahnya diam-diam dilewati dan jawabannya tetap ok
mails = []
auth_store.get_row_by_email = lambda e: {"id": "u1", "email": e, "name": "A", "active": True, "password_hash": "x" * 20}
auth.mailer.send_password_reset_email = lambda *a: mails.append(a)
FakeRedis_instance.kv.clear()
for _ in range(5):
    r = anon.post("/auth/forgot", json={"email": "a@b.c"})
    assert r.status_code == 200 and r.get_json() == {"ok": True}
assert len(mails) == 3  # yang keempat dan kelima tidak mengirim email, tapi jawabannya sama
anon.post("/auth/forgot", json={"email": "lain@b.c"})
assert len(mails) == 4  # alamat lain tidak terpengaruh

# Redis mati: pembatas dilewati, login tetap bisa
join_queue._get_client = lambda: (_ for _ in ()).throw(RuntimeError("redis mati"))
assert login("a@b.c", "benar").status_code == 200

# nonaktifkan akun sendiri: Super Admin ditolak (jangan sampai tidak ada admin), User biasa boleh
deactivated = []
auth_store.update_user = lambda uid, **k: deactivated.append((uid, k))
assert client_as("sa", "super_admin").post("/auth/me/deactivate").status_code == 400 and not deactivated
assert client_as("u1").post("/auth/me/deactivate").status_code == 200 and deactivated == [("u1", {"active": False})]

# ubah nama rapat: hanya pemilik atau super admin, tidak boleh kosong atau terlalu panjang
renamed = []
meetings_store.update_meeting = lambda mid, **f: renamed.append((mid, f))
meetings_store.get_meeting = lambda mid: dict(RECORD) if mid == "m1" else None
owner = client_as("owner")
assert owner.patch("/meetings/m1", json={"title": "  Sprint Planning Proyek X  "}).get_json() == {"title": "Sprint Planning Proyek X"}
assert renamed == [("m1", {"title": "Sprint Planning Proyek X"})]
assert owner.patch("/meetings/m1", json={"title": "   "}).status_code == 400
assert owner.patch("/meetings/m1", json={"title": "x" * 121}).status_code == 400
assert client_as("viewer").patch("/meetings/m1", json={"title": "Curian"}).status_code in (403, 404)  # penonton tidak bisa mengubah
assert client_as("sa", "super_admin").patch("/meetings/m1", json={"title": "Admin"}).status_code == 200
assert len(renamed) == 2  # hanya dua yang berhasil

# hapus rapat yang berbagi berkas rekaman: berkas dibiarkan selama masih dipakai rapat lain, yang terakhir membersihkannya
deleted = []
storage.delete_prefix = lambda prefix, keep=None: deleted.append(("prefix", prefix, keep))
storage.delete_object = lambda key: deleted.append(("object", key))
meetings_store.delete_meeting = lambda mid: None
meetings_store.get_meeting = lambda mid: {"id": mid, "user_id": "owner", "status": "completed", "recording": "m1/recording.webm"}
for rid, refs, expected in (
    ("m1", 1, [("prefix", "m1/", "m1/recording.webm")]),  # sumber, masih ada salinan: rekaman dibiarkan
    ("m1", 0, [("prefix", "m1/", None)]),  # sumber tanpa salinan: semuanya dihapus
    ("c1", 1, [("prefix", "c1/", "m1/recording.webm")]),  # salinan, sumber atau salinan lain masih ada
    ("c1", 0, [("prefix", "c1/", None), ("object", "m1/recording.webm")]),  # salinan terakhir: rekaman sumber ikut dibersihkan
):
    deleted.clear()
    meetings_store.recording_refs = lambda rec, mid, refs=refs: refs
    assert client_as("owner").delete(f"/meetings/{rid}").status_code == 200 and deleted == expected, (rid, refs, deleted)

# /upload langsung kembali dengan id rapat dan mengantre ke transkriber (tidak memproses di request)
import io
from pipeline import job_queue

queued = []
common.check_meeting_quota = lambda uid: None
meetings_store.start_meeting = lambda *a, **k: None
storage.upload_recording = lambda path, mid, keep_local=False: f"{mid}/recording.mp3"
job_queue.enqueue_transcription = lambda *a: queued.append(a)
r = client_as("owner").post("/upload", data={"file": (io.BytesIO(b"abc"), "rapat.mp3"), "num_speakers": "3"})
body = r.get_json()
assert r.status_code == 200 and body["status"] == "processing" and body["meeting_id"].startswith("Upload_")
assert queued == [(body["meeting_id"], body["meeting_id"] + "/recording.mp3", 3)]
print("ok")
