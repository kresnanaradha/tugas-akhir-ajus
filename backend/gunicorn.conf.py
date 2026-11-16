"""Server produksi (menggantikan server pengembangan Flask yang dipakai `python app.py`): `gunicorn -c gunicorn.conf.py app:app`.

Satu proses dengan banyak thread, bukan banyak proses: worker perekam (join_worker_loop) hidup sebagai thread di proses
ini dan hanya boleh ada satu per container (dua bot di satu display saling merekam)."""

import os
import threading

bind = "0.0.0.0:5050"
workers = 1
worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", "16"))
# gthread: permintaan yang lama (unggah, transkripsi) berjalan di thread sendiri dan tidak membuat proses dianggap macet,
# jadi batas ini hanya kena kalau proses utamanya sendiri macet
timeout = 120
accesslog = "-"


def post_worker_init(worker):
    # RECORDER=0 menjalankan API saja (tanpa bot), untuk server yang tidak merekam
    if os.getenv("RECORDER", "1") != "0":
        import join_worker

        threading.Thread(target=join_worker.join_worker_loop, daemon=True).start()
