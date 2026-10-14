import difflib
import json
import os
import re

from openai import OpenAI

from . import artifacts, meetings_store, usage_store

_MODEL = "gpt-4o-mini"

# kata yang terus salah didengar whisper. EXTRA_VOCAB di .env menambah nama tanpa ubah kode,
# mis. EXTRA_VOCAB=Kresna, Diva
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

# ditambahkan saat dipanggil supaya EXTRA_VOCAB dibaca segar
_FIX_NAMES_PROMPT = (
    " Names of people are often misheard too. If a word is clearly a garbled "
    "person's name given the context (for example someone being assigned a "
    "task) and it sounds like a name in the known list below, use that "
    "spelling. If a name appears with slightly different spellings, make them "
    "consistent. If it does not sound like anything in the list, keep it as-is "
    "rather than guessing. Known terms and names: {terms}."
)

# narasi dan data terstruktur punya prompt pendek sendiri: satu prompt besar membuat gpt-4o-mini
# mengikuti aturannya tidak konsisten
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

# panggilan ketiga, ringkasan singkat untuk sekilas lihat (narasi berupa satu paragraf per topik)
_SHORT_PROMPT = (
    "You write a short summary of a meeting transcript, in the same language as "
    "the transcript: 2 to 4 sentences, at most about 70 words, saying what the "
    "meeting was about and its main outcome or decisions. No greetings, no "
    "mention of the meeting ending, nothing that is not in the transcript. If a "
    "speaker has to be mentioned, write 'Pembicara N' for a label like SPEAKER_0N, "
    "or the exact name for a label that is a real name; prefer not to mention "
    "speakers at all. Plain text, one paragraph."
)

_SPEAKER_LABEL = re.compile(r"(?i)^(?:pembicara|speaker)[ _]?0*(\d+)$")
_SPEAKER_INLINE = re.compile(r"(?i)\b(?:speaker[ _]|pembicara )0*(\d+)\b")
_CLOSING = re.compile(r"(?i)\b(ditutup|diakhiri|menutup|mengakhiri|terima kasih)\b")


def _log_usage(meeting_id: str | None, call_type: str, response) -> None:
    # pencatatan pemakaian itu pelengkap, jangan sampai menggagalkan ringkasan
    try:
        usage_store.log_usage(meeting_id, call_type, _MODEL, response.usage)
    except Exception as e:
        print(f"[usage_store] failed to log usage for {meeting_id} ({call_type}): {e}")


# gpt-4o-mini mengembalikan paling banyak ~16k token dan dulu memotong transkrip panjang separuhnya, jadi dikerjakan per potongan
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
    """Apakah `fixed` benar-benar koreksi dari `raw`? Menjaga dari nomor baris yang salah:
    baris seperti itu punya pembicara lain atau kata yang tidak berkaitan."""
    if raw.split("]")[0] != fixed.split("]")[0]:
        return False
    # koreksi yang benar mengubah satu-dua kata: panjang mirip dan teks hampir sama
    if not 0.75 <= len(fixed) / max(len(raw), 1) <= 1.3:
        return False
    return difflib.SequenceMatcher(None, raw.lower(), fixed.lower()).ratio() >= 0.75


def _fix_chunk(client: OpenAI, text: str, meeting_id: str, part: int, parts: int) -> str:
    """`text` dengan koreksi model diterapkan, selalu dengan jumlah baris yang sama. Editor memasangkan baris mentah N
    dengan baris perbaikan N dan penulisan ulang penuh menggabung atau menghilangkan baris, jadi model hanya
    mengembalikan baris yang diubah menurut nomornya dan masing-masing dicek terhadap baris yang diklaim diperbaiki."""
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


# rekaman yang nyaris kosong tidak boleh sampai ke model, ia minta maaf atau mengarang rapat
_MIN_WORDS = 15
NO_SPEECH_SUMMARY = {
    "executive_summary": "Tidak ada percakapan yang terdeteksi dalam rekaman ini.",
    "short_summary": "Tidak ada percakapan yang terdeteksi dalam rekaman ini.",
    "key_decisions": [],
    "topics_discussed": [],
    "action_items": [],
}


def _has_speech(transcript: str) -> bool:
    return len(transcript.split()) >= _MIN_WORDS


def fix_transcript(transcript: str, meeting_id: str) -> str:
    if _has_speech(transcript):
        client = OpenAI()
        chunks = _split_for_fix(transcript)
        transcript = "\n".join(_fix_chunk(client, c, meeting_id, i, len(chunks)) for i, c in enumerate(chunks, start=1))
    artifacts.save_fixed_transcript(meeting_id, transcript)
    return transcript


def _speaker_note(transcript: str) -> str:
    """Menyebut pembicara yang labelnya nama asli (diganti di editor), kalau tidak model tetap
    menulis 'Pembicara 2' untuk [Kresna]."""
    labels = list(dict.fromkeys(re.findall(r"(?m)^\[(.+?)\]", transcript)))
    named = [x for x in labels if not _SPEAKER_LABEL.match(x)]
    if not named:
        return ""
    note = f"Speakers with confirmed real names: {', '.join(named)}. Refer to each of them only by that name, never as 'Pembicara' or 'SPEAKER'."
    if len(named) == len(labels):
        note += " Every speaker in this transcript has a real name, so the word 'Pembicara' must not appear."
    return note + "\n\n"


def _summary_user_message(transcript: str) -> str:
    """Jumlah kata plus panjang target (60% dari transkrip, 250 sampai 1200 kata) supaya ringkasan tumbuh sesuai rapat."""
    words = len(transcript.split())
    target = max(250, min(1200, int(words * 0.6)))
    return f"{_speaker_note(transcript)}Transcript length: {words} words. Write executive_summary of about {target} words.\n\n{transcript}"


