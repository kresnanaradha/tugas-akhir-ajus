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
- `DATABASE_URL` — Postgres connection string for the meetings index
  (`pipeline/meetings_store.py`). Using Supabase: Project Settings ->
  Database -> Connection string. The `meetings` table is created
  automatically on first connect.

Transcription runs locally (no API cost, audio never leaves the machine) via
`whisperx`, which needs `ffmpeg` on `PATH`.

### Google Meet: log in once, save the session

Confirmed during testing: Google Meet denies anonymous automated joins
("You can't join this video call") even with `playwright-stealth` fully
applied, and separately, Google's login page itself refuses to sign in a
Playwright-launched browser ("This browser or app may not be secure") —
that block applies to the *login step*, regardless of stealth.

So the bot never performs the Google login itself. Instead, a human logs in
once and the session (cookies/localStorage) gets saved to a file; every
`/google/join` call loads that file into a fresh Playwright browser instead
of logging in itself. (Previously this ran through a long-lived,
manually-launched Chrome sidecar attached to over CDP — replaced because it
couldn't run inside Docker, where there's no human around to keep a Chrome
window open.)

1. Create a separate Google account for the bot (do not use your personal one).
2. Run the login helper — launches a real Chrome window (a plain subprocess,
   not Playwright-controlled, since Google blocks sign-in on an
   automation-attached browser) pointed at the Google sign-in page:
   ```bash
   python -m bots.google_login
   ```
   If it can't find your Chrome install, set `CHROME_EXECUTABLE_PATH` in
   `.env` to its full path.
3. Log in to the bot's Google account manually in that window, then press
   Enter in the terminal — this attaches Playwright over CDP just long
   enough to save the now-logged-in session to `GOOGLE_AUTH_STATE_PATH`
   (`.env`, default `auth/google.json`).
4. Every `/google/join` call from here on loads that file into a fresh,
   Playwright-launched browser — no Chrome window needs to stay running
   between joins.

Re-run step 2 if joins start failing with a login/redirect error — the saved
session has likely expired.

For running multiple Google accounts concurrently (see `CLAUDE.md`'s "1
container = 1 account" plan), give each account its own
`GOOGLE_AUTH_STATE_PATH` and run the login helper once per account.

Zoom's guest join doesn't require any of this; it works anonymously.

## Run

```bash
python app.py
```

## Test manually

```bash
curl -X POST http://localhost:5050/google/join \
  -H "Content-Type: application/json" \
  -d '{"url": "https://meet.google.com/xxx-yyyy-zzz", "name": "Notulis Bot"}'

curl -X POST http://localhost:5050/zoom/join \
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
- Zoom has no retry for host-denied or lobby-timeout cases beyond a single
  60s wait — the request just fails. (Google Meet already retries up to 3
  times — `google_meet.py`'s `_MAX_JOIN_ATTEMPTS` — Zoom doesn't have an
  equivalent.)
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
- Diarization's speaker-count hint (`num_speakers`) is a user-entered
  estimate ("Perkiraan Jumlah Peserta" in the frontend), not the meeting's
  real participant count — there's no reliable way to scrape that from
  Google Meet/Zoom's web client (see `CLAUDE.md` "Transcription/
  summarization notes").
