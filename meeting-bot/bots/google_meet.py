import os
import re
import time

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from .base import MeetBotBase

# Selectors/join-flow adapted from screenappai/meeting-bot (MIT), GoogleMeetBot.ts.
# Their config defaults to 10 anonymous-join retries + a 10min admission wait per
# attempt: Google Meet intermittently refuses/redirects-away anonymous automated
# joins even for legitimate accounts, so a single attempt is expected to fail
# sometimes. MAX_JOIN_ATTEMPTS below is our (smaller, POC-sized) version of that.
_CONTINUE_WITHOUT_DEVICES = re.compile("Continue without microphone and camera", re.I)
_JOIN_BUTTON_TEXTS = ["Ask to join", "Join now"]
_NAME_INPUT = 'input[type="text"]'
_ADMITTED_SELECTOR = 'button[aria-label^="Leave call"]'
_CANT_JOIN_TEXT = "You can't join this video call"
# The waiting-room screen ("Ask to join" was clicked, host hasn't admitted
# yet) apparently also renders a button whose aria-label starts with "Leave
# call" (to cancel the join request) — same prefix _ADMITTED_SELECTOR
# matches for the real in-call "Leave call" button, so that check alone
# false-positives as "admitted" while still stuck waiting. Requiring this
# text to be gone too fixes it: confirmed via a real test recording where
# the bot reported "admitted" and recorded 42s of nothing but this waiting
# screen, never actually joining.
_WAITING_TEXT = "Please wait until a meeting host brings you into the call"
_MAX_JOIN_ATTEMPTS = 3
_ADMIT_WAIT_SECONDS = 60


class GoogleMeetBot(MeetBotBase):
    def join(self) -> str:
        # Google blocks the OAuth login flow itself when driven by an
        # automation-attached browser ("This browser or app may not be
        # secure"), regardless of stealth patches. So the bot never logs in
        # itself: a human logs in once (bots/google_login.py, run outside
        # Docker), which saves cookies/localStorage to GOOGLE_AUTH_STATE_PATH
        # — every join loads that into a fresh browser instead of connecting
        # to a long-lived signed-in Chrome sidecar over CDP. Same effect
        # (an already-authenticated session), but self-contained per
        # container/account instead of needing an external process kept
        # running — see CLAUDE.md for the "1 container = 1 account" plan.
        auth_state_path = os.getenv("GOOGLE_AUTH_STATE_PATH", "auth/google.json")
        if not os.path.exists(auth_state_path):
            raise RuntimeError(
                f"No saved Google session at {auth_state_path} — run "
                "`python -m bots.google_login` once to log in and create it."
            )

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=[
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-first-run-ui",
                    "--disable-default-browser-promo",
                    "--disable-default-apps",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--window-size=1280,800",
                    "--auto-accept-this-tab-capture",
                    "--autoplay-policy=no-user-gesture-required",
                ],
                ignore_default_args=["--mute-audio", "--enable-automation"],
            )
            context = browser.new_context(
                storage_state=auth_state_path, viewport={"width": 1280, "height": 720}, ignore_https_errors=True
            )

            # iframe_content_window/media_codecs evasions disabled to match the
            # reference project's stealth config for Google Meet specifically.
            Stealth(iframe_content_window=False, media_codecs=False).apply_stealth_sync(context)
            self.page = context.new_page()

            admitted = False
            last_error = None
            for attempt in range(1, _MAX_JOIN_ATTEMPTS + 1):
                try:
                    admitted = self._attempt_join()
                    if admitted:
                        break
                    last_error = "Not admitted to the meeting within timeout"
                except Exception as e:
                    last_error = str(e)

            if not admitted:
                browser.close()
                raise RuntimeError(last_error or "Could not join the meeting")

            out_path = self.record()
            browser.close()
            return out_path

    def _attempt_join(self) -> bool:
        self.page.goto(self.url, wait_until="domcontentloaded")

        # This device-permission modal renders ~2.5-4.5s after load, not
        # immediately: an is_visible() snapshot check here races it and
        # misses the click, leaving the real join form covered underneath.
        # wait_for actually polls until the button appears (or times out).
        try:
            continue_btn = self.page.locator("button", has_text=_CONTINUE_WITHOUT_DEVICES).first
            continue_btn.wait_for(state="visible", timeout=8000)
            continue_btn.click()
            continue_btn.wait_for(state="hidden", timeout=5000)
        except Exception:
            pass

        # Only present for anonymous/guest join; a signed-in account join skips
        # straight to the pre-join screen with the account's own name.
        try:
            name_input = self.page.locator(_NAME_INPUT).first
            name_input.wait_for(state="visible", timeout=8000)
            name_input.fill(self.name)
        except Exception:
            pass

        joined_click = False
        for text in _JOIN_BUTTON_TEXTS:
            btn = self.page.locator("button", has_text=re.compile(text, re.I)).first
            try:
                btn.wait_for(state="visible", timeout=5000)
                btn.click()
                joined_click = True
                break
            except Exception:
                continue
        if not joined_click:
            raise RuntimeError('Could not find "Ask to join" / "Join now" button')

        deadline = time.time() + _ADMIT_WAIT_SECONDS
        while time.time() < deadline:
            try:
                body_text = self.page.evaluate("document.body.innerText")
                if _CANT_JOIN_TEXT in body_text:
                    return False
                if _WAITING_TEXT not in body_text and self.page.locator(_ADMITTED_SELECTOR).first.is_visible(timeout=500):
                    return True
            except Exception:
                return False
            time.sleep(2)
        return False
