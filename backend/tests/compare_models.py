"""Uji manual (bukan tes otomatis): bandingkan dua model Replicate dan hasil whisperx lokal lama pada klip uji, dengan skrip
yang dibacakan (test_script.txt) sebagai acuan. Hanya teksnya yang dibandingkan (tanpa diarization), dan tidak ada yang disimpan
ke R2 atau database. Memakai uang dan mengirim audio ke Replicate.

Jalankan: docker compose run --rm --no-deps -T -v ./tests:/app/tests worker-1 python -m tests.compare_models <meeting_id>"""
import os
import re
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

from pipeline import artifacts, storage  # noqa: E402
from pipeline.meetings_store import get_meeting  # noqa: E402

API = "https://api.replicate.com/v1"
MP3_URL = [None]  # diisi setelah konversi
MODELS = {
    "thomasmol (large-v3-turbo + pyannote community-1)": (
        "744c4f2bffae674f82e79ed46f9cc54796d4903b3e20e68353e05a93eb10a55c",
        lambda url: {"file_url": url, "language": "id"},
        0.000975,
    ),
    "victor-upmeet (large-v3 + wav2vec2 align)": (
        "655845d6190ef70573c669245f245892cd039df4b880a1e3a65852c09252f5cc",
        lambda url: {"audio_file": MP3_URL[0], "language": "id", "diarization": False, "align_output": True},
        0.0014,  # A100 80GB, perkiraan
    ),
}


def run(version, model_input):
    headers = {"Authorization": f"Bearer {os.environ['REPLICATE_API_TOKEN']}"}
    for _ in range(6):
        resp = requests.post(f"{API}/predictions", json={"version": version, "input": model_input}, headers=headers, timeout=60)
        if resp.status_code != 429:
            break
        time.sleep(10)  # saldo di bawah US$5: 6 permintaan per menit
    if not resp.ok:
        raise RuntimeError(f"Replicate menolak ({resp.status_code}): {resp.text[:300]}")
    prediction = resp.json()
    while prediction["status"] not in ("succeeded", "failed", "canceled"):
        time.sleep(3)
        prediction = requests.get(prediction["urls"]["get"], headers=headers, timeout=60).json()
    if prediction["status"] != "succeeded":
        raise RuntimeError(f"{prediction['status']}: {prediction.get('error')}")
    return prediction


def normalize(text):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower().replace("-", " "))).strip().split(" ")


def wer(reference, hypothesis):
    """Kesalahan kata (substitusi, hapus, tambah) dibagi jumlah kata acuan."""
    r, h = normalize(reference), normalize(hypothesis)
    d = list(range(len(h) + 1))
    for i, rw in enumerate(r, start=1):
        prev, d[0] = d[0], i
        for j, hw in enumerate(h, start=1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (rw != hw))
    return d[len(h)] / len(r)


script = open("test_script.txt", encoding="utf-8").read()
reference = " ".join(re.findall(r'"([^"]+)"', script))
reference = re.sub(r"\[Nama [A-Z]\],?", "", reference)  # nama orang diganti pembicara waktu membacakan

meeting = get_meeting(sys.argv[1])
url = storage.presigned_url(meeting["recording"], expires_in=3600)

# rekaman .webm dari browser tidak punya durasi di metadata dan whisperx di Replicate menolaknya ("Could not determine audio
# duration"), jadi untuk model itu dikonversi ke mp3 dulu dan disimpan sementara di R2
import subprocess  # noqa: E402
import tempfile  # noqa: E402

local = tempfile.mktemp(suffix=".webm")
mp3 = tempfile.mktemp(suffix=".mp3")
storage.download_to_file(meeting["recording"], local)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", local, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", mp3], check=True)
tmp_key = f"tmp_compare/{meeting['id']}.mp3"
storage._get_client().upload_file(mp3, storage._bucket(), tmp_key, ExtraArgs={"ContentType": "audio/mpeg"})
mp3_url = storage.presigned_url(tmp_key, expires_in=3600)

results = {"whisperx lokal (hasil lama, large-v3-turbo)": " ".join(l.split("] ", 1)[-1] for l in artifacts.load_transcript(meeting["id"]).split("\n"))}
# transkrip lama sudah ditimpa hasil Replicate, jadi pakai cadangan kalau ada
backup = "/tmp/backup_salinan_uji.json"
if os.path.exists(backup):
    import json

    old = json.load(open(backup, encoding="utf-8"))["transcript"]
    results["whisperx lokal (hasil lama, large-v3-turbo)"] = " ".join(l.split("] ", 1)[-1] for l in old.split("\n"))
else:
    results.pop("whisperx lokal (hasil lama, large-v3-turbo)")

MP3_URL[0] = mp3_url
costs = {}
for name, (version, make_input, rate) in MODELS.items():
    t0 = time.time()
    p = run(version, make_input(url))
    out = p["output"]
    results[name] = " ".join(s["text"].strip() for s in out["segments"])
    sec = (p.get("metrics") or {}).get("predict_time") or 0
    costs[name] = f"{time.time() - t0:.0f}s total, GPU {sec:.0f}s, ~US${sec * rate:.3f}"

storage._get_client().delete_object(Bucket=storage._bucket(), Key=tmp_key)  # buang file sementara
print(f"acuan: {len(normalize(reference))} kata dari skrip\n")
for name, text in results.items():
    print(f"{name}\n   WER {wer(reference, text) * 100:.1f}%  ({len(normalize(text))} kata)  {costs.get(name, '')}")
print("\n--- teks tiap model ---")
for name, text in results.items():
    print(f"\n[{name}]\n{text}")
