"""Semua instruksi (prompt) yang dikirim ke GPT-4o mini, di satu tempat supaya mudah dibaca dan diubah tanpa menyentuh
kode pemanggilnya. Ditulis dalam bahasa Inggris karena model mengikutinya lebih konsisten, hasilnya tetap mengikuti
bahasa transkrip. Pesan user (transkrip, jumlah kata, catatan nama pembicara) disusun di summarize.py."""

# --- 1. Perbaikan transkrip (fix_transcript): memperbaiki salah dengar Whisper per baris

FIX_TRANSCRIPT = (
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
FIX_NAMES = (
    " Names of people are often misheard too. If a word is clearly a garbled "
    "person's name given the context (for example someone being assigned a "
    "task) and it sounds like a name in the known list below, use that "
    "spelling. If a name appears with slightly different spellings, make them "
    "consistent. If it does not sound like anything in the list, keep it as-is "
    "rather than guessing. Known terms and names: {terms}."
)

# --- 2. Ringkasan rapat (summarize): tiga panggilan, narasi, data terstruktur, ringkasan singkat

# narasi dan data terstruktur punya prompt pendek sendiri: satu prompt besar membuat gpt-4o-mini
# mengikuti aturannya tidak konsisten
NARRATIVE_SUMMARY = (
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

SUMMARY_DETAILS = (
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
SHORT_SUMMARY = (
    "You write a short summary of a meeting transcript, in the same language as "
    "the transcript: 2 to 4 sentences, at most about 70 words, saying what the "
    "meeting was about and its main outcome or decisions. No greetings, no "
    "mention of the meeting ending, nothing that is not in the transcript. If a "
    "speaker has to be mentioned, write 'Pembicara N' for a label like SPEAKER_0N, "
    "or the exact name for a label that is a real name; prefer not to mention "
    "speakers at all. Plain text, one paragraph."
)

# --- 3. Perbandingan dua rapat (compare_meetings), dari ringkasannya, bukan transkrip

COMPARE_MEETINGS = (
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

# --- 4. Jawaban Knowledge Base (knowledge_base.answer): RAG, hanya dari potongan yang ditemukan

KB_ANSWER = (
    "You answer a question about a team's past meetings using ONLY the excerpts "
    "given below, each tagged with which meeting it's from. Do not use any "
    "outside knowledge and do not invent meetings, people, dates, or facts not "
    "present in the excerpts. Write a short, direct answer (2-4 sentences), in "
    "the same language as the question, naturally mentioning which meeting(s) "
    "it's based on. If the excerpts genuinely don't answer the question, say so "
    "plainly instead of guessing - do not pad with a vague answer."
)
