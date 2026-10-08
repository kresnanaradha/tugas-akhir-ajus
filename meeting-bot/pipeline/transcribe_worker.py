import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import whisperx
from whisperx.diarize import DiarizationPipeline

from . import artifacts

_DEVICE = "cpu"

# Whisper treats this as the text that came just before the audio. It must stay
# generic: a topic-specific prompt (this used to name Docker, RAM, GPU, dosen,
# demo) makes it guess those words in meetings about anything else. Names and
# terms for one deployment go in EXTRA_VOCAB / WHISPER_INITIAL_PROMPT in .env.
_DEFAULT_PROMPT = "Percakapan rapat dalam bahasa Indonesia, dengan beberapa istilah bahasa Inggris."

_model = None
_align_cache = {}
_diarize_model = None


def _stage(name: str, t0: float) -> float:
    """Prints how long a stage took (shows up in the transcriber's log) and
    returns the new start time -- there is no other sign of progress in a long job."""
    now = time.time()
    print(f"[timing] {name}: {now - t0:.0f}s", flush=True)
    return now


def _get_model():
    global _model
    if _model is None:
        prompt = os.getenv("WHISPER_INITIAL_PROMPT", _DEFAULT_PROMPT)
        extra = os.getenv("EXTRA_VOCAB", "").strip()  # names/terms, same setting summarize.py reads
        if extra:
            prompt += f" Nama: {extra}."
        _model = whisperx.load_model(
            os.getenv("WHISPER_MODEL", "large-v3-turbo"),
            device=_DEVICE,
            compute_type="int8",
            asr_options={"initial_prompt": prompt},
            **({"threads": int(os.environ["WHISPER_THREADS"])} if os.getenv("WHISPER_THREADS") else {}),
        )
    return _model


def _get_align_model(language_code: str):
    # Cached per language — a meeting could switch between the Indonesian
    # and English models the proposal's auto-detect requires.
    if language_code not in _align_cache:
        _align_cache[language_code] = whisperx.load_align_model(language_code=language_code, device=_DEVICE)
    return _align_cache[language_code]


def _get_diarize_model():
    global _diarize_model
    if _diarize_model is None:
        _diarize_model = DiarizationPipeline(token=os.environ["HF_TOKEN"], device=_DEVICE)
    return _diarize_model


def _container_times(path: str):
    """(decoded_start, container_pts) of every audio packet, or None.

    Whisper's timestamps count decoded samples. A browser recording
    (MediaRecorder) stamps its audio packets from a wall clock that runs a bit
    ahead of the samples (60 ms packets, stamped 66 ms apart), so a 60-minute
    file holds 54.5 minutes of audio and the video player's time runs ahead of
    the transcript's by up to 5.5 minutes: the highlight drifted off the speech.
    This table maps one clock to the other without touching the audio."""
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
# Whisper segments run 10-25 s, so the playback highlight sat on a whole
# paragraph. Re-cut them from word timestamps: at a sentence end once a line is
# a few seconds long, on a speaker change, after a pause, and never past a hard cap.
_MIN_LINE_S, _MAX_LINE_S, _PAUSE_S = 3.0, 12.0, 1.5


# A speaker run shorter than this (seconds) AND with fewer words than _MIN_RUN_WORDS
# is diarization noise at a word boundary, not someone speaking: it joins the run before it.
_MIN_RUN_S, _MIN_RUN_WORDS = 1.0, 3


def _smooth_speakers(words: list[dict]) -> None:
    runs = []  # [start_index, end_index_exclusive]
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


def _split_segments(segments: list[dict]) -> list[dict]:
    out = []
    for seg in segments:
        words = [w for w in seg.get("words") or [] if w.get("word")]
        if not words:
            out.append(seg)
            continue
        # Words like numbers come back without timestamps: borrow the neighbour's.
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


def _repeat_run_keep(texts: list[str], min_run: int = 3) -> list[bool]:
    """Keep-mask that collapses a run of `min_run`+ identical consecutive lines to its first.
    Whisper loops on one phrase over music/noise ("atau bisnisnya ya?" x31 in 24 s,
    "Terima kasih." x7), which no person says in a row. Returned as a mask so the
    transcript text and segments, which must keep the same lines, can both use it."""
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


def _is_hallucination(text: str) -> bool:
    """Whisper loops on a word over silence/music ("Kami mencoba mencoba
    mencoba..."): a line of 4+ words with very few distinct ones is never speech."""
    words = [w.strip(".,!?").lower() for w in text.split()]
    return len(words) >= 4 and len(set(words)) / len(words) <= 0.4


