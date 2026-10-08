import json
import os
import difflib
import re

from openai import OpenAI

from . import artifacts, meetings_store, usage_store

_MODEL = "gpt-4o-mini"

# Words Whisper keeps mishearing in this project's meetings (measured: "RAM"
# heard as "rapat", "skrip" as "skripsi"). EXTRA_VOCAB in .env adds names or
# domain terms without a code change, e.g. EXTRA_VOCAB=Kresna, Diva, Ahmad.
_KNOWN_TERMS = (
    "Notulis, Docker, kontainer, RAM, CPU, GB, Knowledge Base, Whisper, transkripsi, "
    "diarization, ringkasan, skrip, server, database, Zoom, Google Meet, dosen, demo"
)


def _known_terms() -> str:
    extra = os.getenv("EXTRA_VOCAB", "").strip()
    return _KNOWN_TERMS + (", " + extra if extra else "")


_FIX_SYSTEM_PROMPT = (
    "You correct obvious speech-to-text errors in a meeting transcript (mostly "
    "Indonesian with some English terms): misheard or misspelled words, wrong "
    "spellings of names, garbled technical terms. Never change the meaning or "
    "the style, and never remove or add content. Every input line starts with "
    "its number, then a tab. Return ONLY the lines that need a correction, as "
    'JSON: {"fixes": [{"n": <line number>, "text": <the whole corrected line, '
    "keeping its [SPEAKER_xx] label>}]}. A line that is fine must not appear. "
    "When in doubt, leave the line out. Keep the same language."
)

# Appended at call time (not baked into the string above) so EXTRA_VOCAB is
# read fresh from the environment.
_FIX_NAMES_PROMPT = (
    " Names of people are often misheard too. If a word is clearly a garbled "
    "person's name given the context (for example someone being assigned a "
    "task) and it sounds like a name in the known list below, use that "
    "spelling. If a name appears with slightly different spellings, make them "
    "consistent. If it does not sound like anything in the list, keep it as-is "
    "rather than guessing. Known terms and names: {terms}."
)

# Two focused calls instead of one big JSON prompt: with every rule packed into
# one prompt, gpt-4o-mini followed them inconsistently (a rule that worked in
# one run regressed after adding another). Narrative and structured data each
# get a short prompt of their own.
_NARRATIVE_PROMPT = (
    "You write the executive summary of a meeting transcript, in the same "
    "language as the transcript. Give a complete, dense account of everything "
    "discussed in the WHOLE meeting as several paragraphs separated by a "
    "blank line, one paragraph per topic in the order it came up. Cover every "
    "point raised, not just the conclusions: what was reported or proposed "
    "and by whom, the reasons, problems, numbers, names and dates, the "
    "outcome, each decision. Never drop a reported result or figure (before "
    "and after values, percentages, sizes, durations, counts, dates) because "
    "it seems minor. The user message gives the transcript's word count and "
    "a target length: write about that many words, complete rather than "
    "short, but never pad and never add anything that is not in the "
    "transcript. Do not mention greetings, thanks or the meeting ending; stop "
    "at the last substantive point. Speakers appear as labels like "
    "SPEAKER_02: write them only as 'Pembicara 2' (same number) and never "
    "guess which label is which person. A label that is a real name instead "
    "(e.g. [Kresna]) was confirmed by the user: use that exact name for that "
    "speaker, everywhere they are mentioned. When the transcript itself names "
    "someone being assigned something (e.g. 'Diva, tolong kamu...'), use "
    "that name for that assignment. Plain text only, no headings or bullets."
)

_DETAILS_PROMPT = (
    "You extract structured data from a meeting transcript, in the same "
    "language as the transcript. Respond with JSON containing exactly these "
    "keys: key_decisions (an array of strings: every decision actually made, "
    "including small ones, each with what was decided and, if stated, why; "
    "task assignments do not belong here), topics_discussed (an array of "
    "strings: every distinct subject covered, 4 to 8 short items), and "
    "action_items (an array of objects, each with exactly: task, a string "
    "with the concrete action; assignee, a real person's name or null: use "
    "the name when the transcript itself says who does it (e.g. 'Diva, "
    "tolong kamu yang kerjakan'), or when a speaker whose label is a real "
    "name (e.g. [Kresna]) commits to it themselves; otherwise null, never "
    "'Pembicara N' or a SPEAKER label; due, a string or null, only if a deadline or date was "
    "explicitly said). List every commitment or request "
    "made in the transcript, including ones nobody was assigned (assignee "
    "null), and nothing that was not committed to."
)

