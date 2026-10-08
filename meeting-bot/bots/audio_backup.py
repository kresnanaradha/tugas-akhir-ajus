"""Backup audio capture straight from PulseAudio, used to repair a damaged recording.

Chrome's tab-capture audio drops samples when the browser is starved of CPU
(measured: 0-2 clicks/s when healthy, 14-24 clicks/s and 9% of the samples missing
on one 60-minute meeting, which sounds like a robot / broken radio). Reading the same
sound from the PulseAudio sink with ffmpeg is ~5x cleaner under the same load.

So while recording, ffmpeg also writes the sink's monitor to a side file. When the
recording is finished and Chrome's audio turns out to be incomplete, the side file
replaces the audio track (video is copied untouched). A healthy recording is never
modified, and every failure here leaves the original recording as it was.
"""

import os
import shutil
import subprocess
import time
from pathlib import Path

SOURCE = os.getenv("BACKUP_AUDIO_SOURCE", "DummyOutput.monitor")
# Replace Chrome's audio when less than this share of the recording's time is audio.
# Strict on purpose: the missing share is also the audio/video drift (0.8% missing =
# 0.7 s out of sync after 100 s, half a minute after an hour). Healthy recordings measure 100.0%.
MIN_COMPLETE = float(os.getenv("BACKUP_AUDIO_MIN_COMPLETE", "99.9"))