def short_summary(transcript: str, meeting_id: str | None) -> str:
    """Ringkasan 2-4 kalimat. Dipakai juga untuk menambahkannya ke rapat yang diringkas sebelum ini ada."""
    if not _has_speech(transcript):
        return NO_SPEECH_SUMMARY["short_summary"]
    response = OpenAI().chat.completions.create(
        model=_MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": _SHORT_PROMPT},
            {"role": "user", "content": _speaker_note(transcript) + transcript},
        ],
    )
    if meeting_id:
        _log_usage(meeting_id, "summarize_short", response)
    text = response.choices[0].message.content.strip()
    return _SPEAKER_INLINE.sub(lambda m: f"Pembicara {int(m.group(1))}", text)


_COMPARE_PROMPT = (
    "You compare two meetings from their summaries, in Indonesian. Return JSON with: "
    "'about_a' and 'about_b' (one plain sentence each, starting 'Rapat A membahas ...' "
    "and 'Rapat B membahas ...', saying what that meeting was about), "
    "'similarities' (list of up to 4 short sentences about what both meetings share: "
    "topics, goals, people, decisions), 'differences' (list of up to 4 short sentences "
    "about what is different or only in one of them, say which one: Rapat A or Rapat B), "
    "'progress' (list of up to 3 short sentences about follow-up or change from A to B, "
    "such as an action item or decision that moved on; empty list if the meetings are "
    "unrelated), and 'conclusion' (2 to 3 sentences, the overall comparison). Use only "
    "what the summaries say, invent nothing. If the two meetings are about unrelated "
    "things, say that plainly instead of forcing a link. If one summary is empty, an "
    "apology or has no topics, decisions or action items, leave similarities and "
    "progress empty and say in the conclusion that it has too little content to compare."
)


def _compare_block(label: str, meeting: dict, summary: dict) -> str:
    items = "; ".join(a.get("task", "") + (" (selesai)" if a.get("done") else "") for a in summary.get("action_items") or [])
    return (
        f"{label}: {meeting.get('title', '')} ({str(meeting.get('created_at', ''))[:10]})\n"
        f"Ringkasan: {(summary.get('executive_summary') or '')[:3000]}\n"
        f"Topik: {', '.join(summary.get('topics_discussed') or [])}\n"
        f"Keputusan: {'; '.join(summary.get('key_decisions') or [])}\n"
        f"Action item: {items}"
    )


def compare_meetings(meeting_a: dict, summary_a: dict, meeting_b: dict, summary_b: dict) -> dict:
    """Satu panggilan gpt-4o-mini atas ringkasan dua rapat (bukan transkrip):
    kesamaan, perbedaan, perkembangan dari A ke B, dan kesimpulan keseluruhan."""
    response = OpenAI().chat.completions.create(
        model=_MODEL,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _COMPARE_PROMPT},
            {"role": "user", "content": _compare_block("Rapat A", meeting_a, summary_a) + "\n\n" + _compare_block("Rapat B", meeting_b, summary_b)},
        ],
    )
    _log_usage(meeting_a["id"], "compare", response)
    data = json.loads(response.choices[0].message.content)

    def lines(key):
        return [str(x).strip() for x in data.get(key) or [] if str(x).strip()]

    return {
        "about_a": str(data.get("about_a") or "").strip(),
        "about_b": str(data.get("about_b") or "").strip(),
        "similarities": lines("similarities"),
        "differences": lines("differences"),
        "progress": lines("progress"),
        "conclusion": str(data.get("conclusion") or "").strip(),
    }


def _build_summary(transcript: str, meeting_id: str | None) -> dict:
    """Dict ringkasan tanpa menyimpan atau mengindeks, supaya bisa dicoba pada transkrip yang tersimpan."""
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
    short = short_summary(transcript, meeting_id)

    data = json.loads(details.choices[0].message.content)

    def clean(text: str) -> str:
        # "SPEAKER_02" / "pembicara 02" -> "Pembicara 2"
        return _SPEAKER_INLINE.sub(lambda m: f"Pembicara {int(m.group(1))}", text)

    def assignee(value):
        # label pembicara bukan orang dan diarization tidak selalu tepat, jadi jangan menebak nama untuknya
        return None if _SPEAKER_LABEL.match((value or "").strip()) else (value or None)

    paragraphs = clean(narrative.choices[0].message.content.strip()).split("\n\n")
    # ponytail: model terus menambah kalimat penutup ("rapat diakhiri dengan terima kasih..."), jadi
    # dibuang di sini. Butuh pengecekan sungguhan kalau kalimat terakhir yang sah memuat kata-kata itu
    sentences = re.split(r"(?<=[.!?])\s+", paragraphs[-1])
    if _CLOSING.search(sentences[-1]):
        sentences = sentences[:-1]
    paragraphs[-1] = " ".join(sentences)
    return {
        "executive_summary": "\n\n".join(p for p in paragraphs if p.strip()),
        "short_summary": short,
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

    # KB itu opt in: index ulang hanya kalau user menambahkan rapat ini. Diimpor di sini supaya pemanggil yang tidak pernah
    # punya rapat KB (image transkriber) tidak butuh chromadb
    try:
        meeting = meetings_store.get_meeting(meeting_id)
        if meeting and meeting.get("in_kb"):
            from . import knowledge_base

            knowledge_base.index_meeting(meeting_id, summary)
    except Exception as e:
        print(f"[knowledge_base] failed to re-index meeting {meeting_id}: {e}")

    return summary
