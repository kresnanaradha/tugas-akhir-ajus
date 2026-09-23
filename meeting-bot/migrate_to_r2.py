"""One-off migration: uploads every meeting still pointing at a local
recording (pre-R2-migration rows — see CLAUDE.md) to Cloudflare R2, along
with its sibling transcript/fixed_transcript/segments/summary files (the old
recordings/<type>/<stem>.<ext> convention, replaced by pipeline/artifacts.py's
meeting-id-keyed R2 layout). Safe to re-run: a row already migrated has no
local file left at its `recording` path, so it's skipped.

Run once from meeting-bot/: python migrate_to_r2.py
"""

import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from pipeline import artifacts, meetings_store, storage  # noqa: E402

RECORDINGS_DIR = Path("recordings")


def _sibling(stem: str, subfolder: str, suffix: str) -> Path:
    return RECORDINGS_DIR / subfolder / f"{stem}{suffix}"


def main():
    migrated = 0
    skipped = 0
    for m in meetings_store.list_meetings():
        recording = m.get("recording") or ""
        local_path = Path(recording) if recording else None
        if not local_path or not local_path.exists():
            skipped += 1
            continue

        meeting_id = m["id"]
        stem = local_path.stem  # the *filename's* stem — not necessarily
        # meeting_id (join-flow bots name the file after the bot class +
        # timestamp, e.g. "ZoomBot_123", while meeting_id is a random uuid;
        # only /upload's filename happens to match its meeting_id).

        new_key = storage.upload_recording(str(local_path), meeting_id)

        transcript_file = _sibling(stem, "transcripts", ".txt")
        if transcript_file.exists():
            artifacts.save_transcript(meeting_id, transcript_file.read_text(encoding="utf-8"))
            transcript_file.unlink()

        fixed_file = _sibling(stem, "fixed_transcripts", ".txt")
        if fixed_file.exists():
            artifacts.save_fixed_transcript(meeting_id, fixed_file.read_text(encoding="utf-8"))
            fixed_file.unlink()

        segments_file = _sibling(stem, "transcripts", ".segments.json")
        if segments_file.exists():
            artifacts.save_segments(meeting_id, json.loads(segments_file.read_text(encoding="utf-8")))
            segments_file.unlink()

        summary_file = _sibling(stem, "summaries", ".summary.json")
        if summary_file.exists():
            artifacts.save_summary(meeting_id, json.loads(summary_file.read_text(encoding="utf-8")))
            summary_file.unlink()

        meetings_store.update_meeting(meeting_id, recording=new_key)
        migrated += 1
        print(f"migrated {meeting_id} ({stem}) -> {new_key}")

    print(f"\nDone. migrated={migrated} skipped(already migrated or no local file)={skipped}")


if __name__ == "__main__":
    main()
