import base64
import os
import time
import uuid
from pathlib import Path

# Recording pattern (getDisplayMedia + MediaRecorder + exposed function chunk
# relay) adapted from screenappai/meeting-bot (MIT license), src/tasks/RecordingTask.ts.
_RECORD_JS = """
async ({ secretId, mimeType }) => {
  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: true,
    audio: { autoGainControl: false, echoCancellation: false, noiseSuppression: false },
    preferCurrentTab: true,
  });
  const recorder = new MediaRecorder(stream, { mimeType });
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
        const binary = new TextDecoder('latin1').decode(buf);
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


class MeetBotBase:
    """Base bot. join-flow patterns adapted from screenappai/meeting-bot (MIT)."""

    MIME_TYPE = "video/webm;codecs=vp8,opus"

    def __init__(self, url: str, name: str, max_duration_min: float):
        self.url = url
        self.name = name
        self.max_duration_min = max_duration_min
        self.secret_id = uuid.uuid4().hex
        self.page = None
        self._chunks = []

    def join(self) -> str:
        raise NotImplementedError

    def record(self) -> str:
        out_dir = Path(os.getenv("RECORDINGS_DIR", "recordings"))
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"{self.__class__.__name__}_{int(time.time())}.webm"

        def on_chunk(secret_id: str, b64data: str):
            if secret_id != self.secret_id:
                return
            self._chunks.append(base64.b64decode(b64data))
            print(f"[record] chunk received, total so far: {len(self._chunks)}")

        try:
            self.page.expose_function("sendChunk", on_chunk)
            # No bring_to_front(): it scopes getDisplayMedia's auto-accept
            # down to just this tab instead of the whole desktop, but every
            # test with it enabled had the browser die outright mid-recording
            # for reasons that resisted diagnosis. Without it, recording
            # captures the whole desktop (over-broad, but it reliably
            # finishes) — trading correctness for something that actually
            # works while that's investigated further.
            print("[record] calling evaluate(_RECORD_JS)...")
            self.page.evaluate(_RECORD_JS, {"secretId": self.secret_id, "mimeType": self.MIME_TYPE})
            print("[record] _RECORD_JS returned OK, recording started")

            time.sleep(self.max_duration_min * 60)
            print("[record] sleep done, calling evaluate(_STOP_JS)...")

            self.page.evaluate(_STOP_JS)
            print("[record] _STOP_JS returned OK")
            # ponytail: final chunk relay isn't awaited past the stop event (no
            # chunkUploadChain like upstream). Small buffer covers it for POC durations;
            # if recordings get cut short, serialize on the JS side like upstream does.
            time.sleep(1)
        finally:
            # Save whatever chunks made it through even if the page/browser
            # crashes mid-recording, instead of losing the whole clip.
            with open(out_path, "wb") as f:
                for chunk in self._chunks:
                    f.write(chunk)

        return str(out_path)
