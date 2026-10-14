"""Uji manual (bukan tes otomatis): kirim satu rekaman asli ke Replicate dan bandingkan dengan transkrip yang sudah
ada. Tidak menyimpan apa pun ke R2 atau database. Memakai uang dan mengirim audio ke pihak ketiga, jalankan dengan sengaja.

Jalankan: docker compose exec -T worker-1 python -m tests.try_replicate <meeting_id>"""
import json
import sys
import tempfile
import time

from dotenv import load_dotenv

load_dotenv()

from pipeline import artifacts, replicate_transcribe as rt, segments, storage  # noqa: E402
from pipeline.meetings_store import get_meeting  # noqa: E402

meeting = get_meeting(sys.argv[1])
key = meeting["recording"]
print("rapat:", meeting["title"], meeting["duration_minutes"], "menit,", meeting.get("estimated_participants"), "pembicara (perkiraan)")

saved, raw = {}, {}
segments.artifacts.save_transcript = lambda mid, text: saved.update(text=text)
segments.artifacts.save_segments = lambda mid, segs: saved.update(segs=segs)
original_run = rt._run
rt._run = lambda url, n: raw.update(prediction=original_run(url, n)) or raw["prediction"]

local = tempfile.mktemp(suffix=".webm")
storage.download_to_file(key, local)

t0 = time.time()
rt.transcribe(local, meeting["id"], key, meeting.get("estimated_participants"))
elapsed = time.time() - t0

old = (artifacts.load_transcript(meeting["id"]) or "").split("\n")
new = saved["text"].split("\n")
words = lambda lines: sum(len(l.split()) for l in lines)
speakers = lambda lines: sorted({l.split("]")[0] for l in lines if l.startswith("[")})
print(f"\nwaktu total {elapsed:.0f} detik")
print(f"lama:     {len(old)} baris, {words(old)} kata, pembicara {speakers(old)}")
print(f"replicate: {len(new)} baris, {words(new)} kata, pembicara {speakers(new)}")
print("\n--- hasil Replicate ---")
for seg in saved["segs"]:
    print(f"{seg['start']:7.1f}-{seg['end']:7.1f} [{seg['speaker']}] {seg['text']}")

json.dump({"saved": saved, "prediction": raw["prediction"]}, open("/tmp/replicate_test.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
