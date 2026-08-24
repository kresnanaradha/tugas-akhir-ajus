import time
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from .base import MeetBotBase

# Join-flow adapted (simplified for POC) from screenappai/meeting-bot (MIT), ZoomBot.ts.
# Navigates straight to Zoom's embedded web client URL (/wc/join/<id>) instead
# of the normal /j/<id> landing page. That landing page's JS auto-attempts a
# zoommtg:// native-app launch, which triggers a Chromium "Open Zoom
# Meetings?" dialog that isn't a JS dialog (Playwright can't see/dismiss it)
# and isn't interceptable via page.route() (custom-scheme navigations never
# become network requests). Going straight to /wc/join/ skips that page and
# its redirect entirely — no dialog, no risk of it silently launching the
# real Zoom desktop app under the host machine's own account.


def _web_client_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.replace("/j/", "/wc/join/", 1)
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


class ZoomBot(MeetBotBase):
    def join(self) -> str:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=[
                    "--use-fake-ui-for-media-stream",
                    "--auto-accept-this-tab-capture",
                    # --auto-accept-this-tab-capture alone picks whichever tab
                    # has OS-level window focus at getDisplayMedia() time —
                    # bring_to_front() only switches Playwright's active tab,
                    # it doesn't reliably steal real OS focus from whatever
                    # else is focused (e.g. the terminal that fired the join
                    # request), so it kept capturing the whole desktop. This
                    # picks the tab by exact title match instead, regardless
                    # of focus — record() sets document.title to the same
                    # secretId right before capturing.
                    f"--auto-select-tab-capture-source-by-title={self.secret_id}",
                    "--autoplay-policy=no-user-gesture-required",
                ],
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                ignore_https_errors=True,
                permissions=["camera", "microphone"],
            )
            # Zoom's web client flags navigator.webdriver etc. and refuses the
            # join ("Automated bots aren't allowed to join this meeting")
            # without this. Reference project (puppeteer-extra-plugin-stealth
            # via playwright-extra) only disables iframe.contentWindow and
            # media.codecs, leaving chrome.runtime patched — but this Python
            # port defaults chrome_runtime to OFF, unlike every other evasion
            # (all default True). That gap is likely why Zoom's bot check
            # passes some runs and not others.
            Stealth(iframe_content_window=False, media_codecs=False, chrome_runtime=True).apply_stealth_sync(context)
            self.page = context.new_page()
            # Diagnostics: kept around since they're free — if "Target page,
            # context or browser has been closed" happens again, one of these
            # should say why.
            self.page.on("crash", lambda: print("[ZoomBot] page CRASHED"))
            self.page.on("close", lambda: print("[ZoomBot] page closed"))
            self.page.on("pageerror", lambda exc: print(f"[ZoomBot] page error: {exc}"))
            self.page.on("console", lambda msg: print(f"[ZoomBot] console.{msg.type}: {msg.text}"))
            context.on("close", lambda: print("[ZoomBot] context closed"))
            browser.on("disconnected", lambda: print("[ZoomBot] browser disconnected"))

            self.page.goto(_web_client_url(self.url), wait_until="domcontentloaded")

            try:
                accept = self.page.locator("button", has_text="Accept Cookies").first
                if accept.is_visible(timeout=2500):
                    accept.click(force=True)
            except Exception:
                pass

            try:
                self.page.wait_for_selector('input[type="text"]', timeout=30000)
                self.page.fill('input[type="text"]', self.name)

                # meetingbot/meetingbot (MIT) found the mute/video toggles
                # aren't reliably clickable right after the input field shows
                # up — a shorter wait made the click miss randomly and the
                # bot would join with sound/video still on. They wait 6s
                # before clicking; matching that, plus their ID selectors
                # (sturdier than text, which Zoom has changed before) with a
                # text-based fallback.
                self.page.wait_for_timeout(6000)

                def click_toggle(selector: str, label: str) -> None:
                    try:
                        self.page.locator(selector).click(timeout=3000)
                    except Exception:
                        try:
                            self.page.locator("button", has_text=label).first.click(timeout=3000)
                        except Exception:
                            pass

                click_toggle("#preview-audio-control-button", "Mute")

                # The camera's getUserMedia device takes longer to come up
                # than the mic, so this button can still look clickable but
                # not yet be wired to the toggle — the click lands but nothing
                # happens. Verify via aria-label (it flips to "Start Video"
                # once off) and retry once after a bit more time.
                video_selector = "#preview-video-control-button"
                click_toggle(video_selector, "Stop Video")
                try:
                    label = self.page.locator(video_selector).get_attribute("aria-label", timeout=2000) or ""
                    if "start video" not in label.lower():
                        self.page.wait_for_timeout(2000)
                        click_toggle(video_selector, "Stop Video")
                except Exception:
                    pass

                self.page.locator("button", has_text="Join").first.click()
            except Exception:
                browser.close()
                raise RuntimeError("Could not find the Zoom web client join form")

            deadline = time.time() + 60
            admitted = False
            while time.time() < deadline:
                body_text = self.page.locator("body").inner_text()
                if "participants" in body_text.lower():
                    admitted = True
                    break
                time.sleep(2)
            if not admitted:
                browser.close()
                raise RuntimeError("Not admitted to the Zoom meeting within timeout")

            # Zoom's web client usually asks how to join audio on entry.
            try:
                self.page.locator("button", has_text="Join Audio by Computer").first.click(timeout=8000)
            except Exception:
                pass

            out_path = self.record()
            browser.close()
            return out_path
