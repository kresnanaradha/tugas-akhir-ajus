import base64
import os
import threading
import time
import uuid
from pathlib import Path

# Recording pattern (getDisplayMedia + MediaRecorder + exposed function chunk
# relay) adapted from screenappai/meeting-bot (MIT license), src/tasks/RecordingTask.ts.
_RECORD_JS = """
async ({ secretId, mimeType }) => {
  // Must match --auto-select-tab-capture-source-by-title exactly (Zoom bot
  // sets that flag to secretId) so Chromium picks this tab by title instead
  // of whichever window happens to have OS focus.
  document.title = secretId;
  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: true,
    audio: { autoGainControl: false, echoCancellation: false, noiseSuppression: false },
    preferCurrentTab: true,
  });
  console.log('[notulis] got stream, tracks:', stream.getTracks().map((t) => `${t.kind}:${t.readyState}:${t.enabled}`).join(','));
  const recorder = new MediaRecorder(stream, { mimeType });
  recorder.addEventListener('error', (e) => console.error('[notulis] MediaRecorder error:', e.error));
  // Reference project (RecordingTask.ts) serializes chunk uploads through a
  // promise chain instead of firing sendChunk from each ondataavailable
  // independently. Without that, a slow send for one chunk can still be
  // in flight when the next 2-second chunk arrives — concurrent overlapping
  // calls through the same exposed function, which real (not fake-camera-
  // sized) chunks made likely.
  let chunkChain = Promise.resolve();
  recorder.ondataavailable = (e) => {
    if (!e.data.size) return;
    const blob = e.data;
    chunkChain = chunkChain.then(async () => {
      try {
        const buf = await blob.arrayBuffer();
        // TextDecoder('latin1') is a WHATWG alias for windows-1252, not true
        // byte-for-byte ISO-8859-1 — bytes 0x80-0x9F decode to codepoints
        // above 255 (curly quotes etc.), which btoa() then rejects. Binary
        // video/audio data hits that range constantly. String.fromCharCode
        // maps bytes 0-255 to codepoints 0-255 exactly, so it's correct;
        // batching avoids the call/allocation overhead of doing it one byte
        // at a time.
        const bytes = new Uint8Array(buf);
        let binary = '';
        const CHUNK = 0x8000;
        for (let i = 0; i < bytes.length; i += CHUNK) {
          binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
        }
        await window.sendChunk(secretId, btoa(binary));
      } catch (err) {
        console.error('[notulis] sendChunk failed:', err);
      }
    });
  };
  recorder.start(2000);
  window.__notulisRecorder = { recorder, stream, getChunkChain: () => chunkChain };
}
"""

_STOP_JS = """
() => new Promise((resolve) => {
  const r = window.__notulisRecorder;
  if (!r || r.recorder.state === 'inactive') { resolve(); return; }
  r.recorder.addEventListener('stop', async () => {
    // Wait for any still-in-flight chunk uploads to finish before returning,
    // same as reference's `await chunkUploadChain` after recorder.stop().
    await r.getChunkChain();
    resolve();
  }, { once: true });
  r.recorder.stop();
  r.stream.getTracks().forEach(t => t.stop());
})
"""


_STATE_CHECK_EVERY_S = 3
# Stop after this long as the only participant (EMPTY_MEETING_MINUTES in .env;
# 0 turns the alone check off). Ended-meeting detection is separate and always on.
_ALONE_STOP_S = float(os.getenv("EMPTY_MEETING_MINUTES", "10")) * 60 or float("inf")


