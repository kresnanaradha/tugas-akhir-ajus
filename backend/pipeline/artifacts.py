"""File rapat di R2, semuanya di bawah <meeting_id>/ (id yang sama dengan tabel meetings)."""

import json

from . import storage


def save_transcript(meeting_id: str, text: str) -> None:
    storage.put_text(f"{meeting_id}/transcript.txt", text)


def load_transcript(meeting_id: str) -> str | None:
    return storage.get_text(f"{meeting_id}/transcript.txt")


def save_fixed_transcript(meeting_id: str, text: str) -> None:
    storage.put_text(f"{meeting_id}/fixed_transcript.txt", text)


def load_fixed_transcript(meeting_id: str) -> str | None:
    return storage.get_text(f"{meeting_id}/fixed_transcript.txt")


def save_segments(meeting_id: str, segments: list) -> None:
    storage.put_text(f"{meeting_id}/segments.json", json.dumps(segments, ensure_ascii=False), content_type="application/json")


def load_segments(meeting_id: str) -> list | None:
    text = storage.get_text(f"{meeting_id}/segments.json")
    return json.loads(text) if text is not None else None


def save_summary(meeting_id: str, summary: dict) -> None:
    storage.put_text(
        f"{meeting_id}/summary.json", json.dumps(summary, ensure_ascii=False, indent=2), content_type="application/json"
    )


def load_summary(meeting_id: str) -> dict | None:
    text = storage.get_text(f"{meeting_id}/summary.json")
    return json.loads(text) if text is not None else None
