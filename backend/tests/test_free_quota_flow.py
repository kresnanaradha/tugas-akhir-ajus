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
    app._jobs["j"] = {"phase": "starting"}
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
print("ok")
