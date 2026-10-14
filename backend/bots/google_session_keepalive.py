"""Menjaga sesi Google tersimpan tidak basi (pernah worker-1.json logout dalam ~2 jam setelah login)
tanpa menyentuh password: hanya membuka lagi halaman Google terautentikasi dengan cookie yang disimpan
google_login.py, jadi bisa jalan tanpa pengawasan dan headless (Google memblokir alur login, bukan sesi yang dipakai ulang).

Jalankan tiap 30-60 menit, mis. docker exec meeting-bot-worker-1-1 python -m bots.google_session_keepalive
atau di host: python -m bots.google_session_keepalive

Exit 0 dan sesi yang disegarkan tersimpan. Exit 1 dan file tidak disentuh kalau sesi sudah habis
(dialihkan ke sign-in): itu butuh orang menjalankan google_login.py."""

import os
import sys

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

AUTH_STATE_PATH = os.getenv("GOOGLE_AUTH_STATE_PATH", "auth/google.json")
# lebih ringan dari url Meet (tanpa izin kamera, tanpa UI join), halaman apa pun yang membuktikan sesi masih login cukup
_CHECK_URL = "https://myaccount.google.com/"
# sesi mati berakhir di form sign in, semua domain login Google mengalihkan lewat accounts.google.com
_SIGNIN_MARKER = "accounts.google.com/signin"


def main() -> int:
    if not os.path.exists(AUTH_STATE_PATH):
        print(f"No saved session at {AUTH_STATE_PATH} -- run `python -m bots.google_login` first.")
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context(storage_state=AUTH_STATE_PATH)
        page = context.new_page()
        page.goto(_CHECK_URL, wait_until="domcontentloaded", timeout=30000)

        if _SIGNIN_MARKER in page.url:
            browser.close()
            print(f"Session at {AUTH_STATE_PATH} has expired (redirected to sign-in) -- re-run google_login.py.")
            return 1

        context.storage_state(path=AUTH_STATE_PATH)
        browser.close()
        print(f"Session still alive, refreshed {AUTH_STATE_PATH}.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
