import os
import subprocess
import sys
import tempfile
from pathlib import Path

from . import replicate_transcribe


def transcribe(local_recording_path: str, meeting_id: str, num_speakers: int | None = None, recording_key: str | None = None) -> str:
    """Transkripsi rekaman dan kembalikan teks transkripnya (transkrip dan segmen disimpan ke R2 oleh yang menjalankannya).
    Lewat Replicate kalau TRANSCRIBE_BACKEND=replicate dan rekamannya sudah di R2 (recording_key), kalau gagal atau tidak,
    whisperx lokal di proses anak: whisper, alignment dan pyannote memakai sekitar 4 GB dan torch tidak
    mengembalikannya setelah `del model`, proses yang selesai mengembalikannya. Model dimuat ulang tiap job, makanya
    cache model berupa volume."""
    if recording_key and replicate_transcribe.enabled():
        try:
            return replicate_transcribe.transcribe(local_recording_path, meeting_id, recording_key, num_speakers)
        except Exception as e:
            print(f"[replicate] gagal ({e}), pakai whisperx lokal", flush=True)

    fd, out_file = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pipeline.transcribe_worker", local_recording_path, meeting_id, str(num_speakers or ""), out_file],
            # stdout diwariskan supaya baris [timing] worker sampai ke log container, stderr disimpan untuk pesan error
            stderr=subprocess.PIPE,
            text=True,
        )
        if proc.returncode != 0:
            lines = proc.stderr.strip().splitlines()
            raise RuntimeError(lines[-1] if lines else f"transcription exited with code {proc.returncode}")
        return Path(out_file).read_text(encoding="utf-8")
    finally:
        os.unlink(out_file)