class MeetBotBase:
    """Base bot. join-flow patterns adapted from screenappai/meeting-bot (MIT)."""

    # mp4 (H.264) was tried and reverted — Playwright's Chromium (Chrome for
    # Testing) ships without the proprietary H.264 encoder (licensing), so
    # MediaRecorder throws NotSupportedError there even though a regular
    # Chrome install can record it fine. Getting mp4 out would need an
    # ffmpeg re-encode pass after recording — not worth it for a POC.
    MIME_TYPE = "video/webm;codecs=vp8,opus"

    def __init__(self, url: str, name: str, max_duration_min: float, on_status_change=None):
        self.url = url
        self.name = name
        self.max_duration_min = max_duration_min
        self.secret_id = uuid.uuid4().hex
        self.page = None
        self._chunks = []
        # Exposed so app.py's job endpoints can report live progress and let
        # the frontend stop a recording early — see record() below.
        self.status = "joining"  # joining -> recording -> stopping
        self.record_started_at: float | None = None
        self.record_ended_at: float | None = None
        self.stop_event = threading.Event()
        # Optional callback(status: str) — app.py wires this to persist each
        # transition to the meetings table (see pipeline/meetings_store.py's
        # update_meeting()), so the Rapat list reflects "sedang merekam" live
        # instead of only ever showing the finished result.
        self._on_status_change = on_status_change

    def _set_status(self, status: str) -> None:
        self.status = status
        if self._on_status_change:
            try:
                self._on_status_change(status)
            except Exception as e:
                # A DB hiccup here should never take down an in-progress
                # recording — worst case the list's status lags reality.
                print(f"[status] on_status_change callback failed: {e}")

    def join(self) -> str:
        raise NotImplementedError

    def meeting_state(self) -> str:
        """"active", "ended" (host ended it / bot was removed) or "alone" (the
        bot is the only participant left). Subclasses read the platform's own
        page text; the default never ends a recording early, same as before
        this hook existed."""
        return "active"

    def _safe_meeting_state(self) -> str:
        # A flaky page read must never end (or crash) a recording by itself.
        try:
            return self.meeting_state()
        except Exception:
            return "active"

    def record(self) -> str:
        out_dir = Path(os.getenv("RECORDINGS_DIR", "recordings")) / "videos"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{self.__class__.__name__}_{int(time.time())}.webm"

        def on_chunk(secret_id: str, b64data: str):
            if secret_id != self.secret_id:
                return
            self._chunks.append(base64.b64decode(b64data))

        try:
            self.page.expose_function("sendChunk", on_chunk)
            # Belt and suspenders: the title-select flag should make Chromium
            # pick this exact tab regardless of focus, but it still captured
            # the whole desktop once even with that in place — so also try to
            # give this window real focus the way --auto-accept-this-tab-capture
            # wants it, in case the two mechanisms interact.
            self.page.bring_to_front()
            self.page.mouse.click(5, 5)
            self.page.wait_for_timeout(300)
            self.page.evaluate(_RECORD_JS, {"secretId": self.secret_id, "mimeType": self.MIME_TYPE})

            self._set_status("recording")
            self.record_started_at = time.time()
            deadline = self.record_started_at + self.max_duration_min * 60
            # Sleep in small steps instead of one blind sleep() so a stop
            # request (app.py's POST /jobs/<id>/stop, setting stop_event from
            # a different thread) actually cuts the recording short instead
            # of only taking effect after the full max duration anyway.
            last_check = 0.0
            ended_hits = 0
            alone_since = None
            while time.time() < deadline and not self.stop_event.is_set():
                time.sleep(1)
                now = time.time()
                if now - last_check < _STATE_CHECK_EVERY_S:
                    continue
                last_check = now
                state = self._safe_meeting_state()
                # "ended" must show up twice in a row before it counts, so one
                # transient screen (a reconnect banner) can't cut a recording.
                ended_hits = ended_hits + 1 if state == "ended" else 0
                if ended_hits >= 2:
                    print("[record] meeting ended, stopping early")
                    break
                # Alone only counts after a long stretch: the bot normally
                # joins before the people do, so "alone" is the expected
                # state at the start of most meetings.
                alone_since = (alone_since or now) if state == "alone" else None
                if alone_since and now - alone_since >= _ALONE_STOP_S:
                    print(f"[record] alone in the meeting for {int(now - alone_since)}s, stopping early")
                    break

            self.record_ended_at = time.time()
            self._set_status("stopping")
            self.page.evaluate(_STOP_JS)
        finally:
            print(f"[record] {len(self._chunks)} chunks received")
            # Save whatever chunks made it through even if the page/browser
            # crashes mid-recording, instead of losing the whole clip.
            with open(out_path, "wb") as f:
                for chunk in self._chunks:
                    f.write(chunk)

        return str(out_path)
