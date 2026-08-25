import os

import whisper

from paths import sibling_path

_model = None


def _get_model():
    global _model
    if _model is None:
        _model = whisper.load_model(os.getenv("WHISPER_MODEL", "base"))
    return _model


# Biases Whisper toward domain terms it otherwise mishears (e.g. "taun
# skripsi" instead of "transkripsi") — override via .env for other domains.
_DEFAULT_PROMPT = (
    "Rapat mengenai Notulis, bot perekam rapat Zoom dan Google Meet, "
    "transkripsi otomatis dengan Whisper, dan ringkasan AI."
)


def transcribe(recording_path: str) -> str:
    prompt = os.getenv("WHISPER_INITIAL_PROMPT", _DEFAULT_PROMPT)
    text = _get_model().transcribe(recording_path, initial_prompt=prompt)["text"]

    sibling_path(recording_path, "transcripts", ".txt").write_text(text, encoding="utf-8")

    return text
