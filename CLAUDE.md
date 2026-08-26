# Notulis — Meeting Bot

POC bot that joins a Google Meet or Zoom call as a guest, records the tab
(video+audio), transcribes it (with speaker labels), and produces an AI
summary. Flask + Playwright + whisperx + GPT-4o mini. Join-flow adapted from
[screenappai/meeting-bot](https://github.com/screenappai/meeting-bot) (MIT).

Full setup/run/test instructions: `meeting-bot/README.md`. This file is
project status — what's done, what's next, what to watch out for.

## Repo state

- `reference/` (a local clone of screenappai/meeting-bot, kept for reading
  their implementation) is gitignored, not committed — it's a reference
  clone, not part of the shipped bot.

## What's built

- `app.py` — Flask app, two endpoints: `POST /google/join`, `POST
  /zoom/join`. Each blocks until the bot leaves the meeting, then runs
  transcription and summarization, and returns everything in one response.
  Each step's failure is reported independently (`transcript_error`,
  `fix_transcript_error`, `summary_error`) rather than failing the whole
  request — a bad summary shouldn't erase a recording that's already on
  disk.
- `bots/base.py` — shared recording logic: injects a `getDisplayMedia` +
  `MediaRecorder` script into the joined page, relays chunks back to Python
  via an exposed function, writes them to `recordings/videos/`.
- `bots/google_meet.py` — Google Meet join flow (CDP-attached signed-in
  sidecar Chrome).
- `bots/zoom.py` — Zoom join flow (anonymous guest, direct web-client URL +
  stealth patch).
- `transcribe.py` — transcription via `whisperx` (local, no API cost): a
  faster-whisper backend, word-alignment, and pyannote diarization, producing
  a `[SPEAKER_NN] ...`-labeled transcript per line. Saves to
  `recordings/transcripts/`.
- `summarize.py` — two GPT-4o mini passes: `fix_transcript()` corrects likely
  ASR mistakes and collapses hallucinated repeated closing lines (saves to
  `recordings/fixed_transcripts/`), then `summarize()` produces
  `{executive_summary, key_decisions, topics_discussed}` JSON (saves to
  `recordings/summaries/`) per Table 2 of the proposal.
- `paths.py` — `sibling_path()`: given a video path like
  `recordings/videos/Foo_123.webm`, resolves the matching file in a sibling
  type folder (`recordings/transcripts/Foo_123.txt` etc.), creating it if
  needed. All three output stages use this so everything for one meeting
  shares a filename stem across `videos/`, `transcripts/`,
  `fixed_transcripts/`, and `summaries/`.

## Status per platform

- **Google Meet: working, tested**, full pipeline (join → record →
  transcribe → fix → summarize, with diarization) confirmed end-to-end.
  Google blocks anonymous automated joins and blocks a Playwright-driven
  login regardless of stealth patches, so the bot never logs in itself: a
  human signs into a dedicated Chrome sidecar (`--remote-debugging-port=9222`),
  and the bot attaches to that already-authenticated session over CDP. That
  sidecar must be launched with `--auto-accept-this-tab-capture` too (added
  to the launch command in README) — without it, every recording pauses on a
  manual "Allow this tab to be seen?" permission dialog since the sidecar
  isn't a Playwright-launched browser and doesn't inherit any args from
  `zoom.py`'s `launch()` call.
- **Zoom: working, tested end-to-end** for join + record. Transcribe/
  summarize reuse the exact same functions Google Meet already confirmed
  working, but haven't been separately re-verified through a live Zoom run
  yet — do that before assuming it's covered. Navigates straight to the
  embedded web-client URL (`/wc/join/<id>` instead of `/j/<id>`) to skip the
  app-chooser landing page entirely — that page auto-attempts a
  `zoommtg://` native-app launch, which pops an unclosable-by-Playwright
  Chromium dialog. `playwright-stealth` (with `chrome_runtime` explicitly
  turned on — this port defaults it off, unlike the upstream
  puppeteer-extra-plugin-stealth the reference project uses) gets past
  Zoom's "Automated bots aren't allowed" check, though not with 100%
  reliability — repeated automated joins against the same meeting/IP in a
  short window seem to raise Zoom's suspicion regardless of stealth quality;
  space out test runs if it starts failing again.

## Transcription/summarization notes

- **Diarization needs a HuggingFace token with model access**, not just a
  token. `HF_TOKEN` (Read-Only scope is enough) alone 403s — you also have to
  visit https://huggingface.co/pyannote/speaker-diarization-community-1 while
  logged in and accept its terms once. Symptom if this hasn't been done:
  `GatedRepoError` on the first diarization call.
