"""Pengecekan izin dan bentuk untuk route yang memakai common.load_meeting, common.pdf, dan
super_admin_required. Database, R2, dan store lainnya dipalsukan.

Jalankan: python -m tests.test_routes   (dari backend/)"""
import app as server
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
print("ok")
