# Notulis — Meeting Bot

POC bot that joins a Google Meet or Zoom call as a guest, records the tab
(video+audio), transcribes it (with speaker labels), and produces an AI
summary. Flask + Playwright + whisperx + GPT-4o mini backend, React Native
(Expo, web target) frontend. Join-flow adapted from
[screenappai/meeting-bot](https://github.com/screenappai/meeting-bot) (MIT).

Full backend setup/run/test instructions: `meeting-bot/README.md`. This file
is project status — what's done, what's next, what to watch out for.

## Repo state

- `meeting-bot/` — Flask backend (bot, transcription, summarization). See
  "What's built" below.
- `frontend/` — Expo (React Native Web) frontend, plain JS/JSX (no
  TypeScript, by request — easier to read while learning). Scaffolded to
  match the features in the thesis proposal ("seminar ide") only, nothing
  extra, so it stays simple to explain to the advisor.
- `reference/` (a local clone of screenappai/meeting-bot, kept for reading
  their implementation) is gitignored, not committed — it's a reference
  clone, not part of the shipped bot.

## What's built

### Backend (`meeting-bot/`)

- `app.py` — Flask app (`threaded=True`), endpoints:
  - `POST /google/join` / `POST /zoom/join` — **async now**: starts the bot
    in a background thread and returns `{job_id}` immediately instead of
    blocking for the whole meeting. Poll `GET /jobs/<job_id>` for progress —
    `{status: "joining"|"recording"|"stopping"|"processing"|"done"|"failed",
    elapsed_seconds?, result?, error?}` (`elapsed_seconds` only while
    `status: "recording"`, read from `bot.record_started_at`). `POST
    /jobs/<job_id>/stop` sets `bot.stop_event`, which `bots/base.py`'s
    `record()` checks once a second instead of one blind `time.sleep()` —
    ends the recording early (still runs the full transcribe/summarize
    pipeline on whatever got captured), for the frontend's "Stop Rekam"
    button. `_jobs` is an in-memory dict (`app.py`), lost on restart —
    fine at POC scale, matches everything else here being single-process.
  - `POST /upload` — multipart file, for meetings that weren't captured by
    the bot. Still synchronous/blocking (no stop button needed — there's no
    live recording to cut short) — reuses the same
    transcribe/fix/summarize pipeline as the join endpoints.
  - `GET /meetings` — reads the index below.
  - `GET /meetings/<id>` — one meeting's full detail, reading its
    transcript/fixed_transcript/summary back from their sibling files on
    disk via `pipeline/paths.py`'s `sibling_path()` — the `meetings` table
    only stores the recording path, not that text.

  Each pipeline step's failure is reported independently
  (`transcript_error`, `fix_transcript_error`, `summary_error`) rather than
  failing the whole request — a bad summary shouldn't erase a recording
  that's already on disk. Wide-open CORS (`Access-Control-Allow-Origin: *`)
  so the frontend's dev server (different port = different origin) can call
  it directly — fine for now since there's no auth either (see "Known POC
  gaps" below); tighten both together before this is ever exposed publicly.
  `/upload` also caps request bodies at 1GB (`MAX_CONTENT_LENGTH`) so an
  oversized file can't hang the dev server.
- `pipeline/meetings_store.py` — `add_meeting()` / `list_meetings()` /
  `get_meeting(id)`, backed by a real Postgres database (Supabase). Every
  successful join/upload inserts a row (`id`, `platform`, `title`,
  `created_at`, `duration_minutes`, `status`, `recording`,
  `estimated_participants`); the `meetings` table (and its columns added
  after the fact) is ensured once per process via `CREATE TABLE IF NOT
  EXISTS` + `ALTER TABLE ADD COLUMN IF NOT EXISTS` — no separate migration
  step. Needs `DATABASE_URL` in `.env` (see "To resume on another machine").
  `duration_minutes` is wall-clock time around `bot.join()` for the join
  endpoints (includes join negotiation, not just recording time), and always
  `null` for `/upload` (no cheap way to get audio duration without decoding
  the file again or adding an `ffprobe` dependency). 4 pre-`meetings_store.py`
  Google Meet recordings that already had a transcript were backfilled by
  hand (one-off `add_meeting()` calls, not a saved script) with their real
  recorded-at time parsed from the filename's timestamp.
  **Keeps one connection alive across calls** (module-level `_conn`,
  reconnects once on `psycopg2.OperationalError`) rather than opening a new
  one per call — Supabase is remote (ap-southeast-2), so a fresh `connect()`
  cost ~1.7s and re-running the `CREATE TABLE`/`ALTER TABLE` check on top of
  that added another ~0.6s, meaning every single `/meetings` request took
  ~3.2s before this. Down to ~0.5s (just the query's own network round trip)
  after. A `threading.Lock` around every use of `_conn` serializes access
  across threads — needed since `app.py` runs `threaded=True` (for job
  polling, see above), and a psycopg2 connection isn't safe to touch from
  multiple threads at once with no coordination at all.
- `bots/base.py` — shared recording logic: injects a `getDisplayMedia` +
  `MediaRecorder` script into the joined page, relays chunks back to Python
  via an exposed function, writes them to `recordings/videos/`.
- `bots/google_meet.py` — Google Meet join flow (CDP-attached signed-in
  sidecar Chrome).
- `bots/zoom.py` — Zoom join flow (anonymous guest, direct web-client URL +
  stealth patch).
- `pipeline/transcribe.py` — transcription via `whisperx` (local, no API
  cost): a faster-whisper backend, word-alignment, and pyannote diarization,
  producing a `[SPEAKER_NN] ...`-labeled transcript per line. Saves to
  `recordings/transcripts/`.
- `pipeline/summarize.py` — two GPT-4o mini passes: `fix_transcript()`
  corrects likely ASR mistakes and collapses hallucinated repeated closing
  lines (saves to `recordings/fixed_transcripts/`), then `summarize()`
  produces `{executive_summary, key_decisions, topics_discussed}` JSON
  (saves to `recordings/summaries/`) per Table 2 of the proposal.
- `pipeline/paths.py` — `sibling_path()`: given a video path like
  `recordings/videos/Foo_123.webm`, resolves the matching file in a sibling
  type folder (`recordings/transcripts/Foo_123.txt` etc.), creating it if
  needed. All three output stages use this so everything for one meeting
  shares a filename stem across `videos/`, `transcripts/`,
  `fixed_transcripts/`, and `summaries/`.

### Frontend (`frontend/`)

Expo Router (file-based routing — folder structure under `app/` = URL
structure; `(app)/` is a route group, doesn't appear in the URL; `_layout.jsx`
wraps every page in its folder, that's where the sidebar/topbar shell lives).

- `app/login.jsx` — split-panel login/landing screen. No auth wired up yet
  (POC scope) — the "Masuk" button links straight to `/dashboard`.
- `app/(app)/dashboard.jsx` — stats (Total Rapat, Total Durasi, Transkrip +
  success rate, Rapat Gagal) and the "Rapat Terbaru" list are now real,
  fetched via `listMeetings()` and computed client-side from that — no more
  invented numbers. ("Anggota Aktif" from the old mock data was dropped
  rather than kept as a 4th fake stat next to 3 real ones — there's no
  backend concept of organization members yet.) 4 quick actions: "Rapat
  Baru" and "Upload Audio" (header + sidebar) link to the two pages below;
  "Bandingkan Rapat" / "Knowledge Base" link to their placeholder pages.
- `app/(app)/rapat/index.jsx` — "Rapat" list, same real data as the
  dashboard's panel (all of it, not just the top 5), with loading/error/empty
  states and a "+ Rapat Baru" button. Each row (`components/MeetingRow.jsx`)
  links to the detail page below.
- `app/(app)/rapat/[id].jsx` — one past meeting's detail: title, platform,
  date/status, then the same transcript/summary rendering as a fresh
  join/upload result (`components/PipelineResult.jsx`, reused — its "Tutup"
  button is omitted here since `onDone` isn't passed). Backed by
  `GET /meetings/<id>`.
- `app/(app)/rapat/baru.jsx` — "Buat Sesi Rapat Baru": platform (Google
  Meet/Zoom), meeting link, bot name, optional "Perkiraan Jumlah Peserta" →
  starts the join via `POST /google/join` or `/zoom/join` (returns a
  `job_id` immediately, doesn't block) then polls `GET /jobs/<id>` every
  second. Shows a distinct UI per phase: "joining" spinner, then a live
  elapsed-time counter + **"Stop Rekam"** button while `status: "recording"`
  (hits `POST /jobs/<id>/stop`), a "processing" spinner once the bot's left
  the meeting, then the real transcript/summary (or the real error) via
  `components/PipelineResult.jsx`.
- `app/(app)/rapat/upload.jsx` — "Upload Audio Rapat": drag-and-drop or
  click-to-browse (native `<input type="file">`, not a library — this app
  is web-only so a real DOM input works fine), optional "Perkiraan Jumlah
  Peserta" once a file is picked → calls `POST /upload` for real. Same
  result/loading UI as above.
- `knowledge-base.jsx`, `perbandingan.jsx`, `laporan.jsx`, `organisasi.jsx` —
  still placeholder pages (`components/PlaceholderPage.jsx`) listing the
  planned features from the proposal for each, not wired to the backend yet.
- `lib/format.js` — `formatMeetingDate()`: turns a backend `created_at` ISO
  timestamp into the {date, time} shape `MeetingRow` expects ("Hari ini" /
  "Kemarin" / "3 Sep").
- `hooks/usePipelineRun.js` — shared idle→loading→done/error state machine,
  used by both `rapat/baru.jsx` and `rapat/upload.jsx` so that logic isn't
  duplicated across the two pages.
- `lib/api.js` — the only place that talks to the backend (`fetch()` calls
  to `EXPO_PUBLIC_API_URL`, default `http://localhost:5050`).
- `constants/theme.js` — design tokens (colors, spacing, type, radius) used
  everywhere instead of hardcoded values.
- `constants/mock-data.js` — down to just `aiInsight` and `currentUser`
  (dashboard banner copy, sidebar user chip) — no real "AI insight" or
  auth/org backend exists yet, so these stay mock. `meetings`/
  `dashboardStats` were removed once real data replaced them.

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
  passing `num_speakers=4` found 3. Scraping the real participant count from
  Google Meet/Zoom's web client turned out to be impractical to do safely
  (no documented/stable selector, and no way to test one live without either
  a signed-in Google session or an active Zoom meeting) — so instead, both
  `rapat/baru.jsx` and `rapat/upload.jsx` have an optional "Perkiraan Jumlah
  Peserta" field the user fills in themselves. Threaded through
  `joinMeeting()`/`uploadAudio()` → `/google/join`, `/zoom/join`, `/upload`
  → `_process_recording()` → `transcribe(num_speakers=...)`. An approximate,
  user-entered number is still a meaningfully better hint than none, per the
  2-vs-3 result above.
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

**This "acceptable" reasoning only holds for one bot per virtual display.**
It assumes the Xvfb/Docker display has nothing else on it — true today
because only one meeting runs at a time. That used to be a side effect of
`/google/join`/`/zoom/join` blocking the whole request; now that joins run in
a background thread (see "What's built" — needed for the "Stop Rekam"
button + live elapsed time), blocking no longer enforces it by accident, so
`app.py`'s `_join()` explicitly rejects a new join (`409`) while one is
already in progress (`phase in ("starting", "processing")` in `_jobs`) —
same one-at-a-time behavior as before, just intentional now instead of
incidental. The moment that guard is ever lifted for real concurrency, two
bots sharing the same display would capture each other's windows. Google
Meet has it worse: the sidecar is one long-lived logged-in Chrome attached
to repeatedly over CDP, so concurrent Meet joins would even share the same
browser, not just the same display — tabs, not just windows, could get
captured across each other. Zoom's bot at least launches a fresh Playwright
browser per join (`bots/zoom.py`), so it only needs display isolation, not
browser isolation. Bottom line: true concurrency needs one
isolated virtual display (ideally one container) per in-progress meeting —
this is one of the concrete reasons "Next steps" #5 wants a real job queue
instead of the current one-request-does-everything model, not just for
tidier request handling.

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
   Google Meet has been confirmed end-to-end so far). The frontend's "Buat
   Sesi Rapat Baru" page now calls `/zoom/join` for real, so this can be
   tested straight from the UI — just make sure `python app.py` (backend)
   is running first.
2. ~~Wire real participant count into `num_speakers`~~ — done, but as a
   user-entered estimate, not a scraped real count (see "Transcription/
   summarization notes" above for why).
3. ~~Make the `/rapat` list, dashboard stats, and meeting rows real~~ — done:
   `pipeline/meetings_store.py` persists every join/upload to a real Postgres
   database (Supabase), `GET /meetings` serves it, and the frontend fetches
   it instead of `constants/mock-data.js`.
4. Known POC gaps, not started (see README "Not handled yet" for the full
   list): one meeting at a time (now an explicit `409` guard in `_join()`
   rather than a side effect of blocking, see "Known accepted limitation"
   above), no auth on the endpoints, no *automatic* inactivity detection —
   a human can now cut a recording short via "Stop Rekam" (`POST
   /jobs/<id>/stop`), but nothing detects on its own that everyone already
   left; it still runs the full `MAX_RECORDING_DURATION_MINUTES` unless a
   person stops it. Two items previously listed here turned out to already
   be handled and were removed after re-checking the actual code: Zoom's
   join already mutes mic/turns off camera (`bots/zoom.py`'s `click_toggle`
   calls) and — less obviously — so does Google Meet's, just via a different
   mechanism (the sidecar Chrome has no real camera/mic, so Meet offers a
   "Continue without microphone and camera" dialog, which `google_meet.py`'s
   `_CONTINUE_WITHOUT_DEVICES` handler clicks); and Google Meet already
   retries a failed admission (`_MAX_JOIN_ATTEMPTS = 3`) — only Zoom's join
   is genuinely a single 60s attempt with no retry.
5. Eventually: move off the in-memory `_jobs` dict/background-thread setup
   toward the proposal's actual architecture (Redis job queue, S3 upload
   instead of local disk, auth between the main Notulis backend and this
   service). The join endpoints are non-blocking now (previous point), but
   that's a lighter-weight stopgap for one process, not the real thing — no
   isolation between jobs, nothing survives a restart, still just one job at
   a time by an explicit guard rather than true concurrency. Deliberately not
   started beyond that — not worth the infra investment until the full
   pipeline had a chance to be validated first. Not just about tidier request
   handling either — it's also what concurrent meetings actually need for
   capture isolation, see "Known accepted limitation" above.

## To resume on another machine

```bash
cd meeting-bot
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Fill in `.env`: `OPENAI_API_KEY` (AI summarization/transcript-fix, GPT-4o
mini), `HF_TOKEN` (diarization — remember this also needs accepting the
pyannote model's terms on HuggingFace once, a token alone isn't enough; see
"Transcription/summarization notes" above), and `DATABASE_URL` (Postgres
connection string for the meetings index — using Supabase: Project Settings
-> Database -> Connection string). The `meetings` table is created
automatically on first connect, nothing to migrate by hand.

For Google Meet, also start the signed-in Chrome sidecar (README has the
exact command, including `--auto-accept-this-tab-capture` — and a warning to
use a separate Google account, not your personal one). Zoom needs no extra
setup.

For the frontend:

```bash
cd frontend
npm install --legacy-peer-deps
npm run web
```

Opens on `http://localhost:8081`. It expects the backend at
`http://localhost:5050` by default (override with `EXPO_PUBLIC_API_URL`) —
run `python app.py` in `meeting-bot/` first, or "Buat Sesi Rapat Baru" /
"Upload Audio Rapat" will just show a connection error.
