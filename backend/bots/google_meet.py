import os
import re
import time

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from .base import MeetBotBase

# selector dan alur join diadaptasi dari screenappai/meeting-bot (MIT), GoogleMeetBot.ts. Meet kadang menolak
# join otomatis bahkan untuk akun asli, jadi satu percobaan wajar gagal sesekali
_CONTINUE_WITHOUT_DEVICES = re.compile("Continue without microphone and camera", re.I)
_JOIN_BUTTON_TEXTS = ["Ask to join", "Join now"]
_NAME_INPUT = 'input[type="text"]'
_ADMITTED_SELECTOR = 'button[aria-label^="Leave call"]'
_CANT_JOIN_TEXT = "You can't join this video call"
# ruang tunggu ("Ask to join" ditekan, belum diizinkan) juga punya tombol berlabel "Leave call", jadi
# _ADMITTED_SELECTOR saja bilang "sudah masuk" padahal masih menunggu. Teks ini juga harus sudah hilang (satu tes
# merekam 42 detik layar tunggu sebagai "sudah masuk")
_WAITING_TEXT = "Please wait until a meeting host brings you into the call"
_MAX_JOIN_ATTEMPTS = 3
# teks halaman huruf kecil untuk "panggilan sudah selesai untuk bot" dan "bot sendirian". Dari kata-kata Meet, belum
# dikonfirmasi di layar sungguhan (catatan sama di zoom.py), kalau meleset rekaman hanya jalan sampai batas waktunya
_ENDED_PHRASES = ("return to home screen", "you've been removed", "you left the meeting", "call has ended", "meeting has ended")
_ALONE_PHRASE = "you're the only one here"
_ADMIT_WAIT_SECONDS = 60


class GoogleMeetBot(MeetBotBase):
    def join(self) -> str:
        # Google memblokir loginnya kalau browser diotomasi, dengan stealth atau tidak, jadi bot tidak pernah login: orang
        # login sekali (bots/google_login.py, di luar Docker) dan sesi yang disimpan di GOOGLE_AUTH_STATE_PATH dimuat
        # ke browser baru setiap join. Satu container = satu akun
        auth_state_path = os.getenv("GOOGLE_AUTH_STATE_PATH", "auth/google.json")
        if not os.path.exists(auth_state_path):
            raise RuntimeError(
                f"No saved Google session at {auth_state_path} - run "
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
                    # tidak ada GPU di container, lihat launch() di zoom.py untuk alasan flag ini perlu
                    "--use-gl=angle",
                    "--use-angle=swiftshader",
                    "--enable-unsafe-swiftshader",
                ],
                ignore_default_args=["--mute-audio", "--enable-automation"],
            )
            context = browser.new_context(
                storage_state=auth_state_path, viewport={"width": 1280, "height": 720}, ignore_https_errors=True
            )

            # dua evasion ini dimatikan, seperti konfigurasi Meet di proyek referensi
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

            # try/finally: record() bisa melempar error di tengah rekaman, tanpa ini bot tetap tinggal di panggilan
            try:
                out_path = self.record()
            finally:
                browser.close()
            return out_path

    def meeting_state(self) -> str:
        text = self.page.locator("body").inner_text(timeout=2000).lower()
        if any(phrase in text for phrase in _ENDED_PHRASES):
            return "ended"
        if _ALONE_PHRASE in text:
            return "alone"
        return "active"

    def _attempt_join(self) -> bool:
        self.page.goto(self.url, wait_until="domcontentloaded")

        # modal izin perangkat ini muncul 2,5-4,5 detik setelah load, jadi ditunggu: cek is_visible() sekilas melewatkannya
        # dan kliknya, lalu form join tetap tertutup
        try:
            continue_btn = self.page.locator("button", has_text=_CONTINUE_WITHOUT_DEVICES).first
            continue_btn.wait_for(state="visible", timeout=8000)
            continue_btn.click()
            continue_btn.wait_for(state="hidden", timeout=5000)
        except Exception:
            pass

        # hanya untuk join sebagai tamu, akun yang login langsung ke layar pra-join
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
