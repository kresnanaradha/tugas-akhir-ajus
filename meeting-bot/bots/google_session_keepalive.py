"""k06: keeps GOOGLE_AUTH_STATE_PATH's saved Google session from going
stale (seen once: worker-1.json signed out within ~2 hours of the last
login) WITHOUT ever touching a password. Unlike bots/google_login.py, this
never logs in -- it just revisits an authenticated Google page using the
cookies google_login.py already saved, the same way staying signed into a
normal browser tab keeps a session alive by itself. No credentials, no
human, so (unlike google_login.py) this is safe to run headless/unattended
-- Google's automation block is specifically on the LOGIN flow, not on
reusing an already-established session.

Run it periodically (every 30-60 min is plenty -- the known expiry was
~2h): via `docker exec` on a schedule (Windows Task Scheduler, cron, etc),
e.g.
    docker exec meeting-bot-worker-1-1 python -m bots.google_session_keepalive
or straight on the host the same way bots/google_login.py runs:
    python -m bots.google_session_keepalive

Exits 0 and re-saves a refreshed storage_state on success. Exits 1 and
leaves the saved file untouched if the session already expired (redirected
to a sign-in page) -- that means a human needs to re-run google_login.py,
not this script.
"""

import os
import sys

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

AUTH_STATE_PATH = os.getenv("GOOGLE_AUTH_STATE_PATH", "auth/google.json")
# Lighter than a Meet URL (no camera/mic prompt, no meeting-join UI to
# navigate) -- all this needs is any page that proves the session is still
# authenticated and gives Google a reason to extend it.
_CHECK_URL = "https://myaccount.google.com/"
# If the session's dead, this ends up back on a sign-in form instead --
# every variant of Google's login domain redirects through accounts.google.com.
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
