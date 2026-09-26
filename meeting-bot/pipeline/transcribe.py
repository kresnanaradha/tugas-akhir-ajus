import os
import subprocess
import sys
import tempfile
from pathlib import Path


def transcribe(local_recording_path: str, meeting_id: str, num_speakers: int | None = None) -> str:
    """Runs pipeline/transcribe_worker.py in a child process instead of
    in-process. whisper + alignment + pyannote hold about 4 GB of RAM, and
    Python/torch don't reliably give that back to the OS after `del model`
    (measured: a finished job left the container at 4 GB while idle). A child
    process that exits returns all of it, so the API process stays small
    between jobs. The cost is reloading the models every job, which is why the
    model cache is a persistent volume (see docker-compose.yml).

    Same contract as before: returns the transcript text, and the worker
    saves transcript/segments to R2 itself."""
    fd, out_file = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pipeline.transcribe_worker", local_recording_path, meeting_id, str(num_speakers or ""), out_file],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            lines = proc.stderr.strip().splitlines()
            raise RuntimeError(lines[-1] if lines else f"transcription exited with code {proc.returncode}")
        return Path(out_file).read_text(encoding="utf-8")
    finally:
        os.unlink(out_file)
