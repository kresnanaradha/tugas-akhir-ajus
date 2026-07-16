import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from bots.google_meet import GoogleMeetBot
from bots.zoom import ZoomBot

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
        return jsonify({"status": "done", "recording": recording_path})
    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)}), 500


@app.post("/google/join")
def google_join():
    return _join(GoogleMeetBot)


@app.post("/zoom/join")
def zoom_join():
    return _join(ZoomBot)


if __name__ == "__main__":
    app.run(port=5000)
