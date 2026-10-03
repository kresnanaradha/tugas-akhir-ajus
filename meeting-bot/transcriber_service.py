"""Standalone worker for the transcriber containers (Dockerfile.transcriber,
docker-compose.yml's transcriber-1/transcriber-2) -- pops jobs a recorder
(app.py's _run_join_job) pushed to Redis once it finished recording and
uploading, runs transcribe -> fix -> summarize -> email against them, then
writes the result back to Postgres/R2. Split out from app.py specifically
so recording (Playwright+Chrome, one lightweight container per concurrent
bot) and transcription (whisperx+torch, heavy but only 1-2 instances
needed) don't compete for the same container's memory limit -- this is
exactly what OOM-killed a live test (worker-test-2, mem_limit=3g, Chrome
and whisper sharing one container) during the optimization week, see
CLAUDE.md.

No Flask app here -- just a loop. Run directly:
    python transcriber_service.py
"""

import os
import socket
import tempfile
import time

from dotenv import load_dotenv

load_dotenv()

from pipeline import auth_store, job_queue, mailer, storage  # noqa: E402 -- see load_dotenv() note above
from pipeline.meetings_store import get_meeting, update_meeting  # noqa: E402
from pipeline.summarize import fix_transcript, summarize  # noqa: E402
from pipeline.transcribe import transcribe  # noqa: E402

LOCAL_FRONTEND_URL = os.getenv("LOCAL_FRONTEND_URL", "http://localhost:8081")
# Must stay the same across restarts of this container (docker-compose sets it
# per service) -- it names the Redis list holding this worker's unfinished
# job, see pipeline/job_queue.py. The hostname fallback only suits a
# single bare-metal run.
CONSUMER_ID = os.getenv("TRANSCRIBER_ID", socket.gethostname())


def _notify_meeting_ready(meeting_id: str, summary: dict) -> None:
    """Same best-effort behavior as app.py's version (which this replaces
    for the join flow -- /upload still uses app.py's own copy since that
    endpoint isn't queued): a mail hiccup must never fail a pipeline that
    already produced a real result."""
    try:
        record = get_meeting(meeting_id)
        user = auth_store.get_user(record["user_id"]) if record and record.get("user_id") else None
        if not user or not user["email_notifications"]:
            return
        excerpt = (summary.get("executive_summary") or "").split("\n\n")[0]
        mailer.send_meeting_ready_email(
            to_email=user["email"],
            title=record["title"],
            summary_excerpt=excerpt,
            meeting_url=f"{LOCAL_FRONTEND_URL}/rapat/{meeting_id}",
        )
    except Exception as e:
        print(f"[transcriber] failed to notify for meeting {meeting_id}: {e}")


def _process_job(job: dict) -> None:
    meeting_id = job["meeting_id"]
    recording_key = job["recording_key"]
    num_speakers = job.get("num_speakers")
    print(f"[transcriber] picked up {meeting_id}")

    fd, local_path = tempfile.mkstemp(suffix=os.path.splitext(recording_key)[1] or ".webm")
    os.close(fd)
    try:
        storage.download_to_file(recording_key, local_path)

        try:
            transcript = transcribe(local_path, meeting_id, num_speakers=num_speakers)
        except Exception as e:
            update_meeting(meeting_id, status="failed")
            print(f"[transcriber] {meeting_id} transcribe failed: {e}")
            return

        # Same fallback as app.py's _process_recording(): summarize the
        # LLM-corrected transcript when that step succeeds, the raw one if
        # it doesn't, but never let a fix_transcript hiccup alone fail the
        # whole job when transcription itself already succeeded.
        to_summarize = transcript
        try:
            to_summarize = fix_transcript(transcript, meeting_id)
        except Exception as e:
            print(f"[transcriber] {meeting_id} fix_transcript failed: {e}")

        try:
            summary = summarize(to_summarize, meeting_id)
            _notify_meeting_ready(meeting_id, summary)
        except Exception as e:
            print(f"[transcriber] {meeting_id} summarize failed: {e}")

        update_meeting(meeting_id, status="completed")
        print(f"[transcriber] {meeting_id} done")
    finally:
        os.unlink(local_path)


def main():
    # Whatever this worker was running when it last died (OOM kill, host
    # reboot, docker kill) is still in its processing list -- retry it, or
    # give up and mark the meeting failed once it has crashed MAX_ATTEMPTS
    # times (otherwise a job that always kills the worker would loop forever).
    requeued, exhausted = job_queue.requeue_unfinished(CONSUMER_ID)
    for job in requeued:
        print(f"[transcriber] re-queued unfinished job {job['meeting_id']} (attempt {job['attempts'] + 1})")
    for job in exhausted:
        update_meeting(job["meeting_id"], status="failed")
        print(f"[transcriber] giving up on {job['meeting_id']} after {job['attempts']} crashed attempts")

    print(f"[transcriber] {CONSUMER_ID} waiting for jobs...")
    while True:
        try:
            claimed = job_queue.claim(CONSUMER_ID, timeout=5)
        except Exception as e:
            # A transient Redis hiccup must never kill a long-running worker.
            print(f"[transcriber] queue read failed, retrying: {e}")
            time.sleep(2)
            continue
        if claimed is None:
            continue
        job, raw = claimed
        try:
            _process_job(job)
        except Exception as e:
            # Not a crash, so a retry would most likely fail the same way
            # (e.g. the recording is missing from R2): fail the meeting and
            # move on instead of leaving it "processing" forever.
            print(f"[transcriber] unhandled error on {job.get('meeting_id')}: {e}")
            try:
                update_meeting(job["meeting_id"], status="failed")
            except Exception as inner:
                print(f"[transcriber] could not mark {job.get('meeting_id')} failed: {inner}")
        finally:
            try:
                job_queue.ack(CONSUMER_ID, raw)
            except Exception as e:
                print(f"[transcriber] ack failed for {job.get('meeting_id')}: {e}")


if __name__ == "__main__":
    main()
