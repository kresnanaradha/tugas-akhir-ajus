# Notulis — Meeting Bot

POC bot that joins a Google Meet or Zoom call as a guest, records the tab
(video+audio) via `MediaRecorder`, and saves it to `meeting-bot/recordings/`
as a `.webm` file. Flask + Playwright. Join-flow adapted from
[screenappai/meeting-bot](https://github.com/screenappai/meeting-bot) (MIT).

Full setup/run/test instructions: `meeting-bot/README.md`. This file is
project status — what's done, what's next, what to watch out for.

## Repo state

- `reference/` (a local clone of screenappai/meeting-bot, kept for reading
  their implementation) is gitignored, not committed — it's a reference
  clone, not part of the shipped bot.

## What's built

- `app.py` — Flask app, two endpoints: `POST /google/join`, `POST
  /zoom/join`. Each blocks until the bot leaves the meeting and returns the
  recording path (or a 500 with the error).
- `bots/base.py` — shared recording logic: injects a `getDisplayMedia` +
  `MediaRecorder` script into the joined page, relays chunks back to Python
  via an exposed function, writes them to `recordings/`.
- `bots/google_meet.py` — Google Meet join flow (CDP-attached signed-in
  sidecar Chrome).
- `bots/zoom.py` — Zoom join flow (anonymous guest, direct web-client URL +
  stealth patch).

## Status per platform

- **Google Meet: working, tested.** Google blocks anonymous automated joins
  and blocks a Playwright-driven login regardless of stealth patches, so the
  bot never logs in itself: a human signs into a dedicated Chrome sidecar
  (`--remote-debugging-port=9222`), and the bot attaches to that
  already-authenticated session over CDP. That sidecar must be launched with
  `--auto-accept-this-tab-capture` too (added to the launch command in
  README) — without it, every recording pauses on a manual "Allow this tab
  to be seen?" permission dialog since the sidecar isn't a
  Playwright-launched browser and doesn't inherit any args from `zoom.py`'s
  `launch()` call.
- **Zoom: working, tested end-to-end.** Navigates straight to the embedded
  web-client URL (`/wc/join/<id>` instead of `/j/<id>`) to skip the
  app-chooser landing page entirely — that page auto-attempts a
  `zoommtg://` native-app launch, which pops an unclosable-by-Playwright
  Chromium dialog. `playwright-stealth` (with `chrome_runtime` explicitly
  turned on — this port defaults it off, unlike the upstream
  puppeteer-extra-plugin-stealth the reference project uses) gets past
  Zoom's "Automated bots aren't allowed" check, though not with 100%
  reliability — repeated automated joins against the same meeting/IP in a
  short window seem to raise Zoom's suspicion regardless of stealth quality;
  space out test runs if it starts failing again.

### Known accepted limitation

Recording captures the whole screen, not just the meeting tab. Tab-only
capture needs the joined page to have real OS-level window focus at the
moment `getDisplayMedia()` fires; `page.bring_to_front()` only switches
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

1. Automatic transcription: pipe finished recordings through OpenAI Whisper.
   This is the next feature on the thesis proposal's roadmap and the
   prerequisite for AI summarization after it — both bots now reliably
   produce a `.webm` with real audio, so there's something to feed it.
2. Known POC gaps, not started (see README "Not handled yet" for the full
   list): one meeting at a time (Playwright runs sync in the request
   thread), no retry beyond a single 60s admission wait, no auth on the
   endpoints, no inactivity detection (recording always runs the full
   `MAX_RECORDING_DURATION_MINUTES`), no mute/stop-video equivalent gap on
   Google Meet's side (only Zoom's join flow does this).

## To resume on another machine

```bash
cd meeting-bot
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

For Google Meet, also start the signed-in Chrome sidecar (README has the
exact command, including `--auto-accept-this-tab-capture` — and a warning to
use a separate Google account, not your personal one). Zoom needs no extra
setup.
