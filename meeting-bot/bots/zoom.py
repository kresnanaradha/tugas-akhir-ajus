import time

from playwright.sync_api import sync_playwright

from .base import MeetBotBase

# Join-flow adapted (simplified for POC) from screenappai/meeting-bot (MIT), ZoomBot.ts.
# Skips their "Launch Meeting"/"Download Now" fallback chain and retry logic —
# assumes the meeting URL lands directly on the page with a
# "Join from your browser" link, which is the common case.


class ZoomBot(MeetBotBase):
    def join(self) -> str:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=[
                    "--use-fake-ui-for-media-stream",
                    "--auto-accept-this-tab-capture",
                    "--autoplay-policy=no-user-gesture-required",
                ],
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                ignore_https_errors=True,
                permissions=["camera", "microphone"],
            )
            self.page = context.new_page()
            self.page.goto(self.url, wait_until="domcontentloaded")

            try:
                accept = self.page.locator("button", has_text="Accept Cookies").first
                if accept.is_visible(timeout=2500):
                    accept.click(force=True)
            except Exception:
                pass

            join_from_browser = self.page.locator("a", has_text="Join from your browser").first
            try:
                join_from_browser.wait_for(timeout=15000)
                join_from_browser.click(force=True)
            except Exception:
                browser.close()
                raise RuntimeError('Could not find "Join from your browser" link — Zoom UI may have changed')

            iframe_el = self.page.wait_for_selector("iframe#webclient", timeout=30000)
            frame = iframe_el.content_frame()
            if frame is None:
                browser.close()
                raise RuntimeError("Could not access Zoom web client iframe")

            frame.wait_for_selector('input[type="text"]', timeout=30000)
            frame.fill('input[type="text"]', self.name)
            frame.locator("button", has_text="Join").first.click()

            deadline = time.time() + 60
            admitted = False
            while time.time() < deadline:
                body_text = frame.locator("body").inner_text()
                if "participants" in body_text.lower():
                    admitted = True
                    break
                time.sleep(2)
            if not admitted:
                browser.close()
                raise RuntimeError("Not admitted to the Zoom meeting within timeout")

            out_path = self.record()
            browser.close()
            return out_path
