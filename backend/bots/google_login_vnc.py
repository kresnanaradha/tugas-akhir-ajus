"""Login akun Google bot langsung di dalam container, ke profil Chromium permanen (GOOGLE_PROFILE_DIR) yang nanti dipakai
bot setiap join. Beda dengan google_login.py (login di Chrome host lalu cookie-nya disalin ke container): di sini browser,
perangkat, dan IP saat login sama dengan saat dipakai, jadi tidak ada cookie pindahan yang ditolak Google.

Layar container dilihat lewat noVNC (http://localhost:6080/vnc.html, kata sandi VNC_PASSWORD di .env). Jalankan saat
worker tidak sedang merekam, karena jendela login muncul di display yang sama dengan bot:
    docker compose exec worker-1 python -m bots.google_login_vnc

Chromium dijalankan sebagai proses biasa, bukan lewat Playwright: Google menolak login di browser yang diotomasi."""

import os
import subprocess
import sys

from playwright.sync_api import sync_playwright

from pipeline import join_queue

PROFILE_DIR = os.getenv("GOOGLE_PROFILE_DIR")


def _worker_busy() -> bool:
    try:
        return any(w["id"] == join_queue.WORKER_ID and w.get("busy") for w in join_queue.workers())
    except Exception:
        return False  # Redis tidak terjangkau: biarkan orangnya yang memutuskan


def main() -> int:
    if not PROFILE_DIR:
        print("GOOGLE_PROFILE_DIR belum diisi untuk worker ini (lihat docker-compose.yml).")
        return 1
    if _worker_busy():
        print("Worker ini sedang merekam rapat. Tunggu rapatnya selesai, jendela login akan ikut terekam.")
        return 1
    os.makedirs(PROFILE_DIR, exist_ok=True)

    with sync_playwright() as p:
        chromium = p.chromium.executable_path
    proc = subprocess.Popen(
        [
            chromium,
            f"--user-data-dir={PROFILE_DIR}",
            # sama dengan yang dipakai Playwright, supaya cookie terenkripsi dengan kunci yang sama dan bisa dibaca bot
            "--password-store=basic",
            "--no-sandbox",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-position=0,0",
            "--window-size=1280,1000",
            "https://accounts.google.com/",
        ],
        env={**os.environ, "DISPLAY": os.getenv("DISPLAY", ":99")},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print("Chromium terbuka di layar container. Buka http://localhost:6080/vnc.html, login akun Google bot,")
    print("tunggu sampai halaman akun Google tampil, lalu tekan Enter di sini untuk menyimpan dan menutup browser.")
    try:
        input()
    finally:
        # tutup dengan sopan (SIGTERM) supaya Chromium menulis cookie ke profil sebelum keluar
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
    print(f"Selesai. Profil tersimpan di {PROFILE_DIR}, bot memakainya mulai join berikutnya.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