def transcribe(local_recording_path: str, meeting_id: str, num_speakers: int | None = None) -> str:
    """local_recording_path is where the video/audio currently sits on disk
    (whisperx needs a real local file to decode) — meeting_id is what the
    resulting transcript/segments get saved under in R2 (see
    pipeline/artifacts.py), independent of that local path."""
    t = time.time()
    audio = whisperx.load_audio(local_recording_path)
    t = _stage(f"load audio ({len(audio) / 16000:.0f}s of audio)", t)

    # Diarization only needs the audio, not the text, and was ~half of the whole
    # job: run it alongside speech-to-text instead of after it (both are native
    # code that releases the GIL, so threads are enough).
    diarize_future = None
    if num_speakers != 1:

        def _diarize():
            t0 = time.time()
            df = _get_diarize_model()(audio, num_speakers=num_speakers)
            _stage("speaker diarization (parallel)", t0)
            return df

        diarize_future = ThreadPoolExecutor(max_workers=1).submit(_diarize)

    model = _get_model()
    t = _stage(f"load model {os.getenv('WHISPER_MODEL', 'large-v3-turbo')}", t)
    result = model.transcribe(audio)
    t = _stage("speech to text", t)

    # whisperx's own language auto-detect is unreliable on short/quiet clips
    # (its own warning: "Audio is shorter than 30s, language detection may
    # be inaccurate") and isn't restricted to what this app actually
    # supports end-to-end (Indonesian or English, per the proposal) — on a
    # short recording it can guess a closely-related language instead (e.g.
    # "jw" Javanese, "ms" Malay), and whisperx has no alignment model for
    # either, crashing the whole pipeline. Fall back to Indonesian (this
    # app's primary language) rather than forcing it always — English still
    # auto-detects and transcribes normally.
    language = result["language"]
    if language not in ("id", "en"):
        language = "id"

    align_model, align_metadata = _get_align_model(language)
    result = whisperx.align(result["segments"], align_model, align_metadata, audio, _DEVICE)
    t = _stage("word alignment", t)

    # Without a speaker-count hint, clustering guesses how many speakers
    # there are, which tends to under- or over-segment. The real join flow
    # can pass the meeting's actual participant count once that's wired up.
    if num_speakers == 1:
        # Nothing to separate, and diarization was the single biggest cost:
        # 132 of 287 s (46%) on an 84 s recording, plus loading the pyannote
        # model. The user said there is one speaker, so label everything so.
        for seg in result["segments"]:
            seg["speaker"] = "SPEAKER_00"
    else:
        diarize_df = diarize_future.result()  # blocks only if it is slower than the text
        result = whisperx.assign_word_speakers(diarize_df, result)
        t = _stage("waiting for diarization + assigning speakers", t)

    result["segments"] = [
        s for s in _split_segments(result["segments"]) if s["text"].strip() and not _is_hallucination(s["text"])
    ]
    mask = _repeat_run_keep([seg["text"] for seg in result["segments"]])
    if not all(mask):
        print(f"[timing] dropped {mask.count(False)} lines of a phrase repeated in a row (Whisper loop)", flush=True)
        result["segments"] = [seg for seg, k in zip(result["segments"], mask) if k]
    # last step before saving: from the audio's clock to the video's clock
    result["segments"] = _to_container_time(result["segments"], local_recording_path)

    text = "\n".join(f"[{seg.get('speaker', 'UNKNOWN')}] {seg['text'].strip()}" for seg in result["segments"])

    artifacts.save_transcript(meeting_id, text)

    # Also save per-segment timing (start/end/speaker/text), discarded from
    # the plain-text file above — needed for anything that wants to sync
    # transcript lines to recording playback (e.g. highlighting the current
    # line as the video plays). Kept separate rather than changing what
    # transcribe() returns, so every existing caller (fix_transcript,
    # summarize, the API response) keeps working unchanged.
    segments = [
        {
            "speaker": seg.get("speaker", "UNKNOWN"),
            "start": seg.get("start"),
            "end": seg.get("end"),
            "text": seg["text"].strip(),
        }
        for seg in result["segments"]
    ]
    artifacts.save_segments(meeting_id, segments)

    return text


if __name__ == "__main__":
    # Entry point for pipeline/transcribe.py's child process: argv is
    # recording path, meeting id, num_speakers ("" for none), output file.
    import sys
    from pathlib import Path

    path, meeting_id, speakers, out_file = sys.argv[1:5]
    Path(out_file).write_text(transcribe(path, meeting_id, int(speakers) if speakers else None), encoding="utf-8")
