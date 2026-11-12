"""Titik masuk backend: membuat app Flask, mendaftarkan route per fitur (folder routes/), lalu menjalankan server dan
worker perekam. Isi tiap fitur ada di routes/<fitur>.py, hal yang dipakai bersama di routes/common.py."""

import os
import threading

from dotenv import load_dotenv

# muat .env sebelum import modul lokal, sebagian membaca env var saat import
load_dotenv()

from flask import Flask, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

import join_worker
from routes import admin, auth, billing, meetings, recording, reports, teams

app = Flask(__name__)
# menandatangani cookie sesi, wajib ada supaya tidak ada default yang gampang ditebak
app.secret_key = os.environ["SECRET_KEY"]
# jaga-jaga upload yang terlalu besar, error json supaya frontend bisa membacanya
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1GB

for module in (auth, recording, meetings, reports, admin, billing, teams):
    app.register_blueprint(module.bp)


@app.errorhandler(RequestEntityTooLarge)
def _file_too_large(_e):
    return jsonify({"error": "File terlalu besar (maks 1GB)"}), 413


@app.after_request
def _add_cors_headers(response):
    # supaya dev server Expo (port lain) bisa memanggil kita dengan cookie. Hanya untuk dev, pakai
    # daftar izin, bukan memantulkan origin apa saja, sebelum dirilis ke publik
    origin = request.headers.get("Origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


if __name__ == "__main__":
    # RECORDER=0 menjalankan API saja (tanpa bot), untuk server yang tidak merekam
    if os.getenv("RECORDER", "1") != "0":
        threading.Thread(target=join_worker.join_worker_loop, daemon=True).start()
    # threaded supaya polling /jobs/<id> jalan saat ada join. 5050 karena ada yang terus memakai
    # 5000, 0.0.0.0 supaya port mapping docker bisa menjangkaunya
    app.run(host="0.0.0.0", port=5050, threaded=True)
