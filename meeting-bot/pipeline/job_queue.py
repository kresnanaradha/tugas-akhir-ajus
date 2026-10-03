"""Redis-backed hand-off from a recorder (app.py's _run_join_job) to a
transcriber (transcriber_service.py) -- the two run in separate containers
now (see CLAUDE.md's "Recorder/transcriber split"), so a plain in-process
function call can't cross that boundary any more.

Crash-safe, not just a bare list: a job is moved atomically (BLMOVE) from the
shared queue into a per-consumer "processing" list while it runs, and only
removed from there by ack() once it's done. If a transcriber dies mid-job
(OOM kill, `docker kill`, host reboot) the job is still sitting in its
processing list, and that same consumer re-queues it on its next start
(requeue_unfinished) instead of the meeting staying "processing" forever.
Each requeue bumps the job's `attempts`; past MAX_ATTEMPTS the caller marks
the meeting failed and the job goes to a dead-letter list for inspection.

The consumer id has to be stable across restarts of the same container
(docker-compose sets TRANSCRIBER_ID per service) -- a random per-process id
would orphan its own unfinished job.
"""

import json
import os

import redis

_QUEUE_KEY = "notulis:transcription_jobs"
_DEAD_KEY = "notulis:transcription_dead"
MAX_ATTEMPTS = 3
_client = None


def _processing_key(consumer_id: str) -> str:
    return f"notulis:transcription_processing:{consumer_id}"


def _get_client():
    global _client
    if _client is None:
        # socket_timeout must exceed BLMOVE's own timeout, or redis-py's
        # socket read times out first and raises instead of the command just
        # returning nil the way the protocol intends (confirmed live:
        # "TimeoutError: Timeout reading from socket" every ~5s with no
        # socket_timeout set). 30s comfortably covers every claim() timeout.
        _client = redis.from_url(os.environ["REDIS_URL"], decode_responses=True, socket_timeout=30)
    return _client


def enqueue_transcription(meeting_id: str, recording_key: str, num_speakers: int | None) -> None:
    _get_client().rpush(
        _QUEUE_KEY,
        json.dumps({"meeting_id": meeting_id, "recording_key": recording_key, "num_speakers": num_speakers, "attempts": 0}),
    )


def claim(consumer_id: str, timeout: int = 5) -> tuple[dict, str] | None:
    """Blocks up to `timeout` seconds for a job and moves it into this
    consumer's processing list. Returns (job, raw) -- hand `raw` back to
    ack() when the job is finished -- or None if nothing arrived (caller
    loops). Always pass a real timeout: 0 blocks forever, which never lets
    the worker loop do anything else."""
    raw = _get_client().blmove(_QUEUE_KEY, _processing_key(consumer_id), timeout, "LEFT", "RIGHT")
    if raw is None:
        return None
    return json.loads(raw), raw


def ack(consumer_id: str, raw: str) -> None:
    _get_client().lrem(_processing_key(consumer_id), 1, raw)


def requeue_unfinished(consumer_id: str) -> tuple[list[dict], list[dict]]:
    """Call once at startup. Takes back whatever this consumer was running
    when it last died: returns (requeued, exhausted). Requeued jobs go to
    the FRONT of the shared queue with attempts + 1; exhausted ones (already
    tried MAX_ATTEMPTS times) are dead-lettered and returned so the caller
    can mark their meetings failed."""
    client = _get_client()
    key = _processing_key(consumer_id)
    requeued, exhausted = [], []
    while True:
        raw = client.lpop(key)
        if raw is None:
            break
        job = json.loads(raw)
        job["attempts"] = job.get("attempts", 0) + 1
        if job["attempts"] >= MAX_ATTEMPTS:
            client.rpush(_DEAD_KEY, json.dumps(job))
            exhausted.append(job)
        else:
            client.lpush(_QUEUE_KEY, json.dumps(job))
            requeued.append(job)
    return requeued, exhausted
