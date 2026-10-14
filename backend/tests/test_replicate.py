"""Transkripsi lewat Replicate: pemetaan hasilnya, polling, dan kembali ke whisperx lokal kalau gagal. Replicate, R2 dan
whisperx dipalsukan.

Jalankan: python -m tests.test_replicate   (dari backend/)"""
import os

from pipeline import replicate_transcribe as rt
from pipeline import segments, transcribe as tr


class Resp:
    def __init__(self, data, ok=True, status=200):
        self.data, self.ok, self.status_code, self.text = data, ok, status, str(data)

    def json(self):
        return self.data

    def raise_for_status(self):
        assert self.ok


def words(speaker, *items):
    return [{"word": w, "start": s, "end": e, "speaker": speaker} for w, s, e in items]


OUTPUT = {
    "language": "id",
    "num_speakers": 2,
    "segments": [
        {"speaker": "SPEAKER_00", "start": 0.0, "end": 4.0, "text": "Halo semua. Selamat pagi.",
         "words": words("SPEAKER_00", (" Halo", 0.0, 0.5), (" semua.", 0.5, 1.0), (" Selamat", 1.2, 1.8), (" pagi.", 1.8, 4.0))},
        {"speaker": "SPEAKER_01", "start": 4.5, "end": 6.0, "text": "Pagi juga.",
         "words": words("SPEAKER_01", (" Pagi", 4.5, 5.0), (" juga.", 5.0, 6.0))},
    ],
}

# pemetaan: pembicara kata yang kosong jatuh ke milik segmennya
mapped = rt.to_segments([{"speaker": "SPEAKER_01", "start": 0, "end": 1, "text": "a", "words": [{"word": "a", "start": 0, "end": 1}]}])
assert mapped[0]["words"][0]["speaker"] == "SPEAKER_01"
assert rt.to_segments([{"text": "x"}])[0]["speaker"] == "SPEAKER_00"

# enabled(): butuh backend replicate DAN token
for backend, token, expected in [("local", "t", False), ("replicate", "", False), ("replicate", "t", True)]:
    os.environ["TRANSCRIBE_BACKEND"], os.environ["REPLICATE_API_TOKEN"] = backend, token
    assert rt.enabled() is expected, (backend, token)

# versi diambil dari "pemilik/model:hash"
os.environ["REPLICATE_MODEL"] = "a/b:abc123"
assert rt._version() == "abc123"

# _run: mengirim url, menunggu sampai selesai, dan mengirim petunjuk bahasa / jumlah pembicara
rt._POLL_S = 0
rt._RETRY_S = 0
sent = {}
states = [Resp({"status": "processing", "urls": {"get": "g"}}), Resp({"status": "succeeded", "urls": {"get": "g"}, "output": OUTPUT})]
rt.requests.post = lambda url, json, headers, timeout: sent.update(json=json, headers=headers) or Resp({"status": "starting", "urls": {"get": "g"}})
rt.requests.get = lambda url, headers, timeout: states.pop(0)
os.environ["REPLICATE_LANGUAGE"], os.environ["EXTRA_VOCAB"] = "id", "Kresna"
prediction = rt._run("https://r2/file", 3)
assert prediction["output"] is OUTPUT
assert sent["json"] == {"version": "abc123", "input": {"file_url": "https://r2/file", "language": "id", "num_speakers": 3, "prompt": "Kresna"}}
assert sent["headers"]["Authorization"] == "Bearer t"

# gagal: pesan Replicate ikut, begitu juga penolakan permintaan
rt.requests.get = lambda url, headers, timeout: Resp({"status": "failed", "error": "boom", "urls": {"get": "g"}})
try:
    rt._run("u", None)
    raise AssertionError("harus gagal")
except RuntimeError as e:
    assert "boom" in str(e)
rt.requests.post = lambda url, json, headers, timeout: Resp("Unauthenticated", ok=False, status=401)
try:
    rt._run("u", None)
    raise AssertionError("harus gagal")
except RuntimeError as e:
    assert "401" in str(e)

# segments.finish: potong per pembicara, simpan teks dan segmen
saved = {}
segments.artifacts.save_transcript = lambda mid, text: saved.update(text=text)
segments.artifacts.save_segments = lambda mid, segs: saved.update(segs=segs)
segments._to_container_time = lambda segs, path: segs
text = segments.finish("m1", rt.to_segments(OUTPUT["segments"]), "x.webm")
assert text == "[SPEAKER_00] Halo semua. Selamat pagi.\n[SPEAKER_01] Pagi juga.", text
assert [s["speaker"] for s in saved["segs"]] == ["SPEAKER_00", "SPEAKER_01"] and saved["text"] == text

# transcribe(): Replicate berhasil, atau gagal lalu whisperx lokal
rt.storage.presigned_url = lambda key, expires_in: "https://r2/" + key
rt.requests.post = lambda url, json, headers, timeout: Resp({"status": "succeeded", "urls": {"get": "g"}, "output": OUTPUT, "metrics": {"predict_time": 10}})
os.environ["TRANSCRIBE_BACKEND"] = "replicate"
assert tr.transcribe("x.webm", "m1", 2, "m1/recording.webm").startswith("[SPEAKER_00]")

calls = []


def fake_local(cmd, **kw):
    calls.append(cmd)
    open(cmd[-1], "w", encoding="utf-8").write("lokal")
    return type("P", (), {"returncode": 0, "stderr": ""})()


tr.subprocess.run = fake_local
rt.requests.post = lambda url, json, headers, timeout: Resp("kena limit", ok=False, status=429)
assert tr.transcribe("x.webm", "m1", 2, "m1/recording.webm") == "lokal" and len(calls) == 1  # gagal -> lokal
assert tr.transcribe("x.webm", "m1", 2) == "lokal" and len(calls) == 2  # tanpa recording_key -> lokal
os.environ["TRANSCRIBE_BACKEND"] = "local"
assert tr.transcribe("x.webm", "m1", 2, "m1/recording.webm") == "lokal" and len(calls) == 3
print("ok")
