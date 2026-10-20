from . import replicate_transcribe


def transcribe(local_recording_path: str, meeting_id: str, num_speakers: int | None = None, recording_key: str | None = None) -> str:
    """Transkripsi rekaman lewat Replicate dan kembalikan teks transkripnya (transkrip dan segmen disimpan ke R2 oleh
    yang menjalankannya). Rekamannya harus sudah di R2 (recording_key), Replicate membacanya dari url bertanda tangan.
    Tidak ada transkripsi lokal: gagal berarti rapatnya gagal (Replicate mati, saldo habis, atau token kosong)."""
    if not recording_key:
        raise RuntimeError("Transkripsi butuh rekaman di R2 (recording_key kosong)")
    return replicate_transcribe.transcribe(local_recording_path, meeting_id, recording_key, num_speakers)
