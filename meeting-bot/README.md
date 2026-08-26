# Meeting Bot (POC)

Minimal Flask + Playwright bot that joins a Google Meet or Zoom call as a
guest, records the tab (video+audio) via `MediaRecorder`, transcribes it
locally with speaker labels (`whisperx`), then has GPT-4o mini clean up the
transcript and summarize it. Everything lands under `recordings/`, split
into `videos/`, `transcripts/`, `fixed_transcripts/`, and `summaries/`.

Join-flow selectors adapted from [screenappai/meeting-bot](https://github.com/screenappai/meeting-bot) (MIT license).

**This is a proof of concept, not production code.** See "Not handled yet" below.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Fill in `.env`:
- `OPENAI_API_KEY` — for AI summarization and transcript cleanup (GPT-4o
  mini). Get one at https://platform.openai.com/api-keys.
- `HF_TOKEN` — for speaker diarization. A Read-Only token from
  https://huggingface.co/settings/tokens is enough, but a token alone
  **isn't sufficient**: while logged in, also visit
  https://huggingface.co/pyannote/speaker-diarization-community-1 and accept
  its terms once, or diarization fails with `GatedRepoError` on first use.

Transcription runs locally (no API cost, audio never leaves the machine) via
`whisperx`, which needs `ffmpeg` on `PATH`.

### Google Meet: run a signed-in Chrome sidecar

Confirmed during testing: Google Meet denies anonymous automated joins
("You can't join this video call") even with `playwright-stealth` fully
applied, and separately, Google's login page itself refuses to sign in a
Playwright-launched/CDP-attached browser ("This browser or app may not be
secure") — that block applies to the *login step*, regardless of stealth.

So the bot never performs the Google login itself. Instead: a human logs in
once, in a real Chrome window, and the bot only attaches to that
already-authenticated browser over the DevTools protocol (CDP) to drive the
Meet join — the same approach the reference project's `chrome-cdp` sidecar
uses.

1. Create a separate Google account for the bot (do not use your personal one).
2. Launch a dedicated Chrome with remote debugging enabled and leave it running.
   Use an **absolute** path for `--user-data-dir` (a relative one gets
   resolved against Chrome's own install directory, which fails to write
   without admin rights) — replace the path below with your own
   `meeting-bot/chrome-profile` directory:
   ```bash
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\path\to\meeting-bot\chrome-profile" --auto-accept-this-tab-capture
   ```
   `--auto-accept-this-tab-capture` matters here specifically: it's normally
   passed to Playwright's own `chromium.launch()`, but this sidecar is a
   regular Chrome the human launches by hand, so it doesn't get that flag
   for free. Without it, every recording pauses on a manual "Allow this tab
   to be seen?" dialog that has to be clicked by hand.
3. In that Chrome window, log in to the bot's Google account manually (normal
   login — this window isn't automated yet, so Google doesn't block it).
4. Set `GOOGLE_CHROME_CDP_URL=http://localhost:9222` in `.env` (already the
   default in `.env.example`).
5. Leave that Chrome window open. Every `/google/join` call attaches to it,
   opens a new tab for the meeting, and closes only that tab when done — the
   signed-in session stays alive for the next join.
6. If Chrome was already running when you launched step 2, the new flags get
   silently ignored (it just opens another window in the already-running
   process). Close every Chrome window first, confirm no `chrome.exe`
   process is left, then launch the sidecar.

Zoom's guest join doesn't require any of this; it works anonymously.

## Run

```bash
python app.py
```

## Test manually

```bash
curl -X POST http://localhost:5000/google/join \
  -H "Content-Type: application/json" \
  -d '{"url": "https://meet.google.com/xxx-yyyy-zzz", "name": "Notulis Bot"}'

curl -X POST http://localhost:5000/zoom/join \
  -H "Content-Type: application/json" \
  -d '{"url": "https://zoom.us/j/xxxxxxxxxx", "name": "Notulis Bot"}'
```

The request blocks until the bot leaves the meeting (after
`MAX_RECORDING_DURATION_MINUTES`, default 5), transcribes, cleans up the
transcript, and summarizes — that whole chain, not just the recording, so
expect it to take a while longer than the meeting itself. The response has
everything from whichever steps succeeded:

```json
{
  "status": "done",
  "recording": "recordings/videos/ZoomBot_1712345678.webm",
  "transcript": "[SPEAKER_00] ...",
  "fixed_transcript": "[SPEAKER_00] ...",
  "summary": {
    "executive_summary": "...",
    "key_decisions": ["..."],
    "topics_discussed": ["..."]
  }
}
```

If transcription, transcript-fixing, or summarization fails, its key is
replaced with `..._error` (e.g. `transcript_error`) instead — a failure at
any step doesn't erase the successful ones before it, so a recording is
never lost just because, say, the OpenAI API had a bad moment.

To test with your own Google Meet: start a meeting from your own Google
account in one browser/tab, then hit `/google/join` with that meeting's URL
— the bot joins as an anonymous guest and (depending on your Meet settings)
you may need to manually click "Admit" in your own meeting window.

## Most likely to break

- **Google Meet anonymous-join / automated-login detection.** Confirmed
  during testing: Google reliably shows "You can't join this video call" for
  an unauthenticated Playwright browser (even fully stealthed), and separately
  refuses to let a Playwright-attached browser sign in at all. This is why
  the bot connects to a human-authenticated Chrome sidecar over CDP instead
  (see setup above). If joins start failing again even with the sidecar,
  suspect Google's detection has adapted further — this is an ongoing
  cat-and-mouse, not a one-time fix.
- **Playwright selectors vs UI changes.** Both bots rely on text/attribute
  selectors scraped from the current Meet/Zoom web UI (button text,
  aria-labels, element IDs). Google and Zoom change this UI without notice;
  when a join stops working, this is the first place to check. Zoom in
  particular has already changed "Join from your browser" wording once
  during this project's own testing.
- **Zoom's bot-detection is inconsistent.** `playwright-stealth` gets past
  the "Automated bots aren't allowed to join this meeting" check most of the
  time, but not always — repeated automated joins against the same
  meeting/IP in a short window seem to raise Zoom's suspicion regardless of
  stealth quality. If joins that used to work start failing with that
  message, try spacing out test runs or a different network before assuming
  the code regressed.
- **Zoom's join path is simplified.** It navigates straight to the embedded
  web-client URL (`/wc/join/<id>`) and assumes that lands on a joinable page
  directly. The reference project has a longer fallback chain ("Launch
  Meeting" → "Download Now" → "Join from your browser", plus
  iframe-vs-app-container detection) for meetings that don't land there
  directly; not ported. Confirmed working end-to-end for the direct case.

## Not handled yet (POC scope only)

- One process handles one meeting at a time — Playwright runs synchronously
  inside the Flask request thread, so concurrent join requests will block
  each other.
- No error handling/retry for host-denied or lobby-timeout cases beyond a
  single 60s wait — the request just fails.
- No auth on the endpoints, no webhook notification, no S3 upload, no Redis
  queue, no Docker, no multi-language selector text (Meet's German-language
  UI text etc. from the reference isn't included).
- No inactivity/lone-participant detection — recording always runs the full
  `MAX_RECORDING_DURATION_MINUTES` regardless of whether anyone's still in
  the call.
- Recording captures the whole screen rather than just the meeting tab in
  local dev (see `CLAUDE.md` "Known accepted limitation" for why this was
  left as-is — it's not expected to matter once deployed to an isolated
  display).
- Diarization guesses the speaker count instead of using the meeting's real
  participant count — `transcribe()` accepts a `num_speakers` hint, but
  nothing currently passes one through from the join endpoints.
- No upload-audio endpoint yet — `transcribe()`/`summarize()` already work
  on any audio/video file path, not just bot output, so this is mostly just
  a new route away.
