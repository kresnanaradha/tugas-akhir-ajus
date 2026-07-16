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
_MAX_JOIN_ATTEMPTS = 3
_ADMIT_WAIT_SECONDS = 60


class GoogleMeetBot(MeetBotBase):
    def join(self) -> str:
        # Google blocks the OAuth login flow itself when driven by an
        # automation-attached browser ("This browser or app may not be
        # secure"), regardless of stealth patches. So the bot never logs in
        # itself: a real Chrome window, started and signed-in by a human
        # (see README), stays running with --remote-debugging-port, and we
        # just attach to that already-authenticated session over CDP.
        cdp_url = os.getenv("GOOGLE_CHROME_CDP_URL")

        with sync_playwright() as p:
            if cdp_url:
                browser = p.chromium.connect_over_cdp(cdp_url)
                context = browser.contexts[0] if browser.contexts else browser.new_context(
                    viewport={"width": 1280, "height": 720}, ignore_https_errors=True
                )
            else:
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
                context = browser.new_context(viewport={"width": 1280, "height": 720}, ignore_https_errors=True)

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
                self._cleanup(cdp_url, browser)
                raise RuntimeError(last_error or "Could not join the meeting")

            out_path = self.record()
            self._cleanup(cdp_url, browser)
            return out_path

    def _cleanup(self, cdp_url: str, browser) -> None:
        # For the shared CDP Chrome, only close our tab so the signed-in
        # session stays up for the next join; otherwise close the whole browser.
        if cdp_url:
            self.page.close()
        else:
            browser.close()

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
                if self.page.locator(_ADMITTED_SELECTOR).first.is_visible(timeout=500):
                    return True
                if _CANT_JOIN_TEXT in self.page.evaluate("document.body.innerText"):
                    return False
            except Exception:
                return False
            time.sleep(2)
        return False
