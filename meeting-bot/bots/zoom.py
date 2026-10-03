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


# Zoom's bot check and the web client's join form are both flaky (see the
# Stealth note in _attempt_join); Google Meet already retries up to 3 times.
_MAX_JOIN_ATTEMPTS = 3
# Lowercased phrases Zoom's web client shows once the host ends the meeting or
# removes the bot. Taken from Zoom's own wording, not yet confirmed against a
# live end-of-meeting screen -- a miss just means the recording runs to its
# normal time limit like before, so verify and extend this list on first use.
_ENDED_PHRASES = (
    "meeting has been ended by host",
    "host has ended this meeting",
    "this meeting has ended",
    "you have been removed from the meeting",
    "removed by the host",
)


class ZoomBot(MeetBotBase):
    def join(self) -> str:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=[
                    # --use-fake-ui-for-media-stream deliberately NOT here:
                    # on Linux it conflicts with getDisplayMedia() and causes
                    # exactly the "NotReadableError: Could not start video
                    # source" this bot was hitting on every Zoom join
                    # (confirmed against a matching CEF/Chromium forum report,
                    # https://www.magpcss.org/ceforum/viewtopic.php?f=6&t=20150
                    # — and explains why google_meet.py, which never had this
                    # flag, worked while this file consistently failed). Not
                    # needed anyway: permissions=["camera", "microphone"] on
                    # the context below already auto-grants those prompts the
                    # proper Playwright way, without touching Chrome's capture
                    # pipeline. Zoom's own camera/mic still report
                    # NotFoundError since the container has no real device --
                    # unrelated to this flag, already handled by the
                    # toggle_off() try/excepts below.
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
                    # No GPU device in the container (confirmed: no /dev/dri)
                    # -- Chrome's GPU process then has nothing to initialize
                    # and doesn't cleanly fall back to software rendering on
                    # its own, which broke the tab's whole compositor (not
                    # just WebGL): confirmed live via a diagnostic that a
                    # video-only getDisplayMedia() failed with the exact same
                    # "NotReadableError: Could not start video source" as the
                    # combined video+audio call, and the page's own WebGL
                    # init failed too ("WebGL is not supported on this
                    # device"). Mesa's software rasterizer is already
                    # installed in the image (libgl1-mesa-dri, mesa-
                    # libgallium) -- these flags are what make Chrome
                    # actually use it instead of giving up.
                    "--use-gl=angle",
                    "--use-angle=swiftshader",
                    "--enable-unsafe-swiftshader",
                ],
            )
            last_error = None
            for attempt in range(1, _MAX_JOIN_ATTEMPTS + 1):
                try:
                    self._attempt_join(browser)
                    break
                except Exception as e:
                    last_error = e
                    print(f"[ZoomBot] join attempt {attempt}/{_MAX_JOIN_ATTEMPTS} failed: {e}")
                    if attempt < _MAX_JOIN_ATTEMPTS:
                        time.sleep(5)
            else:
                browser.close()
                raise last_error

            # Zoom's web client usually asks how to join audio on entry.
            try:
                self.page.locator("button", has_text="Join Audio by Computer").first.click(timeout=8000)
            except Exception:
                pass

            # try/finally: record() can raise (e.g. getDisplayMedia's
            # "NotReadableError: Could not start video source", confirmed
            # live) — without this, that exception skipped straight past
            # the Leave click and browser.close() below, leaving the bot
            # stuck showing as connected in the Zoom call indefinitely
            # instead of just failing the job cleanly.
            try:
                out_path = self.record()
            finally:
                # Click "Leave" instead of just closing the browser — an
                # abrupt disconnect leaves the bot showing as still
                # connected on Zoom's side until its own timeout notices,
                # instead of leaving cleanly right away.
                try:
                    self.page.locator("button", has_text="Leave").first.click(timeout=1500)
                    self.page.locator("button", has_text="Leave Meeting").first.click(timeout=1500)
                except Exception:
                    pass
                browser.close()
            return out_path

    def meeting_state(self) -> str:
        text = self.page.locator("body").inner_text(timeout=2000).lower()
        if any(phrase in text for phrase in _ENDED_PHRASES):
            return "ended"
        return "active"

    def _attempt_join(self, browser) -> None:
        """One try at getting into the meeting on a fresh context/page. On
        failure the context is closed (so a retry starts clean) and a
        RuntimeError is raised; on success self.page is the joined page."""
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

            def click_toggle(selector: str, label: str) -> bool:
                try:
                    self.page.locator(selector).click(timeout=3000)
                    return True
                except Exception:
                    try:
                        self.page.locator("button", has_text=label).first.click(timeout=3000)
                        return True
                    except Exception:
                        return False

            # The mic/camera's getUserMedia device can take longer to come
            # up than the button itself — the click lands but the toggle
            # isn't wired to it yet, so nothing happens. Verify via
            # aria-label (flips to "Unmute"/"Start Video" once off) and
            # retry once after a bit more time. Printed instead of
            # silently swallowed so a join that ends up on camera anyway
            # shows up in the server log instead of just this docstring.
            def toggle_off(selector: str, click_label: str, off_label: str, name: str) -> None:
                click_toggle(selector, click_label)
                try:
                    label = self.page.locator(selector).get_attribute("aria-label", timeout=2000) or ""
                    if off_label not in label.lower():
                        self.page.wait_for_timeout(2000)
                        click_toggle(selector, click_label)
                        label = self.page.locator(selector).get_attribute("aria-label", timeout=2000) or ""
                    if off_label not in label.lower():
                        print(f"[ZoomBot] could not confirm {name} is off (aria-label: {label!r})")
                except Exception as e:
                    print(f"[ZoomBot] {name} toggle check failed: {e}")

            toggle_off("#preview-audio-control-button", "Mute", "unmute", "mic")
            toggle_off("#preview-video-control-button", "Stop Video", "start video", "camera")

            self.page.locator("button", has_text="Join").first.click()
        except Exception:
            context.close()
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
            context.close()
            raise RuntimeError("Not admitted to the Zoom meeting within timeout")
