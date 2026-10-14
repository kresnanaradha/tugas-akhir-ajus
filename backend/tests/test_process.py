"""process_recording tetap jalan kalau satu langkah gagal dan hanya mengirim email kalau ringkasan ada. Model, whisper, dan
email dipalsukan.

Jalankan: python -m tests.test_process   (dari backend/)"""
from pipeline import process

mails = []
process.get_meeting = lambda mid: {"user_id": "u", "title": "T"}
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
print("ok")