- **`num_speakers` matters a lot.** Diarization clustering guesses the
  speaker count when it isn't given, which reliably under-segments — on a
  real 4-speaker test clip, unhinted diarization only found 2 speakers;
  passing `num_speakers=4` found 3. `transcribe()` takes an optional
  `num_speakers` param for this; nothing currently passes it through from
  the join endpoints (the real speaker count would need to come from the
  meeting platform's participant count, not guessed).
- **Runs on CPU** (no GPU on the dev machine) via `compute_type="int8"` —
  reasonably fast for `WHISPER_MODEL=medium`; `large-v3` needs ~8-10GB RAM to
  even load and is impractical without a GPU, don't reach for it by default.
- The `fix_transcript()` prompt has to be told explicitly to only collapse
  *literally repeated* trailing phrases — an earlier looser version ("remove
  trailing filler/closing phrases") over-trimmed and deleted real closing
  sentences that just happened to sound like a sign-off. If summaries ever
  seem to be missing content from the end of a meeting, check this first.
- Whisper mishears this project's own vocabulary without help — "taun
  skripsi" instead of "transkripsi" was a recurring one. Two things fixed it:
  Whisper's `initial_prompt` (in `transcribe.py`) and an explicit term list
  in `fix_transcript()`'s system prompt (in `summarize.py`). Extend both if
  new domain terms start getting mangled.

### Known accepted limitation

Recording captures the whole screen, not just the meeting tab, in local dev.
Tab-only capture needs the joined page to have real OS-level window focus at
the moment `getDisplayMedia()` fires; `page.bring_to_front()` only switches
Playwright's active tab, not actual OS window focus, so it doesn't reliably
beat out whatever else has focus (e.g. the terminal that fired the join
request). Chromium's `--auto-select-tab-capture-source-by-title` flag (used
to pick the tab by exact title match instead of focus) didn't fix it either
when tried. Decided not to chase this further: on a real deployment the
browser runs in an isolated display (Xvfb/Docker) with nothing else on
screen, so "whole screen" and "just the tab" end up being the same capture
either way — this only looks bad in local dev with other windows open.
`puppeteer-stream` (an npm library some other meeting-bot projects use)
solves this properly via a `chrome.tabCapture`-based extension instead of
`getDisplayMedia()`, which is deterministic regardless of focus — worth
considering if this ever needs revisiting for real, but it's a Node-only
library and would mean either porting to Node or hand-rolling an equivalent
extension.

### Playwright version pin

`requirements.txt` pins `playwright>=1.60.0`. Below that version, Chrome for
Testing crashes when stopping a `getDisplayMedia` stream's tracks
(`stream.getTracks().forEach(t => t.stop())` —
[microsoft/playwright#39158](https://github.com/microsoft/playwright/issues/39158)),
which is exactly what `base.py`'s `_STOP_JS` does on every recording. This
silently killed the browser mid-session with no crash dump and no
Playwright-visible crash/close event — if a recording ever dies again with
"Target page, context or browser has been closed" and no diagnostic output,
check this hasn't regressed (e.g. from a `pip install` that ignores the
pin) before spending hours re-debugging it like this session did.

## Next steps

1. Verify the transcribe/summarize pipeline through a live Zoom run (only
   Google Meet has been confirmed end-to-end so far).
2. Upload Audio: a cheap next feature since `transcribe()`/`summarize()`
   already work on any audio/video file path, not just bot output — mostly
   just a new upload endpoint reusing them.
3. Wire real participant count into `transcribe()`'s `num_speakers` param
   instead of leaving diarization to guess.
4. Known POC gaps, not started (see README "Not handled yet" for the full
   list): one meeting at a time (Playwright runs sync in the request
   thread), no retry beyond a single 60s admission wait, no auth on the
   endpoints, no inactivity detection (recording always runs the full
   `MAX_RECORDING_DURATION_MINUTES`), no mute/stop-video equivalent gap on
   Google Meet's side (only Zoom's join flow does this).
5. Eventually: move off blocking-HTTP-per-request toward the proposal's
   actual architecture (Redis job queue, S3 upload instead of local disk,
   auth between the main Notulis backend and this service). Deliberately not
   started yet — not worth the infra investment until the full pipeline
   (which just got proven out today) had a chance to be validated first.

## To resume on another machine

```bash
cd meeting-bot
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Fill in `.env`: `OPENAI_API_KEY` (AI summarization/transcript-fix, GPT-4o
mini) and `HF_TOKEN` (diarization — remember this also needs accepting the
pyannote model's terms on HuggingFace once, a token alone isn't enough; see
"Transcription/summarization notes" above).

For Google Meet, also start the signed-in Chrome sidecar (README has the
exact command, including `--auto-accept-this-tab-capture` — and a warning to
use a separate Google account, not your personal one). Zoom needs no extra
setup.
