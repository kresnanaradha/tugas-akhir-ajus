import base64
import os
import threading
import time
import uuid
from pathlib import Path

from . import audio_backup

# getDisplayMedia + MediaRecorder + fungsi yang meneruskan potongan data, diadaptasi dari screenappai/meeting-bot
# (lisensi MIT), RecordingTask.ts
_RECORD_JS = """
async ({ secretId, mimeType }) => {
  // harus sama dengan --auto-select-tab-capture-source-by-title (bot Zoom mengisi flag itu dengan secretId) supaya
  // Chromium memilih tab ini lewat judul, bukan jendela mana pun yang sedang fokus
  document.title = secretId;
  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: true,
    audio: { autoGainControl: false, echoCancellation: false, noiseSuppression: false },
    preferCurrentTab: true,
  });
  console.log('[notulis] got stream, tracks:', stream.getTracks().map((t) => `${t.kind}:${t.readyState}:${t.enabled}`).join(','));
  const recorder = new MediaRecorder(stream, { mimeType });
  recorder.addEventListener('error', (e) => console.error('[notulis] MediaRecorder error:', e.error));
  // unggahan potongan lewat rantai promise supaya pengiriman yang lambat tidak menimpa potongan 2 detik berikutnya
  let chunkChain = Promise.resolve();
  recorder.ondataavailable = (e) => {
    if (!e.data.size) return;
    const blob = e.data;
    chunkChain = chunkChain.then(async () => {
      try {
        const buf = await blob.arrayBuffer();
        // bukan TextDecoder('latin1'): itu windows-1252, byte 0x80-0x9F didecode di atas 255 dan btoa() menolaknya.
        // String.fromCharCode memetakan 0-255 dengan tepat, per batch supaya alokasinya sedikit
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
  // pengawas hening: kapan terakhir audio terdengar, supaya bot bisa berhenti setelah lama sepi. AudioContext
  // yang tertahan dianggap ada suara, jadi kegagalan di sini tidak bisa memotong rekaman
  window.__notulisLastSound = Date.now();
  const track = stream.getAudioTracks()[0];
  if (track) {
    // hanya kerasnya suara yang penting: sample rate rendah dan buffer besar supaya ini tidak berebut CPU dengan
    // perekam (sampel yang hilang terdengar seperti gemeretak)
    const ctx = new AudioContext({ sampleRate: 8000, latencyHint: 'playback' });
    const analyser = ctx.createAnalyser();
    ctx.createMediaStreamSource(new MediaStream([track])).connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    setInterval(() => {
      if (ctx.state !== 'running') { ctx.resume(); window.__notulisLastSound = Date.now(); return; }
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
      if (Math.sqrt(sum / buf.length) > 0.003) window.__notulisLastSound = Date.now();
    }, 1000);
  }
  recorder.start(2000);
  window.__notulisRecorder = { recorder, stream, getChunkChain: () => chunkChain };
}
"""

_STOP_JS = """
() => new Promise((resolve) => {
  const r = window.__notulisRecorder;
  if (!r || r.recorder.state === 'inactive') { resolve(); return; }
  r.recorder.addEventListener('stop', async () => {
    // tunggu unggahan potongan yang masih berjalan
    await r.getChunkChain();
    resolve();
  }, { once: true });
  r.recorder.stop();
  r.stream.getTracks().forEach(t => t.stop());
})
"""


_STATE_CHECK_EVERY_S = 3
# berhenti setelah selama ini sendirian di rapat (EMPTY_MEETING_MINUTES di .env, 0 = mati). Mendeteksi
# rapat berakhir selalu menyala
_ALONE_STOP_S = float(os.getenv("EMPTY_MEETING_MINUTES", "10")) * 60 or float("inf")
# berhenti setelah selama ini tanpa suara terdengar (SILENCE_MINUTES di .env, 0 = mati)
_SILENCE_STOP_S = float(os.getenv("SILENCE_MINUTES", "30")) * 60 or float("inf")


