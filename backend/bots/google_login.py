"""Login sekali: membuka Chrome asli (subproses biasa, bukan playwright.chromium.launch) dengan remote debugging,
menunggu orang login ke akun Google bot, lalu terhubung lewat CDP sebentar saja untuk menyimpan sesi ke
GOOGLE_AUTH_STATE_PATH. GoogleMeetBot memuat file itu setiap join.

Login-nya sendiri harus di Chrome yang tidak diotomasi: Google menolak login di browser yang dikendalikan
otomasi ("This browser or app may not be secure"), dengan atau tanpa stealth. Playwright baru menyentuhnya
setelah orangnya selesai.

Jalankan di host, bukan di Docker (butuh layar dan seseorang yang mengetik password / kode 2FA), sekali per
akun: python -m bots.google_login. Jalankan lagi saat sesi tersimpan habis."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

AUTH_STATE_PATH = os.getenv("GOOGLE_AUTH_STATE_PATH", "auth/google.json")
_CDP_PORT = 9333

_CHROME_CANDIDATES = [
    os.getenv("CHROME_EXECUTABLE_PATH"),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def _find_chrome() -> str:
    for candidate in _CHROME_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError(
        "Could not find a real Chrome install in the usual locations. "
        "Set CHROME_EXECUTABLE_PATH in .env to its full path."
    )


def main():
    Path(AUTH_STATE_PATH).parent.mkdir(parents=True, exist_ok=True)
    chrome_path = _find_chrome()
    profile_dir = tempfile.mkdtemp(prefix="notulis-google-login-")

    proc = subprocess.Popen(
        [chrome_path, f"--remote-debugging-port={_CDP_PORT}", f"--user-data-dir={profile_dir}", "https://accounts.google.com/"]
    )
    try:
        input("Log in to the bot's Google account in the Chrome window that just opened, then press Enter here to save the session... ")
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{_CDP_PORT}")
            context = browser.contexts[0]
            context.storage_state(path=AUTH_STATE_PATH)
            browser.close()
        print(f"Saved session to {AUTH_STATE_PATH}")
    finally:
        proc.terminate()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
