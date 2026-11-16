"""process_recording tetap jalan kalau satu langkah gagal dan hanya mengirim email kalau ringkasan ada. Model, whisper, dan
email dipalsukan.

Jalankan: python -m tests.test_process   (dari backend/)"""
from pipeline import process

mails = []
process.get_meeting = lambda mid: {"user_id": "u", "title": "T"}
process.list_viewers = lambda mid: []
process.auth_store.get_user = lambda uid: {"email": "a@b.c", "email_notifications": True}
process.mailer.send_meeting_ready_email = lambda **kw: mails.append(kw)

ok_summary = {"executive_summary": "Paragraf satu.\n\nParagraf dua."}


def run(transcribe=lambda *a, **k: "raw", fix=lambda t, m: "fixed", summarize=lambda t, m: ok_summary):
    mails.clear()
    process.transcribe, process.fix_transcript, process.summarize = transcribe, fix, summarize
    return process.process_recording("x.webm", "m1", 3)


def boom(*a, **k):
    raise RuntimeError("boom")


r = run()
assert r["transcript"] == "raw" and r["fixed_transcript"] == "fixed" and r["summary"] == ok_summary
assert len(mails) == 1 and mails[0]["summary_excerpt"] == "Paragraf satu." and mails[0]["meeting_url"].endswith("/rapat/m1")

# transkripsi gagal: tidak ada yang lain jalan
r = run(transcribe=boom)
assert r == {"transcript_error": "boom"} and not mails

# perbaikan gagal: transkrip mentah yang diringkas
seen = []
r = run(fix=boom, summarize=lambda t, m: seen.append(t) or ok_summary)
assert r["fix_transcript_error"] == "boom" and seen == ["raw"] and len(mails) == 1

# ringkasan gagal: error dilaporkan, tanpa email
r = run(summarize=boom)
assert r["summary_error"] == "boom" and "summary" not in r and not mails

# pemilik menolak email
process.auth_store.get_user = lambda uid: {"email": "a@b.c", "email_notifications": False}
run()
assert not mails

# penonton (tautan yang sama) ikut dapat email berkata lain: yang menolak dilewati, NULL di database dianggap menyala
process.auth_store.get_user = lambda uid: {"email": "owner@b.c", "email_notifications": True}
process.list_viewers = lambda mid: [
    {"id": "v1", "email": "v1@b.c", "email_notifications": None},
    {"id": "v2", "email": "v2@b.c", "email_notifications": False},
]
run()
assert [(m["to_email"], m["shared"]) for m in mails] == [("owner@b.c", False), ("v1@b.c", True)]

# satu email gagal tidak menghentikan yang lain
def flaky(**kw):
    if kw["to_email"] == "owner@b.c":
        raise RuntimeError("smtp")
    mails.append(kw)
process.mailer.send_meeting_ready_email = flaky
run()
assert [m["to_email"] for m in mails] == ["v1@b.c"]

# penonton yang bergabung setelah rapat selesai: hanya dia
process.mailer.send_meeting_ready_email = lambda **kw: mails.append(kw)
process.auth_store.get_user = lambda uid: {"email": f"{uid}@b.c", "email_notifications": True}
mails.clear()
process.notify_meeting_ready("m1", ok_summary, only_user_id="late")
assert [(m["to_email"], m["shared"]) for m in mails] == [("late@b.c", True)]
print("ok")
