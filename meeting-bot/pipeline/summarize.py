import json

from openai import OpenAI

from . import artifacts, knowledge_base, usage_store

_MODEL = "gpt-4o-mini"

_FIX_SYSTEM_PROMPT = (
    "Fix obvious speech-to-text errors in this meeting transcript (misheard "
    "words, typos) without changing its meaning, removing real content, or "
    "adding anything. This is a meeting about Notulis, a Zoom/Google Meet "
    "recording bot with automatic transcription (transkripsi) via Whisper, "
    "AI summarization (ringkasan), a job queue (antrian pekerjaan), and a "
    "backend — watch for phonetically-similar mishearings of those specific "
    "terms (e.g. 'taun skripsi' should be 'transkripsi'). The only thing to "
    "remove is an exact phrase mechanically repeated 2+ times in a row at "
    "the very end (e.g. 'Terima kasih. Terima kasih. Terima kasih.') — collapse "
    "that to one occurrence. Never remove a closing sentence that isn't a "
    "literal repeat, even if it sounds like a sign-off. When in doubt, keep "
    "the text as-is. Keep the same language. Return only the corrected "
    "transcript text, nothing else — no preamble, no quotes."
)

_SUMMARY_SYSTEM_PROMPT = (
    "You summarize meeting transcripts. Respond with JSON containing exactly "
    "these keys: executive_summary (a short paragraph string), key_decisions "
    "(an array of strings), topics_discussed (an array of strings), and "
    "action_items (an array of objects, each with exactly: task — string, the "
    "concrete action to do; assignee — string or null, the person's name only "
    "if the transcript clearly assigns it to them, never guess; due — string "
    "or null, a deadline/date only if one was explicitly mentioned). Only "
    "include real action items actually committed to in the transcript — an "
    "empty array is correct if there weren't any, don't invent some just to "
    "fill the field. Write in the same language as the transcript."
)


def _log_usage(meeting_id: str | None, call_type: str, response) -> None:
    # Best-effort: the super admin dashboard's cost figure is a nice-to-have,
    # not something that should ever take down a successful transcription/
    # summarization if the usage table hiccups.
    try:
        usage_store.log_usage(meeting_id, call_type, _MODEL, response.usage)
    except Exception as e:
        print(f"[usage_store] failed to log usage for {meeting_id} ({call_type}): {e}")


def fix_transcript(transcript: str, meeting_id: str) -> str:
    client = OpenAI()
    response = client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": _FIX_SYSTEM_PROMPT},
            {"role": "user", "content": transcript},
        ],
    )
    _log_usage(meeting_id, "fix_transcript", response)
    fixed = response.choices[0].message.content

    artifacts.save_fixed_transcript(meeting_id, fixed)

    return fixed


def summarize(transcript: str, meeting_id: str) -> dict:
    client = OpenAI()
    response = client.chat.completions.create(
        model=_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": transcript},
        ],
    )
    _log_usage(meeting_id, "summarize", response)
    summary = json.loads(response.choices[0].message.content)

    artifacts.save_summary(meeting_id, summary)

    # Indexed for the RAG Knowledge Base search — best-effort: a Chroma
    # hiccup here shouldn't fail an otherwise-successful summary the same
    # way a bad summary shouldn't erase an otherwise-successful transcript
    # (see _process_recording's per-step error handling in app.py).
    try:
        knowledge_base.index_meeting(meeting_id, summary)
    except Exception as e:
        print(f"[knowledge_base] failed to index meeting {meeting_id}: {e}")

    return summary
