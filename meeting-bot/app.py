import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from bots.google_meet import GoogleMeetBot
from bots.zoom import ZoomBot
from pipeline.summarize import fix_transcript, summarize
from pipeline.transcribe import transcribe

load_dotenv()

app = Flask(__name__)
MAX_DURATION_MIN = float(os.getenv("MAX_RECORDING_DURATION_MINUTES", "5"))


def _join(bot_cls):
    data = request.get_json(force=True) or {}
    url = data.get("url")
    name = data.get("name") or "Notulis Bot"
    if not url:
        return jsonify({"error": "url is required"}), 400

    bot = bot_cls(url, name, MAX_DURATION_MIN)
    try:
        recording_path = bot.join()
    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)}), 500

    result = {"status": "done", "recording": recording_path}

    # Each step's failure is reported separately instead of failing the whole
    # request — a bad transcription/summarization shouldn't erase a
    # successful recording that's already sitting on disk.
    try:
        transcript = transcribe(recording_path)
        result["transcript"] = transcript
    except Exception as e:
        result["transcript_error"] = str(e)
        return jsonify(result)

    # Summarize the LLM-corrected transcript when that step succeeds, since
    # otherwise ASR mistakes (e.g. misheard words) just carry straight into
    # the summary. Fall back to the raw transcript rather than failing the
    # whole request if only the fix step breaks.
    to_summarize = transcript
    try:
        to_summarize = fix_transcript(transcript, recording_path)
        result["fixed_transcript"] = to_summarize
    except Exception as e:
        result["fix_transcript_error"] = str(e)

    try:
        result["summary"] = summarize(to_summarize, recording_path)
    except Exception as e:
        result["summary_error"] = str(e)

    return jsonify(result)


@app.post("/google/join")
def google_join():
    return _join(GoogleMeetBot)


@app.post("/zoom/join")
def zoom_join():
    return _join(ZoomBot)


if __name__ == "__main__":
    app.run(port=5000)
