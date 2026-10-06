"""One-time interactive login: launches a REAL Chrome (as a plain
subprocess, not via playwright.chromium.launch()) with remote debugging
enabled, waits for a human to sign into the bot's Google account by hand,
then attaches over CDP just long enough to save that session (cookies/
localStorage) to GOOGLE_AUTH_STATE_PATH — google_meet.py's GoogleMeetBot
loads that file on every join afterward instead of needing a live
human-signed-in Chrome sidecar kept running in the background.

Must launch un-automated Chrome for the login step itself: Google's login
page refuses to sign in a browser that's already automation-attached
("This browser or app may not be secure"), even with stealth patches —
confirmed the hard way (see README's "Most likely to break"). Playwright
only touches this browser via CDP after the human has already finished
logging in, same as the old CDP-sidecar setup avoided the same block.

Run on the host (not in Docker — needs a real display and a human to type a
password/2FA code), once per Google account:

    python -m bots.google_login

Re-run it if the saved session ever expires (GoogleMeetBot will complain
that it can't join / gets redirected to a login page).
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

AUTH_STATE_PATH = os.getenv("GOOGLE_AUTH_STATE_PATH", "auth/google.json")
_CDP_PORT = 9333  # distinct from the old GOOGLE_CHROME_CDP_URL default (9222)

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
