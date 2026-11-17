"""Rapat salinan: hasil rapat sumber tersalin ke rapat User kedua dan ia dikabari, satu yang gagal tidak menghentikan yang
lain. R2, database, dan email dipalsukan.

Jalankan: python -m tests.test_followers   (dari backend/)"""
from pipeline import followers

store = {  # id rapat -> {nama berkas: isi}, meniru R2
    "src": {"transcript": "raw", "fixed_transcript": "fixed", "segments": [{"text": "a"}], "summary": {"executive_summary": "S"}},
}
updates, mails = [], []
SRC = {"id": "src", "recording": "src/recording.webm", "duration_minutes": 12.5, "status": "completed"}

for name in ("transcript", "fixed_transcript", "segments", "summary"):
    setattr(followers.artifacts, f"load_{name}", lambda mid, name=name: store.get(mid, {}).get(name))
    setattr(followers.artifacts, f"save_{name}", lambda mid, data, name=name: store.setdefault(mid, {}).__setitem__(name, data))
followers.meetings_store.update_meeting = lambda mid, **f: updates.append((mid, f))
followers.process.notify_meeting_ready = lambda mid, summary, shared=False: mails.append((mid, shared))

# hasil tersalin, rekaman tetap menunjuk berkas sumber, pemilik salinan dikabari dengan email berkata lain
followers.finish_follower("copy1", SRC)
assert store["copy1"] == store["src"]
assert updates == [("copy1", {"status": "completed", "recording": "src/recording.webm", "duration_minutes": 12.5})]
assert mails == [("copy1", True)]

# copy_results: semua salinan yang menunggu terisi, satu yang gagal tidak menghentikan yang lain
updates.clear(); mails.clear()
followers.meetings_store.get_meeting = lambda mid: SRC
followers.meetings_store.list_followers = lambda mid: [{"id": "bad"}, {"id": "copy2"}]
real_update = followers.meetings_store.update_meeting


def flaky(mid, **f):
    if mid == "bad":
        raise RuntimeError("db")
    real_update(mid, **f)


followers.meetings_store.update_meeting = flaky
followers.copy_results("src")
assert [m for m, _ in mails] == ["copy2"] and store["copy2"] == store["src"]

# sumber sudah tidak ada: tidak melakukan apa-apa
followers.meetings_store.get_meeting = lambda mid: None
mails.clear()
followers.copy_results("src")
assert not mails
print("ok")
