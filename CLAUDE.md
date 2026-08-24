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
- `bots/google_meet.py` — Google Meet join flow.
- `bots/zoom.py` — Zoom join flow (guest join, works anonymously).

## Status per platform

- **Google Meet: working, tested.** Confirmed during testing that Google
  blocks anonymous automated joins *and* blocks a Playwright-driven login,
  regardless of stealth patches. Workaround (implemented): a human logs into
  a dedicated Chrome window with `--remote-debugging-port=9222`, and the bot
  attaches to that already-authenticated session over CDP instead of
  launching/logging in its own browser. See README "Google Meet: run a
  signed-in Chrome sidecar" for the exact steps — this sidecar Chrome must be
  running before `/google/join` is called.
- **Zoom: implemented but NOT confirmed end-to-end yet.** The debugging
  session went entirely into getting Google Meet working; Zoom is next to
  actually test. It's also a simplified join path — only handles the meeting
  URL landing directly on a page with a "Join from your browser" link. The
  reference project has a longer fallback chain ("Launch Meeting" → "Download
  Now" → "Join from your browser") for meetings that don't land there
  directly; not ported.

## Next steps

1. Test Zoom end-to-end (join, get admitted, record, file plays back).
2. If Zoom's direct-join assumption fails on a real meeting, port more of the
   reference project's fallback chain.
3. Known POC gaps, not started (see README "Not handled yet" for the full
   list): one meeting at a time (Playwright runs sync in the request thread),
   no retry beyond a single 60s admission wait, no auth on the endpoints, no
   inactivity detection (recording always runs the full
   `MAX_RECORDING_DURATION_MINUTES`).

## To resume on another machine

```bash
cd meeting-bot
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

For Google Meet, also start the signed-in Chrome sidecar (README has the
exact command + a warning to use a separate Google account, not your
personal one). Zoom needs no extra setup.
