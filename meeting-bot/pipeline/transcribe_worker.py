import os

import whisperx
from whisperx.diarize import DiarizationPipeline

from . import artifacts

_DEVICE = "cpu"

# Biases Whisper toward domain terms it otherwise mishears (e.g. "taun
# skripsi" instead of "transkripsi") — override via .env for other domains.
_DEFAULT_PROMPT = (
    "Rapat mengenai Notulis, bot perekam rapat Zoom dan Google Meet, "
    "transkripsi otomatis dengan Whisper, dan ringkasan AI. Istilah yang sering "
    "muncul: Docker, kontainer, RAM, CPU, GB, skrip, Knowledge Base, diarization, dosen, demo."
)

_model = None
_align_cache = {}
_diarize_model = None


def _get_model():
    global _model
    if _model is None:
        prompt = os.getenv("WHISPER_INITIAL_PROMPT", _DEFAULT_PROMPT)
        extra = os.getenv("EXTRA_VOCAB", "").strip()  # names/terms, same setting summarize.py reads
        if extra:
            prompt += f" Nama: {extra}."
        _model = whisperx.load_model(
            os.getenv("WHISPER_MODEL", "medium"),
            device=_DEVICE,
            compute_type="int8",
            asr_options={"initial_prompt": prompt},
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


def transcribe(local_recording_path: str, meeting_id: str, num_speakers: int | None = None) -> str:
    """local_recording_path is where the video/audio currently sits on disk
    (whisperx needs a real local file to decode) — meeting_id is what the
    resulting transcript/segments get saved under in R2 (see
    pipeline/artifacts.py), independent of that local path."""
    audio = whisperx.load_audio(local_recording_path)

    result = _get_model().transcribe(audio)

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
        diarize_df = _get_diarize_model()(audio, num_speakers=num_speakers)
        result = whisperx.assign_word_speakers(diarize_df, result)

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
