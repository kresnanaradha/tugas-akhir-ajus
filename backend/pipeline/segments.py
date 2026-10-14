"""Langkah setelah transkripsi yang sama untuk whisperx lokal dan Replicate: potong ulang segmen dari timestamp kata,
buang halusinasi, petakan waktu ke jam video, lalu simpan transkrip dan segmen ke R2. Tidak mengimpor whisperx."""

import subprocess

from . import artifacts


def _container_times(path: str):
    """(decoded_start, container_pts) untuk setiap paket audio, atau None.

    Whisper menghitung sampel yang didecode, tapi rekaman browser memberi stempel paket 60 ms-nya berjarak 66 ms, jadi
    file 60 menit hanya berisi 54,5 menit audio dan jam video berjalan sampai 5,5 menit lebih awal dari
    transkrip. Tabel ini memetakan satu jam ke jam lainnya tanpa menyentuh audionya."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "packet=pts_time,duration_time", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=300,
        ).stdout.splitlines()
        packets = sorted((float(a), float(b)) for a, b in (ln.split(",")[:2] for ln in out if ln.count(",") >= 1) if a and b)
    except Exception as e:
        print(f"[timing] could not read audio packet times ({e}), keeping decoded-sample times", flush=True)
        return None
    if len(packets) < 2:
        return None
    decoded, t = [], 0.0
    for _, dur in packets:
        decoded.append(t)
        t += dur
    span = packets[-1][0] + packets[-1][1] - packets[0][0]
    if span > 0:
        pct = 100 * t / span
        print(f"[timing] recorded audio is {pct:.1f}% complete ({span - t:.0f}s of {span:.0f}s missing)" + (" -- samples were dropped while recording" if pct < 98 else ""), flush=True)
    return decoded, [pts for pts, _ in packets]


def _to_container_time(segments: list[dict], path: str) -> list[dict]:
    table = _container_times(path)
    if table is None:
        return segments
    import numpy as np

    decoded, pts = table
    for seg in segments:
        for key in ("start", "end"):
            if seg.get(key) is not None:
                seg[key] = round(float(np.interp(seg[key], decoded, pts)), 3)
    return segments


_SENTENCE_END = (".", "?", "!")
# segmen whisper 10-25 detik, terlalu panjang untuk sorotan saat diputar. Dipotong ulang dari timestamp kata: di
# akhir kalimat begitu baris berdurasi beberapa detik, saat pembicara ganti, setelah jeda, tidak pernah lewat batas keras
_MIN_LINE_S, _MAX_LINE_S, _PAUSE_S = 3.0, 12.0, 1.5


# putaran bicara yang lebih pendek dari _MIN_RUN_S detik dan di bawah _MIN_RUN_WORDS kata adalah noise diarization,
# ia bergabung ke putaran sebelumnya
_MIN_RUN_S, _MIN_RUN_WORDS = 1.0, 3


def _smooth_speakers(words: list[dict]) -> None:
    runs = []  # [indeks_awal, indeks_akhir_eksklusif]
    for i, w in enumerate(words):
        if runs and words[runs[-1][0]].get("speaker") == w.get("speaker"):
            runs[-1][1] = i + 1
        else:
            runs.append([i, i + 1])
    for k, (a, b) in enumerate(runs):
        if len(runs) == 1:
            break
        dur = words[b - 1]["end"] - words[a]["start"]
        if b - a < _MIN_RUN_WORDS and dur < _MIN_RUN_S:
            neighbour = words[runs[k - 1][0]] if k > 0 else words[runs[k + 1][0]]
            for w in words[a:b]:
                w["speaker"] = neighbour.get("speaker")


def split_segments(segments: list[dict]) -> list[dict]:
    out = []
    for seg in segments:
        words = [w for w in seg.get("words") or [] if w.get("word")]
        if not words:
            out.append(seg)
            continue
        # angka datang tanpa timestamp, pinjam milik tetangganya
        last_end = seg["start"]
        for w in words:
            if w.get("start") is None:
                w["start"], w["end"] = last_end, last_end
            last_end = w["end"] if w.get("end") is not None else last_end
        _smooth_speakers(words)
        group = []

        def flush():
            if group:
                out.append(
                    {
                        "speaker": group[0].get("speaker") or seg.get("speaker", "UNKNOWN"),
                        "start": group[0]["start"],
                        "end": group[-1]["end"],
                        "text": " ".join(w["word"].strip() for w in group),
                    }
                )
                group.clear()

        for w in words:
            if group:
                span = group[-1]["end"] - group[0]["start"]
                new_speaker = w.get("speaker") != group[0].get("speaker")
                paused = w["start"] - group[-1]["end"] > _PAUSE_S
                at_sentence_end = group[-1]["word"].strip().endswith(_SENTENCE_END) and span >= _MIN_LINE_S
                if new_speaker or paused or at_sentence_end or span >= _MAX_LINE_S:
                    flush()
            group.append(w)
        flush()
    return out


def repeat_run_keep(texts: list[str], min_run: int = 3) -> list[bool]:
    """Mask yang mempertahankan satu: `min_run`+ baris identik berturut-turut diciutkan ke yang pertama. Whisper berulang pada satu frasa
    di atas musik atau noise ("atau bisnisnya ya?" x31), tidak ada yang bicara begitu. Berupa mask supaya transkrip dan
    segmen, yang harus punya baris sama, bisa memakainya."""
    norm = [" ".join("".join(c for c in t.lower() if c.isalnum() or c == " ").split()) for t in texts]
    keep, i = [True] * len(texts), 0
    while i < len(texts):
        j = i
        while j + 1 < len(texts) and norm[j + 1] == norm[i] and norm[i]:
            j += 1
        if j - i + 1 >= min_run:
            for k in range(i + 1, j + 1):
                keep[k] = False
        i = j + 1
    return keep


def is_hallucination(text: str) -> bool:
    """Whisper berulang pada satu kata di atas keheningan ("Kami mencoba mencoba..."): 4+ kata dengan sedikit kata berbeda bukan ucapan."""
    words = [w.strip(".,!?").lower() for w in text.split()]
    return len(words) >= 4 and len(set(words)) / len(words) <= 0.4


def finish(meeting_id: str, raw_segments: list[dict], local_recording_path: str) -> str:
    """Dari segmen mentah (seg + words + speaker) ke transkrip: potong ulang, buang halusinasi dan pengulangan, petakan
    waktu ke jam video, simpan teks dan segmen di bawah meeting_id di R2. Mengembalikan teksnya."""
    segments = [s for s in split_segments(raw_segments) if s["text"].strip() and not is_hallucination(s["text"])]
    mask = repeat_run_keep([seg["text"] for seg in segments])
    if not all(mask):
        print(f"[timing] dropped {mask.count(False)} lines of a phrase repeated in a row (Whisper loop)", flush=True)
        segments = [seg for seg, k in zip(segments, mask) if k]
    # langkah terakhir sebelum menyimpan: dari jam audio ke jam video
    segments = _to_container_time(segments, local_recording_path)

    text = "\n".join(f"[{seg.get('speaker', 'UNKNOWN')}] {seg['text'].strip()}" for seg in segments)
    artifacts.save_transcript(meeting_id, text)

    # timestamp per segmen juga, untuk menyinkronkan baris transkrip dengan video
    artifacts.save_segments(
        meeting_id,
        [
            {
                "speaker": seg.get("speaker", "UNKNOWN"),
                "start": seg.get("start"),
                "end": seg.get("end"),
                "text": seg["text"].strip(),
            }
            for seg in segments
        ],
    )
    return text
