import time
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from .base import MeetBotBase

# alur join diadaptasi (disederhanakan) dari screenappai/meeting-bot (MIT), ZoomBot.ts. Langsung ke url web client
# (/wc/join/<id>) bukan /j/<id>: halaman itu mencoba membuka aplikasi native (zoommtg://), memunculkan dialog Chromium
# yang tidak bisa ditutup Playwright dan bisa menyalakan aplikasi Zoom asli di host


def _web_client_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.replace("/j/", "/wc/join/", 1)
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


# pengecekan bot dan form join sama-sama tidak stabil (lihat catatan Stealth di _attempt_join), Meet juga mencoba 3 kali
_MAX_JOIN_ATTEMPTS = 3
# frasa huruf kecil dari layar Zoom saat host mengakhiri rapat atau mengeluarkan bot. Dari kata-kata Zoom, belum
# dikonfirmasi di layar akhir sungguhan: kalau meleset rekaman hanya jalan sampai batas waktunya, jadi cek
# dan lengkapi daftar ini saat pertama dipakai
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
                    # tanpa --use-fake-ui-for-media-stream: di Linux flag itu merusak getDisplayMedia() dengan "NotReadableError: Could not
                    # start video source" (itu terjadi di setiap join Zoom, Meet tidak pernah punya flag-nya). Tidak perlu juga,
                    # permissions=[camera, microphone] di context sudah menyetujui izin itu. Kamera dan mic Zoom sendiri
                    # tetap bilang NotFoundError (tidak ada perangkat di container), toggle_off() menanganinya
                    "--auto-accept-this-tab-capture",
                    # --auto-accept-this-tab-capture saja mengambil tab yang punya fokus OS, dan bring_to_front() tidak
                    # merebut fokus sungguhan, jadi tetap menangkap seluruh desktop. Ini memilih tab lewat judul yang persis sama
                    # (record() mengisi document.title dengan secretId yang sama tepat sebelum menangkap)
                    f"--auto-select-tab-capture-source-by-title={self.secret_id}",
                    "--autoplay-policy=no-user-gesture-required",
                    # tidak ada GPU di container (tidak ada /dev/dri) dan Chrome tidak turun sendiri ke rendering software,
                    # yang merusak compositor tab: getDisplayMedia() gagal dengan "NotReadableError" dan WebGL tidak
                    # jalan. Rasterizer software Mesa ada di image, flag ini membuat Chrome memakainya
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

            # web client biasanya menanyakan cara bergabung ke audio
            try:
                self.page.locator("button", has_text="Join Audio by Computer").first.click(timeout=8000)
            except Exception:
                pass

            # try/finally: record() bisa melempar error (seperti "NotReadableError" dari getDisplayMedia), tanpa ini bot
            # tetap tinggal di panggilan
            try:
                out_path = self.record()
            finally:
                # klik Leave, bukan menutup browser: terputus mendadak membuat bot tetap di panggilan sampai timeout
                # Zoom menyadarinya
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
        """Satu percobaan di context dan halaman baru. Kalau gagal context ditutup (supaya percobaan ulang mulai bersih) dan
        RuntimeError dilempar, kalau berhasil self.page adalah halaman yang sudah masuk."""
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True,
            permissions=["camera", "microphone"],
        )
        # tanpa ini web client melihat navigator.webdriver dan menolak dengan "Automated bots aren't allowed".
        # Proyek referensi membiarkan chrome.runtime ditambal, tapi port Python ini membuat chrome_runtime mati secara default,
        # kemungkinan alasan pengecekan bot lolos di beberapa percobaan dan tidak di yang lain
        Stealth(iframe_content_window=False, media_codecs=False, chrome_runtime=True).apply_stealth_sync(context)
        self.page = context.new_page()
        # diagnostik, murah dipertahankan: kalau "Target page, context or browser has been closed" muncul lagi, salah satunya menjelaskan sebabnya
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

            # meetingbot/meetingbot (MIT) menemukan toggle mute/video tidak andal diklik tepat setelah
            # input muncul, jadi tunggu 6 detik dan pakai selector ID (lebih kokoh dari teks) dengan cadangan teks
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

            # perangkat mic/kamera bisa lebih lama dari tombolnya, jadi klik mendarat sebelum toggle tersambung.
            # Cek aria-label (berubah setelah mati), coba sekali lagi, dan cetak kalau masih belum mati supaya join yang
            # berakhir dengan kamera menyala terlihat di log
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
