import json

from openai import OpenAI

from paths import sibling_path

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
    "(an array of strings), and topics_discussed (an array of strings). "
    "Write in the same language as the transcript."
)


def fix_transcript(transcript: str, recording_path: str) -> str:
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": _FIX_SYSTEM_PROMPT},
            {"role": "user", "content": transcript},
        ],
    )
    fixed = response.choices[0].message.content

    sibling_path(recording_path, "fixed_transcripts", ".txt").write_text(fixed, encoding="utf-8")

    return fixed


def summarize(transcript: str, recording_path: str) -> dict:
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": transcript},
        ],
    )
    summary = json.loads(response.choices[0].message.content)

    sibling_path(recording_path, "summaries", ".summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return summary
