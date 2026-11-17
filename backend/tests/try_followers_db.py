"""SQL rapat salinan terhadap Postgres sungguhan (jendela 30 menit, salinan status, jatah mingguan, hapus). Manual: arahkan
DATABASE_URL ke database SEMENTARA, bukan produksi, karena skrip ini menulis baris.

Jalankan: DATABASE_URL=postgresql://... python tests/try_followers_db.py   (dari backend/, PYTHONPATH=.)"""
import os
import uuid
from datetime import datetime, timedelta

assert os.getenv("DATABASE_URL"), "isi DATABASE_URL dengan database sementara"

from pipeline import auth_store, db, meetings_store as ms  # noqa: E402

tag = uuid.uuid4().hex[:6]
u1 = auth_store.create_user(f"a{tag}@x.id", "password1", "A")["id"]
u2 = auth_store.create_user(f"b{tag}@x.id", "password1", "B")["id"]
url = f"https://us02web.zoom.us/j/{tag}"
m1 = f"m1{tag}"


def row(mid):
    return ms.get_meeting(mid)


# rapat sumber yang sedang berjalan ditemukan lewat tautan; User kedua mendapat salinan yang statusnya mengikuti
ms.start_meeting(m1, "zoom", "Rapat Zoom", url=url, user_id=u1)
assert ms.find_meeting_by_url(url)["id"] == m1
f = ms.create_follower(row(m1), u2)
r = row(f)
assert r["source_meeting_id"] == m1 and r["user_id"] == u2 and r["status"] == "joining" and r["recording"] == ""
assert ms.find_follower(m1, u2) == f and [x["id"] for x in ms.list_followers(m1)] == [f]
assert ms.find_meeting_by_url(url)["id"] == m1  # salinan tidak pernah dikembalikan sebagai sumber

ms.update_meeting(m1, status="recording")
assert row(f)["status"] == "recording"

# rekaman berakhir: status, rekaman, dan durasi ikut ke salinan
ms.update_meeting(m1, status="processing", recording=f"{m1}/recording.webm", duration_minutes=5.0, ended_at=datetime.now())
r = row(f)
assert (r["status"], r["recording"], r["duration_minutes"]) == ("processing", f"{m1}/recording.webm", 5.0)
assert ms.find_meeting_by_url(url)["id"] == m1  # baru berakhir: masih rapat yang sama

# lewat 30 menit setelah berakhir: tautan yang sama adalah rapat baru
db.execute("UPDATE meetings SET ended_at = %s WHERE id = %s", (datetime.now() - timedelta(minutes=31), m1))
assert ms.find_meeting_by_url(url) is None

# selesai: status completed sumber tidak langsung disalin (menunggu hasilnya tersalin), salinan yang selesai tidak ditimpa
ms.update_meeting(m1, status="completed")
assert row(f)["status"] == "processing" and [x["id"] for x in ms.list_followers(m1)] == [f]
ms.update_meeting(f, status="completed")
assert ms.list_followers(m1) == []
ms.update_meeting(m1, status="processing")
assert row(f)["status"] == "completed"  # salinan yang sudah selesai tidak ditarik mundur

# rekaman dipakai bersama: hitungan untuk hapus
assert ms.recording_refs(f"{m1}/recording.webm", m1) == 1 and ms.recording_refs(f"{m1}/recording.webm", f) == 1
ms.delete_meeting(m1)
assert row(f)["source_meeting_id"] is None and ms.recording_refs(f"{m1}/recording.webm", f) == 0

# gagal ikut ke salinan, dan rapat gagal tidak ditemukan lagi untuk dibagikan
m2 = f"m2{tag}"
url2 = f"https://us02web.zoom.us/j/{tag}2"
ms.start_meeting(m2, "zoom", "Rapat Zoom", url=url2, user_id=u1)
f2 = ms.create_follower(row(m2), u2)
ms.update_meeting(m2, status="failed")
assert row(f2)["status"] == "failed" and ms.find_meeting_by_url(url2) is None

# jatah mingguan: menit rapat salinan tidak dihitung (tidak memakai AI sendiri)
m3 = f"m3{tag}"
ms.start_meeting(m3, "zoom", "Rapat Zoom", url=f"{url}3", user_id=u1)
f3 = ms.create_follower(row(m3), u2)
ms.update_meeting(m3, status="limited", duration_minutes=10.0)  # limited juga tidak dihitung, jadi ubah ke processing
ms.update_meeting(m3, status="processing", duration_minutes=10.0)
since = datetime.now() - timedelta(days=1)
# u2 hanya punya rapat f (5 menit) yang sudah dilepas dari sumbernya, salinan f3 yang masih terhubung tidak dihitung
assert ms.recorded_minutes_since(u1, since) >= 10.0 and ms.recorded_minutes_since(u2, since) == 5.0
assert row(f3)["duration_minutes"] == 10.0
print("ok")