_SPEAKER_LABEL = re.compile(r"(?i)^(?:pembicara|speaker)[ _]?0*(\d+)$")
_SPEAKER_INLINE = re.compile(r"(?i)\b(?:speaker[ _]|pembicara )0*(\d+)\b")
_CLOSING = re.compile(r"(?i)\b(ditutup|diakhiri|menutup|mengakhiri|terima kasih)\b")

def _log_usage(meeting_id: str | None, call_type: str, response) -> None:
    # Best-effort: the super admin dashboard's cost figure is a nice-to-have,
    # not something that should ever take down a successful transcription/
    # summarization if the usage table hiccups.
    try:
        usage_store.log_usage(meeting_id, call_type, _MODEL, response.usage)
    except Exception as e:
        print(f"[usage_store] failed to log usage for {meeting_id} ({call_type}): {e}")


# gpt-4o-mini can return at most ~16k tokens, and fix_transcript has to hand
# back the WHOLE text it was given. A 1-2 hour meeting is 12k-30k tokens of
# Indonesian, so one call silently cut the second half off (and summarize()
# then summarized the truncated version). Work in blocks of whole lines that
# stay far below that limit instead.
_FIX_CHUNK_WORDS = 700


def _split_for_fix(transcript: str, max_words: int = _FIX_CHUNK_WORDS) -> list[str]:
    chunks, current, count = [], [], 0
    for line in transcript.split("\n"):
        words = len(line.split())
        if current and count + words > max_words:
            chunks.append("\n".join(current))
            current, count = [], 0
        current.append(line)
        count += words
    chunks.append("\n".join(current))
    return chunks


def _same_line(raw: str, fixed: str) -> bool:
    """Is `fixed` really a correction of `raw`? Guards against a wrong line number:
    such a line has another speaker or unrelated words."""
    if raw.split("]")[0] != fixed.split("]")[0]:
        return False
    # A real correction changes a word or two: about the same length and nearly the
    # same text. Anything else is text from a neighbouring line or a rewrite.
    if not 0.75 <= len(fixed) / max(len(raw), 1) <= 1.3:
        return False
    return difflib.SequenceMatcher(None, raw.lower(), fixed.lower()).ratio() >= 0.75


def _fix_chunk(client: OpenAI, text: str, meeting_id: str, part: int, parts: int) -> str:
    """Returns `text` with the model's corrections applied, always with exactly
    the same lines. The editor pairs raw line N with fixed line N, and asking a
    model to rewrite the whole text made it merge or drop lines (61 of 632 in a
    60-minute meeting), shifting every suggestion after that. So it only returns
    the lines to change, by number, and each one is checked against the line it
    claims to correct."""
    lines = text.split(chr(10))
    numbered = chr(10).join(f"{i}{chr(9)}{ln}" for i, ln in enumerate(lines, start=1))
    system = _FIX_SYSTEM_PROMPT + _FIX_NAMES_PROMPT.format(terms=_known_terms())
    response = client.chat.completions.create(
        model=_MODEL,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": numbered}],
    )
    _log_usage(meeting_id, "fix_transcript", response)
    choice = response.choices[0]
    if choice.finish_reason == "length":
        print(f"[fix_transcript] part {part}/{parts} of {meeting_id} was cut off, keeping the raw text")
        return text
    try:
        fixes = json.loads(choice.message.content or "{}").get("fixes", [])
    except (ValueError, AttributeError):
        print(f"[fix_transcript] part {part}/{parts} of {meeting_id} was not valid JSON, keeping the raw text")
        return text
    out, rejected = list(lines), 0
    for f in fixes:
        try:
            n, new = int(f["n"]), str(f["text"]).strip()
        except (KeyError, TypeError, ValueError):
            rejected += 1
            continue
        if 1 <= n <= len(lines) and _same_line(lines[n - 1], new):
            out[n - 1] = new
        else:
            rejected += 1
    if rejected:
        print(f"[fix_transcript] part {part}/{parts} of {meeting_id}: {rejected} corrections did not match their line, ignored")
    return chr(10).join(out)


# A recording with (almost) no speech must not reach the model: asked to fix or
# summarize an empty transcript it apologizes or invents a plausible meeting.
_MIN_WORDS = 15
NO_SPEECH_SUMMARY = {
    "executive_summary": "Tidak ada percakapan yang terdeteksi dalam rekaman ini.",
    "key_decisions": [],
    "topics_discussed": [],
    "action_items": [],
}


def _has_speech(transcript: str) -> bool:
    return len(transcript.split()) >= _MIN_WORDS


def fix_transcript(transcript: str, meeting_id: str) -> str:
    if not _has_speech(transcript):
        artifacts.save_fixed_transcript(meeting_id, transcript)
        return transcript
    client = OpenAI()
    chunks = _split_for_fix(transcript)
    fixed = "\n".join(_fix_chunk(client, c, meeting_id, i, len(chunks)) for i, c in enumerate(chunks, start=1))

    artifacts.save_fixed_transcript(meeting_id, fixed)

    return fixed


