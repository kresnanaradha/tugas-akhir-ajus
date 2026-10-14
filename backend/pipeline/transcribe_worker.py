import os
import time
from concurrent.futures import ThreadPoolExecutor

import whisperx
from whisperx.diarize import DiarizationPipeline

from . import segments

_DEVICE = "cpu"

# teks yang dianggap whisper datang tepat sebelum audio. Buat tetap umum, prompt khusus topik membuatnya
# menebak kata-kata itu di setiap rapat. Nama untuk satu deployment masuk EXTRA_VOCAB / WHISPER_INITIAL_PROMPT di .env
_DEFAULT_PROMPT = "Percakapan rapat dalam bahasa Indonesia, dengan beberapa istilah bahasa Inggris."

_model = None
_align_cache = {}
_diarize_model = None


def _stage(name: str, t0: float) -> float:
    """Cetak berapa lama sebuah tahap berjalan (muncul di log transkriber) dan kembalikan waktu mulai yang baru."""
    now = time.time()
    print(f"[timing] {name}: {now - t0:.0f}s", flush=True)
    return now


def _get_model():
    global _model
    if _model is None:
        prompt = os.getenv("WHISPER_INITIAL_PROMPT", _DEFAULT_PROMPT)
        extra = os.getenv("EXTRA_VOCAB", "").strip()  # nama/istilah, pengaturan yang sama dengan yang dibaca summarize.py
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
    # di-cache per bahasa, rapat bisa berbahasa Indonesia atau Inggris
    if language_code not in _align_cache:
        _align_cache[language_code] = whisperx.load_align_model(language_code=language_code, device=_DEVICE)
    return _align_cache[language_code]


def _get_diarize_model():
    global _diarize_model
    if _diarize_model is None:
        _diarize_model = DiarizationPipeline(token=os.environ["HF_TOKEN"], device=_DEVICE)
    return _diarize_model


def transcribe(local_recording_path: str, meeting_id: str, num_speakers: int | None = None) -> str:
    """Transkripsi file lokal (whisperx butuh satu) dan simpan teks dan segmen di bawah meeting_id di R2."""
    t = time.time()
    audio = whisperx.load_audio(local_recording_path)
    t = _stage(f"load audio ({len(audio) / 16000:.0f}s of audio)", t)

    # diarization hanya butuh audio dan setengah dari seluruh pekerjaan, jadi dijalankan berdampingan dengan speech to text
    # (kode native, thread cukup)
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

    # deteksi bahasa whisperx tidak andal pada klip pendek dan bisa memilih bahasa yang tidak punya model alignment
    # (jw, ms) lalu crash, jadi apa pun selain id atau en menjadi bahasa Indonesia
    language = result["language"]
    if language not in ("id", "en"):
        language = "id"

    align_model, align_metadata = _get_align_model(language)
    result = whisperx.align(result["segments"], align_model, align_metadata, audio, _DEVICE)
    t = _stage("word alignment", t)

    # tanpa petunjuk jumlah pembicara, clustering cenderung terlalu sedikit atau terlalu banyak
    if num_speakers == 1:
        # satu pembicara: tidak ada yang dipisahkan, dan diarization adalah biaya terbesar
        for seg in result["segments"]:
            seg["speaker"] = "SPEAKER_00"
    else:
        diarize_df = diarize_future.result()  # menunggu hanya kalau lebih lambat dari teks
        result = whisperx.assign_word_speakers(diarize_df, result)
        t = _stage("waiting for diarization + assigning speakers", t)

    return segments.finish(meeting_id, result["segments"], local_recording_path)


if __name__ == "__main__":
    # titik masuk untuk proses anak transcribe.py: path rekaman, id rapat, num_speakers ('' kalau tidak ada), file keluaran
    import sys
    from pathlib import Path

    path, meeting_id, speakers, out_file = sys.argv[1:5]
    Path(out_file).write_text(transcribe(path, meeting_id, int(speakers) if speakers else None), encoding="utf-8")
