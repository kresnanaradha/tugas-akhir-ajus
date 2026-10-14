"""Pengecekan izin dan bentuk untuk route yang memakai _load_meeting, _pdf, dan
super_admin_required. Database, R2, dan store lainnya dipalsukan.

Jalankan: python -m tests.test_routes   (dari backend/)"""
import app as server

RECORD = {"id": "m1", "user_id": "owner", "recording": "m1/recording.webm", "status": "completed", "title": "T"}


def client_as(user_id, role="user"):
    c = server.app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["role"] = user_id, role
    return c


server.auth_store.is_active = lambda uid: True
server.get_meeting = lambda mid: dict(RECORD) if mid == "m1" else None
server.is_viewer = lambda mid, uid: uid == "viewer"
server.auth_store.get_user = lambda uid: {"team_id": None, "name": uid}
server.artifacts.load_summary = lambda mid: {"action_items": []}
server.artifacts.load_transcript = lambda mid: "t"
server.artifacts.load_fixed_transcript = lambda mid: "f"
server.artifacts.load_segments = lambda mid: []
server.storage.head = lambda key: {"size": 5}
server.update_meeting = lambda *a, **k: None
server.knowledge_base.remove_meeting = lambda mid: None

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

# ubah: pemilik dan super admin boleh, penonton tautan dapat 403, orang asing 404
url = "/meetings/m1/knowledge-base"
assert client_as("owner").post(url, json={"enabled": False}).status_code == 200
assert client_as("boss", "super_admin").post(url, json={"enabled": False}).status_code == 200
assert client_as("viewer").post(url, json={"enabled": False}).status_code == 403
assert client_as("stranger").post(url, json={"enabled": False}).status_code == 404

# route khusus super admin
server.admin_stats.get_stats = lambda: {"ok": 1}
assert client_as("owner").get("/admin/stats").status_code == 403
assert client_as("boss", "super_admin").get("/admin/stats").get_json() == {"ok": 1}

# job yang tidak berjalan
assert client_as("owner").get("/jobs/unknown").status_code == 404

with server.app.app_context():
    r = server._pdf(b"%PDF", "x.pdf")
    assert r.mimetype == "application/pdf" and "x.pdf" in r.headers["Content-Disposition"]
print("ok")