def _speaker_note(transcript: str) -> str:
    """Lists the speakers whose label is a real name (the user renamed them in
    the editor). Without this the model sometimes still wrote 'Pembicara 2'
    for a speaker labeled [Kresna]; naming them explicitly makes it stable."""
    labels = list(dict.fromkeys(re.findall(r"(?m)^\[(.+?)\]", transcript)))
    named = [x for x in labels if not _SPEAKER_LABEL.match(x)]
    if not named:
        return ""
    note = f"Speakers with confirmed real names: {', '.join(named)}. Refer to each of them only by that name, never as 'Pembicara' or 'SPEAKER'."
    if len(named) == len(labels):
        note += " Every speaker in this transcript has a real name, so the word 'Pembicara' must not appear."
    return note + "\n\n"


def _summary_user_message(transcript: str) -> str:
    """Tells the model how long the transcript is and how long the summary
    should be, so the summary grows with the meeting instead of staying a
    fixed short paragraph: about 60% of the transcript's words, at least 250
    and at most 1200."""
    words = len(transcript.split())
    target = max(250, min(1200, int(words * 0.6)))
    return f"{_speaker_note(transcript)}Transcript length: {words} words. Write executive_summary of about {target} words.\n\n{transcript}"


def _build_summary(transcript: str, meeting_id: str | None) -> dict:
    """Builds the summary dict without saving or indexing anything, so it can
    be tested against stored transcripts. meeting_id None skips usage logging
    (test calls)."""
    if not _has_speech(transcript):
        return {**NO_SPEECH_SUMMARY, "key_decisions": [], "topics_discussed": [], "action_items": []}
    client = OpenAI()
    narrative = client.chat.completions.create(
        model=_MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": _NARRATIVE_PROMPT},
            {"role": "user", "content": _summary_user_message(transcript)},
        ],
    )
    details = client.chat.completions.create(
        model=_MODEL,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _DETAILS_PROMPT},
            {"role": "user", "content": _speaker_note(transcript) + transcript},
        ],
    )
    if meeting_id:
        _log_usage(meeting_id, "summarize", narrative)
        _log_usage(meeting_id, "summarize_details", details)

    data = json.loads(details.choices[0].message.content)

    def clean(text: str) -> str:
        # "SPEAKER_02" / "pembicara 02" -> "Pembicara 2", one consistent form.
        return _SPEAKER_INLINE.sub(lambda m: f"Pembicara {int(m.group(1))}", text)

    def assignee(value):
        # A speaker label is not a person, and diarization is unreliable
        # enough that guessing a name for it would misattribute (seen: a reply
        # labeled as the wrong speaker), so a label becomes empty.
        return None if _SPEAKER_LABEL.match((value or "").strip()) else (value or None)

    paragraphs = clean(narrative.choices[0].message.content.strip()).split("\n\n")
    # ponytail: the model keeps adding a closing sentence ("rapat diakhiri dengan
    # terima kasih...") despite being told not to, so drop it here. Add a real
    # check if a legitimate last sentence ever contains one of these words.
    sentences = re.split(r"(?<=[.!?])\s+", paragraphs[-1])
    if _CLOSING.search(sentences[-1]):
        sentences = sentences[:-1]
    paragraphs[-1] = " ".join(sentences)
    return {
        "executive_summary": "\n\n".join(p for p in paragraphs if p.strip()),
        "key_decisions": [clean(x) for x in data.get("key_decisions", [])],
        "topics_discussed": [clean(x) for x in data.get("topics_discussed", [])],
        "action_items": [
            {"task": clean(a.get("task", "")), "assignee": assignee(a.get("assignee")), "due": a.get("due")}
            for a in data.get("action_items", [])
        ],
    }


def summarize(transcript: str, meeting_id: str) -> dict:
    summary = _build_summary(transcript, meeting_id)
    artifacts.save_summary(meeting_id, summary)

    # KB is opt-in: only refresh the index if the user already added this
    # meeting (best-effort, a Chroma hiccup shouldn't fail the summary).
    # Imported lazily, not at module level -- chromadb/sentence-transformers
    # are a real dependency weight (see knowledge_base.py) that a caller
    # which never touches KB-enabled meetings shouldn't have to install at
    # all (e.g. transcriber_service.py's trimmed image, see CLAUDE.md).
    try:
        meeting = meetings_store.get_meeting(meeting_id)
        if meeting and meeting.get("in_kb"):
            from . import knowledge_base

            knowledge_base.index_meeting(meeting_id, summary)
    except Exception as e:
        print(f"[knowledge_base] failed to re-index meeting {meeting_id}: {e}")

    return summary
