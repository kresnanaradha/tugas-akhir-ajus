"""_run_join_job memutuskan antara "antre untuk AI" dan "simpan tanpa diproses" dari
sisa menit Free minggu ini. Semua di luar keputusan itu dipalsukan, jadi ini
tidak menyentuh database, R2, Redis, dan tidak mengirim email.

Jalankan: python -m tests.test_free_quota_flow   (dari backend/)"""
import app


class FakeBot:
    record_started_at = 1.0

    def __init__(self, minutes):
        self.record_ended_at = 1.0 + minutes * 60.0

    def join(self):
        return "recording.webm"


def run(minutes, remaining):
    calls = {"updates": [], "queued": [], "emails": []}
    app.storage.upload_recording = lambda path, job_id: "key"
    app.update_meeting = lambda job_id, **kw: calls["updates"].append(kw)
    app.get_meeting = lambda job_id: {"user_id": "u1"}
    app._weekly_quota = lambda uid: None if remaining is None else {"limit": 60, "used": 60 - remaining, "remaining": remaining}
    app.job_queue.enqueue_transcription = lambda *a: calls["queued"].append(a)
    app._send_unprocessed_email = lambda *a: calls["emails"].append(a)
    app.join_queue.set_job = lambda *a, **kw: None
    app.join_queue.finish = lambda *a: None
    app._run_join_job("j", FakeBot(minutes), "zoom", "T", None)
    return calls


# 20 menit muat di minggu yang baru: diproses.
c = run(20, 60)
assert c["updates"][-1]["status"] == "processing" and c["queued"] and not c["emails"]

# 45 menit padahal sisa 40: disimpan utuh, tidak diantre, pemilik diberi email.
c = run(45, 40)
assert c["updates"][-1]["status"] == "limited" and not c["queued"] and len(c["emails"]) == 1

# Tepat sebesar sisanya masih muat.
c = run(40, 40)
assert c["updates"][-1]["status"] == "processing" and c["queued"]

# Paket tanpa batas (tanpa kuota mingguan): selalu diproses.
c = run(500, None)
assert c["updates"][-1]["status"] == "processing" and c["queued"]


# POST /meetings/<id>/process: proses ulang rapat gagal, dengan kuota yang sama.
def process(status, minutes, remaining, recording="k", url="https://zoom.us/j/1", this_week=True):
    queued = []
    created = app._week_start() + app.timedelta(hours=1 if this_week else -1)
    record = {"id": "m", "user_id": "u1", "status": status, "duration_minutes": minutes, "recording": recording,
              "url": url, "estimated_participants": None, "created_at": created.strftime("%Y-%m-%dT%H:%M:%S")}
    app._load_meeting = lambda mid, edit=False: (record, None)
    app._user_is_active = lambda uid: True
    app.update_meeting = lambda *a, **kw: None
    app.job_queue.enqueue_transcription = lambda *a: queued.append(a)
    app._weekly_quota = lambda uid: None if remaining is None else {"limit": 60, "used": 60 - remaining, "remaining": remaining}
    client = app.app.test_client()
    with client.session_transaction() as s:
        s["user_id"], s["role"] = "u1", "user"
    return client.post("/meetings/m/process").status_code, bool(queued)


# rapat gagal minggu ini (30 menit) sudah terhitung di "used": sisa 10 + 30 sendiri = 40, muat
assert process("failed", 30, 10) == (200, True)
# rapat gagal minggu lalu tidak terhitung minggu ini: 30 > sisa 10, ditolak
assert process("failed", 30, 10, this_week=False) == (402, False)
# upload (tanpa url) tidak terkena kuota mingguan
assert process("failed", 30, 0, url=None) == (200, True)
# gagal bergabung, tidak ada rekaman
assert process("failed", 0, 60, recording=None) == (409, False)
# rapat selesai tidak bisa diproses ulang lewat sini
assert process("completed", 5, 60) == (409, False)
# paket tanpa batas
assert process("failed", 500, None) == (200, True)
print("ok")