class MeetBotBase:
    """Bot dasar. Pola join diadaptasi dari screenappai/meeting-bot (MIT)."""

    # mp4 (H.264) pernah dicoba lalu dikembalikan: Chromium milik Playwright tidak punya encoder H.264, jadi MediaRecorder
    # melempar NotSupportedError
    MIME_TYPE = "video/webm;codecs=vp8,opus"

    def __init__(self, url: str, name: str, max_duration_min: float | None, on_status_change=None):
        self.url = url
        self.name = name
        self.max_duration_min = max_duration_min
        self.secret_id = uuid.uuid4().hex
        self.page = None
        self._chunk_count = 0
        # dibaca endpoint job untuk progres langsung, tombol Stop mengatur stop_event
        self.status = "joining"  # joining -> recording -> stopping
        self.record_started_at: float | None = None
        self.record_ended_at: float | None = None
        self.stop_event = threading.Event()
        # callback(status): menyimpan tiap perubahan status ke baris rapat supaya daftar menampilkan "sedang merekam" secara langsung
        self._on_status_change = on_status_change

    def _set_status(self, status: str) -> None:
        self.status = status
        if self._on_status_change:
            try:
                self._on_status_change(status)
            except Exception as e:
                # gangguan db tidak boleh menjatuhkan rekaman
                print(f"[status] on_status_change callback failed: {e}")

    def join(self) -> str:
        raise NotImplementedError

    def _silent_for(self) -> float:
        # Detik sejak halaman terakhir mendengar audio; 0 kalau tidak bisa dibaca.
        try:
            v = self.page.evaluate("() => (Date.now() - window.__notulisLastSound) / 1000")
            return v if isinstance(v, (int, float)) else 0.0
        except Exception:
            return 0.0

    def meeting_state(self) -> str:
        """Salah satu dari "active", "ended" (host mengakhiri atau bot dikeluarkan) atau "alone" (tinggal bot).
        Subkelas membaca teks halaman platform-nya, default-nya tidak pernah mengakhiri rekaman lebih awal."""
        return "active"

    def _safe_meeting_state(self) -> str:
        # pembacaan halaman yang goyah tidak boleh mengakhiri atau menjatuhkan rekaman
        try:
            return self.meeting_state()
        except Exception:
            return "active"

    def record(self) -> str:
        out_dir = Path(os.getenv("RECORDINGS_DIR", "recordings")) / "videos"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{self.__class__.__name__}_{int(time.time())}.webm"

        # potongan langsung ditulis ke disk begitu datang (~4,5 MB per menit, ~550 MB untuk 2 jam), jadi kalau crash
        # yang sudah terekam tetap ada
        out_file = open(out_path, "wb")
        backup = None  # rekaman samping PulseAudio, lihat audio_backup.py

        def on_chunk(secret_id: str, b64data: str):
            if secret_id != self.secret_id or out_file.closed:
                return
            out_file.write(base64.b64decode(b64data))
            out_file.flush()
            self._chunk_count += 1

        try:
            self.page.expose_function("sendChunk", on_chunk)
            # flag judul seharusnya membuat Chromium memilih tab ini apa pun fokusnya, tapi pernah tetap menangkap
            # seluruh desktop, jadi jendelanya juga diberi fokus sungguhan
            self.page.bring_to_front()
            self.page.mouse.click(5, 5)
            self.page.wait_for_timeout(300)
            backup = audio_backup.start(out_path.with_suffix(".backup.ogg"))
            self.page.evaluate(_RECORD_JS, {"secretId": self.secret_id, "mimeType": self.MIME_TYPE})

            self._set_status("recording")
            self.record_started_at = time.time()
            deadline = self.record_started_at + self.max_duration_min * 60 if self.max_duration_min else float("inf")
            # tidur sedikit-sedikit supaya permintaan stop (thread lain mengisi stop_event) memotong rekaman
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
                # "ended" harus muncul dua kali berturut-turut supaya satu layar sesaat (banner menyambung ulang) tidak memotong rekaman
                ended_hits = ended_hits + 1 if state == "ended" else 0
                if ended_hits >= 2:
                    print("[record] meeting ended, stopping early")
                    break
                # sendirian baru dihitung setelah waktu lama, bot biasanya masuk sebelum orang-orangnya
                alone_since = (alone_since or now) if state == "alone" else None
                if alone_since and now - alone_since >= _ALONE_STOP_S:
                    print(f"[record] alone in the meeting for {int(now - alone_since)}s, stopping early")
                    break
                silent_for = self._silent_for()
                if silent_for >= _SILENCE_STOP_S:
                    print(f"[record] no sound for {int(silent_for)}s, stopping early")
                    break
            else:
                if not self.stop_event.is_set():
                    print(f"[record] time cap of {self.max_duration_min} min reached, stopping")

            self.record_ended_at = time.time()
            self._set_status("stopping")
            self.page.evaluate(_STOP_JS)
        finally:
            print(f"[record] {self._chunk_count} chunks received")
            out_file.close()
            try:
                audio_backup.finish(backup, out_path, self.record_started_at)
            except Exception as e:  # perbaikan tidak boleh menjatuhkan rekaman yang sudah selesai
                print(f"[audio_backup] unexpected error, original kept: {e}")

        return str(out_path)
