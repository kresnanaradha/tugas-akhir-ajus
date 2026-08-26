import os

import whisperx
from whisperx.diarize import DiarizationPipeline

from paths import sibling_path

_DEVICE = "cpu"

# Biases Whisper toward domain terms it otherwise mishears (e.g. "taun
# skripsi" instead of "transkripsi") — override via .env for other domains.
_DEFAULT_PROMPT = (
    "Rapat mengenai Notulis, bot perekam rapat Zoom dan Google Meet, "
    "transkripsi otomatis dengan Whisper, dan ringkasan AI."
)

_model = None
_align_cache = {}
_diarize_model = None


def _get_model():
    global _model
    if _model is None:
        prompt = os.getenv("WHISPER_INITIAL_PROMPT", _DEFAULT_PROMPT)
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


def transcribe(recording_path: str, num_speakers: int | None = None) -> str:
    audio = whisperx.load_audio(recording_path)

    result = _get_model().transcribe(audio)

    align_model, align_metadata = _get_align_model(result["language"])
    result = whisperx.align(result["segments"], align_model, align_metadata, audio, _DEVICE)

    # Without a speaker-count hint, clustering guesses how many speakers
    # there are, which tends to under- or over-segment. The real join flow
    # can pass the meeting's actual participant count once that's wired up.
    diarize_df = _get_diarize_model()(audio, num_speakers=num_speakers)
    result = whisperx.assign_word_speakers(diarize_df, result)

    text = "\n".join(f"[{seg.get('speaker', 'UNKNOWN')}] {seg['text'].strip()}" for seg in result["segments"])

    sibling_path(recording_path, "transcripts", ".txt").write_text(text, encoding="utf-8")

    return text