def start(path: Path):
    """Starts ffmpeg writing the sink monitor to `path` (.ogg). Returns a handle, or
    None when this machine has no PulseAudio / ffmpeg (e.g. a bare-metal dev run)."""
    if not shutil.which("ffmpeg"):
        return None
    try:
        proc = subprocess.Popen(
            [
                "ffmpeg", "-v", "error", "-y",
                "-f", "pulse", "-use_wallclock_as_timestamps", "1", "-i", SOURCE,
                # wall-clock stamps + padding: silence while the sink sleeps stays silence
                # instead of shortening the file
                "-af", "aresample=async=1000:first_pts=0",
                "-ac", "1", "-ar", "48000", "-c:a", "libopus", "-b:a", "48k", str(path),
            ],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        started_at = time.time()
        time.sleep(1.0)
        if proc.poll() is not None:
            print(f"[audio_backup] ffmpeg exited at start: {proc.stderr.read().decode(errors='replace')[-200:]}")
            return None
        return {"proc": proc, "path": path, "started_at": started_at}
    except Exception as e:
        print(f"[audio_backup] could not start: {e}")
        return None


def _stop(handle) -> None:
    proc = handle["proc"]
    try:
        proc.stdin.write(b"q")
        proc.stdin.flush()
        proc.wait(timeout=20)
    except Exception:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def _decode(path, seconds, rate=8000, fill_gaps=False):
    import numpy as np

    af = ["-af", "aresample=async=1:first_pts=0"] if fill_gaps else []
    raw = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-vn", *af, "-ac", "1", "-ar", str(rate), "-t", str(seconds), "-f", "s16le", "-"],
        capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768


def completeness(path) -> float | None:
    """Percent of the file's audio timeline that is audio (100 = no samples missing)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "packet=pts_time,duration_time", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.splitlines()
    packets = sorted((float(a), float(b)) for a, b in (ln.split(",")[:2] for ln in out if "," in ln) if a and b)
    if len(packets) < 10:
        return None
    span = packets[-1][0] + packets[-1][1] - packets[0][0]
    return 100 * sum(d for _, d in packets) / span if span > 0 else None


def _offset(video_path, backup_path, expected: float) -> tuple[float, bool]:
    """Seconds by which the backup audio starts after the video's t=0, found by
    matching the two audios around `expected` (the difference of their start times).
    Returns (offset, found); not found keeps `expected`."""
    import numpy as np

    rate, win = 8000, 40
    chrome = _decode(video_path, 150, rate, fill_gaps=True)
    pulse = _decode(backup_path, 150, rate)
    if len(chrome) < win * rate or len(pulse) < win * rate:
        return expected, False
    # the loudest `win` seconds of the first minutes carry the most to match on
    hop = rate * 5
    starts = range(0, len(chrome) - win * rate + 1, hop)
    s = max(starts, key=lambda i: float(np.sqrt((chrome[i:i + win * rate] ** 2).mean())))
    seg = chrome[s:s + win * rate]
    if float(np.sqrt((seg ** 2).mean())) < 0.005:
        return expected, False
    # where the backup audio must be: expected +-3 s
    a0 = max(int((s / rate - (expected + 3)) * rate), 0)
    a1 = int((s / rate - (expected - 3)) * rate) + len(seg)
    region = pulse[a0:a1]
    if len(region) <= len(seg):
        return expected, False

    def best_match(x, y, min_score):
        """Index k where x (short) best matches y[k:], by normalised cross-correlation."""
        n = 1 << (len(y) + len(x)).bit_length()
        corr = np.fft.irfft(np.fft.rfft(y, n) * np.conj(np.fft.rfft(x, n)), n)[: len(y) - len(x) + 1]
        energy = np.concatenate(([0.0], np.cumsum(y.astype(np.float64) ** 2)))
        local = np.sqrt(energy[len(x):len(x) + len(corr)] - energy[: len(corr)]) + 1e-9
        score = corr / (local * (np.linalg.norm(x) + 1e-9))
        k = int(np.argmax(score))
        return (k, True) if score[k] >= min_score and score[k] >= 4 * float(np.std(score)) else (k, False)

    # 1) the waveforms themselves (sample accurate when Chrome's audio is healthy)
    k, ok = best_match(seg, region, 0.2)
    if ok:
        return s / rate - (a0 + k) / rate, True
    # 2) Chrome's audio is damaged, so match the volume envelope (10 ms steps) instead
    blk = rate // 100

    def envelope(v):
        v = np.abs(v)
        v = v[: len(v) // blk * blk].reshape(-1, blk).mean(axis=1)
        return v - v.mean()

    e_seg, e_region = envelope(seg), envelope(region)
    k, ok = best_match(e_seg, e_region, 0.3)
    if ok:
        return s / rate - (a0 + k * blk) / rate, True
    return expected, False


def finish(handle, video_path: Path, video_started_at: float | None) -> None:
    """Stops the side capture and, if Chrome's audio is incomplete, swaps it in."""
    if not handle:
        return
    _stop(handle)
    try:
        backup = handle["path"]
        done = completeness(video_path)
        if done is None or done >= MIN_COMPLETE:
            return
        if not backup.exists() or backup.stat().st_size < 4096:
            print(f"[audio_backup] recording is {done:.1f}% complete but there is no backup audio to use")
            return
        expected = handle["started_at"] - (video_started_at or handle["started_at"])
        offset, found = _offset(video_path, backup, expected)
        fixed = video_path.with_suffix(".fixed.webm")
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(video_path)]
        cmd += ["-itsoffset", f"{offset:.3f}", "-i", str(backup)] if offset >= 0 else ["-ss", f"{-offset:.3f}", "-i", str(backup)]
        cmd += ["-map", "0:v:0", "-map", "1:a:0", "-c", "copy", str(fixed)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=600)
        if not fixed.exists() or fixed.stat().st_size < 0.5 * video_path.stat().st_size:
            raise RuntimeError("repaired file is missing or far too small")
        os.replace(fixed, video_path)
        print(f"[audio_backup] chrome audio was {done:.1f}% complete; replaced with PulseAudio capture (offset {offset:+.2f}s, {'matched' if found else 'estimated'})")
    except Exception as e:
        print(f"[audio_backup] repair skipped, original kept: {e}")
    finally:
        try:
            if not os.getenv("BACKUP_AUDIO_KEEP"):  # debugging aid
                handle["path"].unlink(missing_ok=True)
        except Exception:
            pass
