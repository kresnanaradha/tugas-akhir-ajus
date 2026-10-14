"""Transkripsi lewat Replicate (thomasmol/whisper-diarization: Whisper large-v3-turbo + pyannote community-1 di GPU).
Replicate mengunduh rekaman dari url R2 bertanda tangan, jadi tidak ada file yang kita unggah. Hasilnya melewati
langkah akhir yang sama dengan whisperx lokal (segments.finish)."""

import os
import time

import requests

from . import segments, storage

_API = "https://api.replicate.com/v1"
_POLL_S = 5
_RETRY_S = 5  # jeda antar percobaan saat kena batas permintaan (429)
_MAX_WAIT_S = 3 * 3600
_USD_PER_SECOND = 0.000975  # GPU L40S, untuk perkiraan biaya di log


def enabled() -> bool:
    """TRANSCRIBE_BACKEND=replicate dan tokennya terisi. Tanpa token tetap pakai whisperx lokal, dengan peringatan."""
    if os.getenv("TRANSCRIBE_BACKEND", "local").strip().lower() != "replicate":
        return False
    if not os.getenv("REPLICATE_API_TOKEN"):
        print("[replicate] TRANSCRIBE_BACKEND=replicate tapi REPLICATE_API_TOKEN kosong, pakai whisperx lokal", flush=True)
        return False
    return True


def _version() -> str:
    # "pemilik/model:versi" atau hanya "versi", API membutuhkan hash versinya saja
    return os.environ["REPLICATE_MODEL"].rsplit(":", 1)[-1]


def to_segments(output_segments: list[dict]) -> list[dict]:
    """Segmen Replicate (speaker, text, start, end, words[word, start, end, speaker]) ke bentuk whisperx yang dipakai
    segments.finish. Pembicara yang kosong jatuh ke milik segmennya, lalu SPEAKER_00."""
    out = []
    for seg in output_segments:
        speaker = seg.get("speaker") or "SPEAKER_00"
        words = [
            {"word": w.get("word"), "start": w.get("start"), "end": w.get("end"), "speaker": w.get("speaker") or speaker}
            for w in seg.get("words") or []
        ]
        out.append({"speaker": speaker, "start": seg.get("start"), "end": seg.get("end"), "text": seg.get("text") or "", "words": words})
    return out


def _run(file_url: str, num_speakers: int | None) -> dict:
    """Buat prediksi dan tunggu sampai selesai. Mengembalikan prediksi yang sukses, melempar RuntimeError kalau gagal."""
    headers = {"Authorization": f"Bearer {os.environ['REPLICATE_API_TOKEN']}"}
    model_input = {"file_url": file_url}
    language = os.getenv("REPLICATE_LANGUAGE", "id").strip()
    if language:
        model_input["language"] = language  # kosong = deteksi otomatis
    if num_speakers:
        model_input["num_speakers"] = num_speakers
    vocab = os.getenv("EXTRA_VOCAB", "").strip()
    if vocab:
        model_input["prompt"] = vocab

    for _ in range(6):
        resp = requests.post(f"{_API}/predictions", json={"version": _version(), "input": model_input}, headers=headers, timeout=60)
        if resp.status_code != 429:
            break
        time.sleep(_RETRY_S)  # saldo di bawah US$5 dibatasi 6 permintaan per menit, tunggu sebentar lalu coba lagi
    if not resp.ok:
        raise RuntimeError(f"Replicate menolak permintaan ({resp.status_code}): {resp.text[:300]}")
    prediction = resp.json()
    started = time.time()
    while prediction["status"] not in ("succeeded", "failed", "canceled"):
        if time.time() - started > _MAX_WAIT_S:
            raise RuntimeError("Replicate terlalu lama, dibatalkan")
        time.sleep(_POLL_S)
        poll = requests.get(prediction["urls"]["get"], headers=headers, timeout=60)
        poll.raise_for_status()
        prediction = poll.json()
    if prediction["status"] != "succeeded":
        raise RuntimeError(f"Replicate {prediction['status']}: {prediction.get('error')}")
    return prediction


def transcribe(local_recording_path: str, meeting_id: str, recording_key: str, num_speakers: int | None = None) -> str:
    """Transkripsi rekaman yang sudah ada di R2 (recording_key). File lokalnya hanya dipakai untuk memetakan waktu."""
    t0 = time.time()
    url = storage.presigned_url(recording_key, expires_in=6 * 3600)
    prediction = _run(url, num_speakers)
    seconds = (prediction.get("metrics") or {}).get("predict_time") or 0
    print(
        f"[replicate] selesai dalam {time.time() - t0:.0f}s, GPU {seconds:.0f}s (~US${seconds * _USD_PER_SECOND:.3f}), "
        f"{prediction['output'].get('num_speakers')} pembicara, bahasa {prediction['output'].get('language')}",
        flush=True,
    )
    return segments.finish(meeting_id, to_segments(prediction["output"]["segments"]), local_recording_path)
