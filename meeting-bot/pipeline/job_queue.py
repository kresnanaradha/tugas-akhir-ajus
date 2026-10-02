"""Redis-backed hand-off from a recorder (app.py's _run_join_job) to a
transcriber (transcriber_service.py) -- the two run in separate containers
now (see CLAUDE.md's "Team" -- the recorder/transcriber split), so a plain
in-process function call can't cross that boundary any more. A plain Redis
list (RPUSH/BLPOP) is enough at this scale: a handful of jobs at a time,
one queue, no need for rq's retry/scheduling/dashboard machinery.

ponytail: no dead-letter handling or retry-on-crash -- a transcriber that
dies mid-job silently drops it (the meeting stays "processing" forever).
Fine for a thesis demo's job volume; add an ack/requeue scheme (e.g. BRPOPLPUSH
into a processing list) if this ever needs to survive a transcriber crash.
"""

import json
import os

import redis

_QUEUE_KEY = "notulis:transcription_jobs"
_client = None


def _get_client():
    global _client
    if _client is None:
        # socket_timeout must exceed BLPOP's own timeout, or redis-py's
        # socket read times out first and raises instead of BLPOP just
        # returning nil the way the protocol intends (confirmed live:
        # "TimeoutError: Timeout reading from socket" every ~5s with no
        # socket_timeout set at all, which should default to blocking
        # forever but evidently didn't). 30s comfortably covers every
        # dequeue_transcription(timeout=...) call in this codebase.
        _client = redis.from_url(os.environ["REDIS_URL"], decode_responses=True, socket_timeout=30)
    return _client


def enqueue_transcription(meeting_id: str, recording_key: str, num_speakers: int | None) -> None:
    _get_client().rpush(
        _QUEUE_KEY, json.dumps({"meeting_id": meeting_id, "recording_key": recording_key, "num_speakers": num_speakers})
    )


def dequeue_transcription(timeout: int = 5) -> dict | None:
    """Blocks up to `timeout` seconds for a job; None if none arrived
    (caller loops). timeout=0 would block forever, which never lets the
    worker loop check for e.g. a shutdown signal -- always pass a real
    number instead."""
    result = _get_client().blpop(_QUEUE_KEY, timeout=timeout)
    if result is None:
        return None
    _, raw = result
    return json.loads(raw)
