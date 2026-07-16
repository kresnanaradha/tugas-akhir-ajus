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
  recorder.ondataavailable = async (e) => {
    if (!e.data.size) return;
    const buf = await e.data.arrayBuffer();
    const bytes = new Uint8Array(buf);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
    await window.sendChunk(secretId, btoa(binary));
  };
  recorder.start(2000);
  window.__notulisRecorder = { recorder, stream };
}
"""

_STOP_JS = """
() => new Promise((resolve) => {
  const r = window.__notulisRecorder;
  if (!r || r.recorder.state === 'inactive') { resolve(); return; }
  r.recorder.addEventListener('stop', () => resolve(), { once: true });
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

        self.page.expose_function("sendChunk", on_chunk)
        self.page.evaluate(_RECORD_JS, {"secretId": self.secret_id, "mimeType": self.MIME_TYPE})

        time.sleep(self.max_duration_min * 60)

        self.page.evaluate(_STOP_JS)
        # ponytail: final chunk relay isn't awaited past the stop event (no
        # chunkUploadChain like upstream). Small buffer covers it for POC durations;
        # if recordings get cut short, serialize on the JS side like upstream does.
        time.sleep(1)

        with open(out_path, "wb") as f:
            for chunk in self._chunks:
                f.write(chunk)

        return str(out_path)
