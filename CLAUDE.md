# Notulis — Meeting Bot

Thesis-project meeting bot that joins a Google Meet or Zoom call as a guest,
records it (video+audio), transcribes it (with speaker labels), and produces
an AI summary — now grown into a small multi-user product around that core:
login/roles, per-user meeting history, a RAG knowledge base over past
meetings, PDF reports, Xendit subscription billing, a super admin dashboard,
and Docker-based multi-worker bots. Flask + Playwright + whisperx + GPT-4o
mini backend, React Native (Expo, web target) frontend. Join-flow adapted
from [screenappai/meeting-bot](https://github.com/screenappai/meeting-bot)
(MIT).

Full backend setup/run/test instructions: `meeting-bot/README.md`. This file
is project status — what's done, what's next, what to watch out for.

## Repo state

- `meeting-bot/` — Flask backend (bot, transcription, summarization, auth,
  billing, admin, RAG). See "What's built" below.
- `frontend/` — Expo (React Native Web) frontend, plain JS/JSX (no
  TypeScript, by request — easier to read while learning).
- `reference/` (a local clone of screenappai/meeting-bot, kept for reading
  their implementation) is gitignored, not committed — it's a reference
  clone, not part of the shipped bot.

## What's built

### Backend (`meeting-bot/`)

**Auth** (`pipeline/auth_store.py`, `/auth/register|login|logout|me`) —
session-cookie auth (Flask's signed session, `SECRET_KEY` in `.env`), two
roles (`user`, `super_admin`). `login_required`/`super_admin_required`
decorators guard almost every route now (a handful of intentionally-public
ones below). Users have an `active` flag: deactivating replaces deleting,
since old meetings point at `users.id` — a deactivated user is rejected at
login and their live session is cut within 30s (`_active_cache` in `app.py`).
A user also optionally belongs to one team (`users.team_id`/`team_role`,
NULL = no team) — see "Team" below.

**Meeting lifecycle** — `POST /google/join` / `/zoom/join` start the bot in
a background thread and return `{job_id}` immediately; poll `GET
/jobs/<id>` for `{status: "joining"|"recording"|"stopping"|"processing",
elapsed_seconds?, error?}` while the bot is still joining/recording. `POST
/jobs/<id>/stop` ends the recording early via `bot.stop_event` (checked
once a second in `bots/base.py`'s `record()`), for the "Stop Rekam" button.
`_jobs` is an in-memory dict, lost on restart — fine at POC scale. `_join()`
rejects a second join (`409`) while one is already in progress in that
process — see "Known accepted limitation" for why this still matters even
with multiple worker containers. `/jobs/<id>` and `/jobs/<id>/stop` are
**not** `login_required` (a stray gap, low priority since a job id is an
unguessable uuid).

Once the bot finishes and uploads the recording, this process's job is
**done** — `_jobs.pop(job_id)`, so a later `GET /jobs/<id>` 404s on
purpose. Transcription happens elsewhere now (see "Recorder/transcriber
split" below); the frontend already falls back to polling `GET
/meetings/<id>` on a 404 (`rapat/[id].jsx`'s `pollMeeting()`), which reads
the real status from Postgres, so this needed **zero frontend changes**.
`POST /upload` is the one exception: it still runs transcribe→fix→summarize
synchronously in-process via `_process_recording()` (no live recording to
cut short, so no queue hand-off was needed there — not yet moved onto the
queue, see "Known gaps").

**Recorder/transcriber split** (`pipeline/job_queue.py`, `transcriber_service.py`,
`Dockerfile.transcriber`) — recording (Playwright+Chromium+Xvfb, one
lightweight container per concurrent bot) and transcription (whisperx+torch,
heavy but only 1-2 instances needed) used to share one container/process;
this OOM-killed a live test (`mem_limit=3g`, Chrome and whisper together
during optimization-week load testing, see "Docker multi-worker" below) and
is now split into two kinds of container connected by a Redis queue:
- A recorder (`_run_join_job` in `app.py`) uploads the finished recording to
  R2, sets `meetings.status = "processing"`, and pushes
  `{meeting_id, recording_key, num_speakers}` onto Redis
  (`job_queue.enqueue_transcription()`) instead of transcribing itself.
- `transcriber-1`/`transcriber-2` (`docker-compose.yml`, built from
  `Dockerfile.transcriber`, `python:3.12-slim` base — no Playwright/
  Chromium/Xvfb at all) run `transcriber_service.py`, a plain loop that
  blocks on `job_queue.dequeue_transcription()` (Redis `BLPOP`), downloads
  the recording from R2 (`storage.download_to_file()`), runs the same
  transcribe→fix→summarize→email pipeline `_process_recording()` uses for
  `/upload`, and writes `meetings.status = "completed"/"failed"` when done.
  Exactly 2 instances (not scaled 1:1 with bot count) so transcription's
  RAM/CPU — the heaviest part of the whole pipeline — never exceeds 2
  concurrent jobs regardless of how many bots are recording at once.
- Confirmed end-to-end on a real Zoom join: recorded → uploaded → queued →
  picked up by `transcriber-2` (a *different* container than the one that
  recorded) → transcribed → summarized → `status: "completed"` in Postgres.
- `pipeline/summarize.py` used to import `knowledge_base` (chromadb +
  sentence-transformers) at module level even though it's only used when a
  meeting has `in_kb = true` — that alone made the trimmed transcriber
  image fail to boot (`ModuleNotFoundError: chromadb`). Fixed by moving that
  import inside the `if meeting.get("in_kb")` branch, so a caller that never
  touches KB-enabled meetings (the transcriber, almost always) doesn't need
  chromadb installed at all.
- Redis needs `redis-py`'s `socket_timeout` set *larger* than
  `BLPOP`'s own timeout (`pipeline/job_queue.py`) — left unset, redis-py's
  socket read timed out first every ~5s ("`TimeoutError: Timeout reading
  from socket`") instead of `BLPOP` just returning nil the way the protocol
  intends. `transcriber_service.py`'s loop also wraps the dequeue call
  itself in try/except now, not just per-job processing — a transient Redis
  hiccup must never crash a long-running worker.
- Redis is `requirepass`-protected (`REDIS_PASSWORD` in `.env`) even though
  it's never exposed outside the compose network (no `ports:` on the
  `redis` service) — defense in depth against a future port-mapping mistake,
  especially once this runs on a real VPS.

**Meetings** — `GET /meetings` (this user's own, plus meetings handed to them
through same-link sharing, plus any teammate's meeting explicitly opted into
team sharing — see "Team" below; pre-auth rows with `user_id IS NULL` are
visible to nobody but a super admin), `GET /meetings/<id>` (full detail: transcript, summary,
segments, all read back from R2 — the DB row only stores the R2 key), `GET
/meetings/<id>/recording` (302 to a presigned R2 URL, so the browser
streams straight from R2 — Range requests still work for `<video>`
scrubbing). `POST /meetings/<id>/transcript` saves an edited transcript
(and optionally per-line speaker renames/text via `segments.json`) and
re-runs `summarize()`. `DELETE /meetings/<id>` — owner or `super_admin`
only (a pre-auth row with no owner needs `super_admin`), refused while
still recording/processing (`409`); deletes the R2 folder, the Knowledge
Base chunks, then the DB row, in that order so a failure never leaves an
orphaned reference.

**Meeting access** (`_can_view_meeting` / `_can_edit_meeting` in `app.py`) —
*view* (detail, recording, `GET /jobs/<id>`, comparison PDF): owner, super
admin, a user in `meeting_viewers` (see below), or a teammate of the owner when
the owner turned on "Bagikan ke Team"; anyone else gets a `404` (not `403`,
so ids can't be probed). *Edit* (transcript, action items, KB toggle, stop
recording, delete, share-team): owner or super admin only — teammates and
link viewers are read-only. `meeting_viewers` is filled by `_join()` when a
second user submits a link that already has a live/recent meeting
(`find_meeting_by_url`): that user is handed the existing meeting instead of
a second bot, and may then view it.

**Speaker naming** — the transcript editor (`rapat/[id].jsx`) lets you
rename a diarization label (`SPEAKER_00`) to a real name, move a
mis-attributed line to a different speaker, and re-run the summary. When a
speaker's label is a real name, `summarize.py` tells the model explicitly
("these speakers already have confirmed real names: ...") so it uses the
name instead of falling back to "Pembicara N" — a raw name-swap without
that nudge was unreliable (the model kept reverting to "Pembicara N" for
~1 in 3 speakers in testing).

**Action items** — `POST /meetings/<id>/action-items/<index>/toggle`
(`{done: bool}`, explicit value not a blind flip) and `PUT
/meetings/<id>/action-items` (replace the whole list — covers edit/add/
remove in one call). Both take `_summary_lock` (a single process-wide lock)
around the read-modify-write of `summary.json`, because two quick toggles
used to both read the same stale copy and the second write silently erased
the first.

**Knowledge Base** (`pipeline/knowledge_base.py`, sentence-transformers +
Chroma, no API cost) — **opt-in per meeting** (`POST
/meetings/<id>/knowledge-base {enabled}`), not automatic: only the
executive summary (split per paragraph — this embedding model only reads
~128 tokens, a multi-paragraph summary would otherwise get truncated) and
key decisions are indexed. `GET /knowledge-base/search` embeds the query,
searches only meetings this user opted in, and has GPT-4o mini write one
grounded answer from the matched chunks (still not a chatbot — one query,
one answer, no history). Raw cosine similarity from this multilingual
MiniLM model sits in a narrow band (~0.1 unrelated, ~0.35–0.5 genuinely
relevant) rather than spanning 0–1, so it's rescaled (`_FLOOR`/`_CEIL`) to
read as an intuitive percentage, and blended with a lexical boost (a real
content word from the query — 4+ letters, not a stopword, not one of the
words baked into the `_KIND_PREFIX` labels — appearing verbatim in the
chunk's own text) so a short keyword query like "keputusan kresna" doesn't
let every "Keputusan"-labeled chunk outrank the one that actually names
Kresna, purely because it shares the word "keputusan" with the injected
kind label.

**Reports** — `pipeline/report_stats.py` + `pipeline/report_pdf.py` for
this user's own Laporan page (`GET /reports/stats`, `GET
/reports/action-items` — a cross-meeting action-item rollup, cached 60s
and invalidated on any toggle/edit, and `GET /reports/export` for the PDF);
`pipeline/admin_stats.py` for the system-wide Admin dashboard (`GET
/admin/stats`, `GET /admin/export`) — meeting volume, MRR, OpenAI cost
(real tracked usage), R2 storage, user count.

**Perbandingan Rapat** — `GET /perbandingan/export?a=<id>&b=<id>` renders
two meetings side by side as a PDF (a 2-column, 1-row reportlab `Table`
whose cells each hold a list of flowables — the standard trick for
side-by-side content in reportlab, since it has no native two-document
layout). Frontend page does the live side-by-side view; deliberately no
automatic text-diff/highlighting (two different meetings' content is
naturally almost entirely different, so a literal diff would just flag
everything as "different" and add no signal).

**Admin user management** — `GET/POST /admin/users`, `PATCH
/admin/users/<id>` (name/role/active), `POST
/admin/users/<id>/reset-password` — `super_admin` only, can't deactivate or
demote your own account.

**Billing** (Xendit, `pipeline/billing_store.py` /
`pipeline/xendit_client.py`, `/billing/*`) — subscription checkout, cancel
(downgrades at period end), and a webhook (verified by a static
`x-callback-token`, not a payload signature). `/billing/return` and
`/billing/webhook` are intentionally public (a redirect target and a
server-to-server callback respectively); everything else under `/billing/*`
is `login_required` and scoped to `session["user_id"]` (every call site
passes it explicitly — `billing_store`'s `DEFAULT_ACCOUNT_ID` is now just an
unused fallback for a caller that doesn't pass its own id). `PLAN_LIMITS`
(meetings/month, recording minutes/week) is enforced in `app.py`'s
`_check_meeting_quota()`/`_join()`; Knowledge Base access is gated the same
way via `_kb_allowed()`.

**Team** (`pipeline/team_store.py`, `/teams/*`) — one team per user (not a
Slack-style multi-workspace setup): `teams` (id, name, owner_id) and
`team_invites` (token, team_id, optional email, expiry) tables, membership
stored directly on `users.team_id`/`team_role` ('admin' or 'member').
`POST /teams` requires the Team plan and creates the caller as its first
admin; `POST /teams/invite` (admin only) returns a shareable link
(`/team/gabung/<token>`) and, if an email was given, sends it via
`pipeline/mailer.py`'s `send_team_invite_email()` (best-effort — the link
still works even if the email fails to send). `POST /teams/join` accepts an
invite as a member; `DELETE`/`PATCH /teams/members/<id>` (admin only) remove
or re-role a member; `POST /teams/leave` is self-service and deletes the
team if it empties out. Sharing a meeting with the team is a **separate,
per-meeting opt-in** (`POST /meetings/<id>/share-team {enabled}`,
`meetings.shared_with_team`, owner-only) — being on a team never exposes a
meeting automatically, matching how Knowledge Base opt-in already works.
Deliberately not built: nested sub-teams and a hard per-team seat quota —
Team is a flat monthly fee (`billing_store.PLAN_PRICES`), not metered per
seat, so a seat cap would enforce a limit the billing itself doesn't charge
for; revisit if that pricing model changes.

**Email notifications** (`pipeline/mailer.py`, stdlib `smtplib` only, no
new dependency) — after `summarize()` succeeds (shared by both the join
flow and `/upload`), emails the meeting's owner a styled HTML message
(matches the frontend's own color tokens) with the first paragraph of the
summary and a link to the meeting. No-op if `SMTP_HOST`/`SMTP_USER`/
`SMTP_PASSWORD` aren't set in `.env` — stays inert rather than erroring,
same pattern as this app's other optional integrations. A send failure is
logged and swallowed, never fails the pipeline.

**Storage (R2)** — `pipeline/storage.py` (boto3 S3 client against
Cloudflare R2's endpoint) / `pipeline/artifacts.py` (meeting-id-keyed
convenience layer: `save_transcript`/`load_summary`/etc). Every artifact
for one meeting lives under `<meeting_id>/...` (`recording.<ext>`,
`transcript.txt`, `fixed_transcript.txt`, `segments.json`, `summary.json`).
Env vars read lazily (not at import time) — `load_dotenv()` has to run
before any local import, or the bucket name silently reads as unset.

**Transcription/summarization** — `pipeline/transcribe.py` runs whisperx
(faster-whisper + alignment + pyannote diarization) in a **child process**
(`pipeline/transcribe_worker.py`) so the model's memory is released when it
exits, rather than staying resident in the main Flask process between
meetings. `pipeline/summarize.py` does two GPT-4o mini calls: a narrative
pass (`executive_summary`, length scaled to the transcript so it covers the
*whole* meeting rather than staying a fixed short paragraph) and a details
pass (`key_decisions`, `topics_discussed`, `action_items` as JSON).

**Docker multi-worker** (`docker-compose.yml`, `Dockerfile`,
`docker-entrypoint.sh`) — 10 independent worker (recorder) services
(`worker-1` through `worker-10`), each the full backend image in its own
container with its own Xvfb virtual display, its own Google account/session
(`auth/worker-N.json`, mounted read-only), and its own host port; all
share one Postgres/R2/`.env`, plus now `redis`/`transcriber-1`/
`transcriber-2` (see "Recorder/transcriber split" above). **Only `worker-1`
actually has a logged-in Google session right now** — `worker-2` through
`worker-10` need `bots/google_login.py` run once per account before they're
usable (see "Next steps"). Nothing routes a join to "whichever worker is
free" yet — the frontend still points at one fixed `EXPO_PUBLIC_API_URL`,
so today this only proves 10 isolated bot processes *can* run side by side,
not that the app picks one automatically.

`worker-test`/`worker-test-2` (same compose file) are a separate,
throwaway pair used for load-testing during the optimization week (torch
CPU-only build via `Dockerfile`'s `TORCH_CPU` build arg, `mem_limit`/`cpus`
caps, no Google auth mount — tested with Zoom instead, which needs no
login). 2 concurrent Zoom bots there measured a combined ~2.9GB RAM/~40%
CPU — comfortably under a 6-CPU/7.7GB budget — but transcription sharing
the SAME `mem_limit=3g` container as the recording OOM-killed the job; that
finding is what drove the recorder/transcriber split above, not just a
theoretical concern.

### Frontend (`frontend/`)

Expo Router (file-based routing under `app/`; `(app)/` is a route group
that doesn't appear in the URL; `_layout.jsx` wraps every page in that
folder — sidebar/topbar shell and the `login_required`-equivalent redirect
to `/login` live there, via `lib/auth-context.jsx`).

- `app/login.jsx` — real login/register (`lib/api.js`'s `login()`/
  `register()`), not wired-up-yet mock.
- `app/(app)/dashboard.jsx` — real stats + "Rapat Terbaru" from
  `listMeetings()`; the "AI Insight" banner surfaces the newest finished
  meeting's still-open action items (or its key decisions if none are
  open) from its already-generated summary, no extra AI call.
- `app/(app)/rapat/index.jsx` — meeting list split into a filterable list
  (all/platform/failed) on the left and a read-only summary preview of the
  selected meeting on the right, instead of list-then-click-through.
- `app/(app)/rapat/[id].jsx` — one meeting's full detail: tabs for AI
  summary / transcript (video synced to segments) / an editor tab (rename
  speakers, move a mis-attributed line, edit text, re-run the summary);
  editable action items; a "Simpan ke Knowledge Base" toggle; delete.
- `app/(app)/rapat/baru.jsx` / `rapat/upload.jsx` — start a join or upload
  an existing recording; both show "Rapat Terbaru" and either the bot's
  join steps or the upload's processing steps in a side column.
- `app/(app)/knowledge-base.jsx` — real semantic search plus a list of
  which meetings are currently opted into the KB (with a remove button).
- `app/(app)/laporan.jsx` — this user's own volume/recording/action-item
  stats, real charts, PDF export.
- `app/(app)/perbandingan.jsx` — pick two meetings, see them side by side,
  export the same comparison as a PDF.
- `app/(app)/admin.jsx` — system-wide stats (super admin only) plus a user
  management panel (add, change role, reset password, (de)activate).
- `app/(app)/pengaturan.jsx` — Xendit subscription plans (Free/Pro/Team),
  upgrade/downgrade, profile self-service (name/email/phone/password/
  notifications/logout/deactivate).
- `app/(app)/team/index.jsx` — create a team (Team plan only), rename it,
  list/re-role/remove members, generate an invite link (+ optional email),
  leave. `app/(app)/team/gabung/[token].jsx` — the invite landing page
  (shows which team, then `POST /teams/join`). The per-meeting "Bagikan ke
  Team" toggle lives in `rapat/[id].jsx` instead (owner-only, next to
  Hapus Rapat); a teammate's shared meeting shows a "Dibagikan Team" badge
  in `components/MeetingRow.jsx`.
- `lib/api.js` — the only place that talks to the backend.
- `lib/auth-context.jsx` — current-user state + the redirect-to-`/login`
  gate for everything under `(app)/`.
- `constants/theme.js` — design tokens (colors, spacing, type, radius)
  used everywhere instead of hardcoded values; `pipeline/mailer.py` and
  `pipeline/report_pdf.py` on the backend mirror this same palette so
  emails/PDFs don't look like a different product.

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
  Google Meet/Zoom's web client turned out to be impractical to do safely,
  so instead both `rapat/baru.jsx` and `rapat/upload.jsx` have an optional
  "Perkiraan Jumlah Peserta" field the user fills in themselves — threaded
  through to `transcribe(num_speakers=...)`. Passing `1` skips diarization
  entirely (everything gets one label) and is noticeably faster.
- **Runs on CPU** (no GPU on the dev machine) via `compute_type="int8"` —
  reasonably fast for `WHISPER_MODEL=medium`; `large-v3` needs ~8-10GB RAM to
  even load and is impractical without a GPU, don't reach for it by default.
- The `fix_transcript()` prompt has to be told explicitly to only collapse
  *literally repeated* trailing phrases — an earlier looser version ("remove
  trailing filler/closing phrases") over-trimmed and deleted real closing
  sentences that just happened to sound like a sign-off.
- Whisper mishears this project's own vocabulary without help — "taun
  skripsi" instead of "transkripsi" was a recurring one. Two things fixed it:
  Whisper's `initial_prompt` (in `transcribe.py`) and an explicit term list
  in `fix_transcript()`'s system prompt (in `summarize.py`), extendable via
  `EXTRA_VOCAB` in `.env` for names specific to one deployment.

### Known accepted limitation

Recording captures the whole screen, not just the meeting tab, in local dev
(tab-only capture needs real OS-level window focus at the moment
`getDisplayMedia()` fires, which Playwright can't reliably force). Decided
not to chase this further: in a real deployment the browser runs in an
isolated display (Xvfb/Docker) with nothing else on it, so "whole screen"
and "just the tab" are the same capture either way.

**This reasoning only holds for one bot per virtual display.** With the
multi-worker Docker setup, that's true by construction — each worker
container gets its own Xvfb display — but *within* one worker, `_join()`'s
`409` guard still matters: that one process/display can only safely run one
recording at a time, since two bots sharing a display would capture each
other's windows (and Google Meet's sidecar shares one long-lived browser
across joins, so it's worse there — tabs, not just windows, could get
captured across each other). True per-worker concurrency would need real
per-job display isolation, which isn't built.

### Playwright version pin

`requirements.txt` pins `playwright==1.63.0` (matched to the Dockerfile's
base image tag — bump both together). Below `1.60.0`, Chrome for Testing
crashes when stopping a `getDisplayMedia` stream's tracks
([microsoft/playwright#39158](https://github.com/microsoft/playwright/issues/39158)),
which is exactly what `base.py`'s `_STOP_JS` does on every recording. If a
recording ever dies again with "Target page, context or browser has been
closed" and no diagnostic output, check this hasn't regressed before
spending hours re-debugging it.

## Long meetings (1-2 hours)

What changed so a long recording doesn't silently break (checked individually,
but no full-length run has been done yet -- do a 15-minute one first):
- `MAX_RECORDING_DURATION_MINUTES` in `.env` is empty = no global cap (0 works
  too). A recording then ends on host-ended / alone for
  `EMPTY_MEETING_MINUTES` / no sound for `SILENCE_MINUTES` (default 30, 0 = off;
  an AudioContext analyser in the recorded page, RMS > 0.003, checked in
  `bots/base.py`) / Stop Rekam, so a stuck bot records until one of those fires
  (~270 MB per hour in R2). Free is capped by a weekly pool instead: 60 recorded
  minutes per week (bot joins only, not uploads, `_weekly_quota()` in `app.py`),
  reset every Sunday 08:00 server time (WITA); the join is refused when it is
  used up, the recording is cut at what is left, and the owner gets one email
  (`mailer.send_quota_exhausted_email`) on the recording that used the last
  minutes. Plus 5 meetings per month (`billing_store.PLAN_LIMITS`). Pengaturan
  shows the remaining minutes. Use a Team/Pro account to test beyond 60 minutes.
  The env var is read when the container
  is created, so recreate `worker-*` after changing it.
- `bots/base.py` `record()` writes each chunk to disk as it arrives instead of
  holding the whole recording in memory until the end (about 4.5 MB per minute,
  so ~550 MB for 2 hours): a crash mid-meeting keeps what was captured so far.
  The partial file lives inside the container (`recordings/videos/`), so it
  survives a `docker restart` but not a container re-create.
- `summarize.fix_transcript()` works in blocks of ~2000 words
  (`_split_for_fix`). gpt-4o-mini returns at most ~16k tokens, and the old
  single call had to return the whole transcript, so anything past roughly an
  hour was cut off without an error and `summarize()` then summarized the cut
  version. A block whose answer is cut off or empty falls back to its raw text.
  Checked against the real model on an 11,196-word transcript: 99% of the
  words and 715 of 720 lines came back.
- Measured on a real 60-minute Google Meet (6 speakers, CPU only):
  - First run, whisper `medium` int8, 2 cores, stages one after another: 4 h 33 min
    (4.5x the recording), peak RAM 4.0 GB, and `medium` MISSED about a third of the
    speech (174 vs 272 words on a 3-minute clip; whole meetings looked complete).
  - Now, `large-v3-turbo` (default, also in `.env`), speaker diarization running in a
    thread next to speech-to-text, 6 cores, `WHISPER_THREADS`/`OMP_NUM_THREADS` = 3:
    2 h 04 min (2.0x), peak RAM 4.9 GB. On the 3-minute clip diarization was ~half of
    the old total (556 of 1149 s). Peak RAM of a 3-minute clip already touched 6.1 GB,
    so transcribers have `mem_limit` 7g and only ONE long job should run at a time
    (`docker compose stop transcriber-2`).
  - Per-stage `[timing]` lines are printed by `pipeline/transcribe_worker.py`; they only
    reach the container log since `transcribe.py` stopped capturing stdout.
- Quality fixes from that meeting: the Whisper `initial_prompt` and the fix prompt used to
  name this thesis project (Docker, RAM, Notulis...), which biases every other meeting --
  both are generic now (add names via `EXTRA_VOCAB`). Segments are re-cut from word
  timestamps (<= 12 s, at sentence ends, speaker flicker smoothed) so the playback
  highlight follows the speech; repeated-word hallucinations ("mencoba mencoba ...") are
  dropped; a recording with fewer than 15 words skips the LLM (it used to apologize and
  invent a summary). `fix_transcript()` now asks the model only for the lines to change
  (JSON, by line number), each validated against its raw line, so fixed.txt always has
  exactly the raw lines -- the editor pairs line N with line N, and the old full rewrite
  dropped 61 of 632 lines.
- Why the highlight drifted from the video: a browser (MediaRecorder) recording stamps its
  60 ms audio packets 66 ms apart, so a 60-minute file holds only 54.5 minutes of audio.
  Whisper counts decoded samples, the video player counts container time, and the gap grew
  linearly to 5.5 minutes. `transcribe_worker._to_container_time()` maps every segment time
  through the audio packet table (ffprobe) before saving; the audio itself is untouched.
  Meetings transcribed before that fix have segment times in audio time (their last segment
  ends ~9% too early) and were remapped by hand once; do not remap one twice.
- Robot / "broken radio" audio, root cause and fix: Chrome's tab-capture audio drops samples
  when the browser is starved of CPU. Measured on all recordings: 100% complete = 0-2
  clicks/s, 96-99% = 2.5-4.4 clicks/s, the 60-minute meeting 90.9% = 14-24 clicks/s
  (and a 15 Hz robotic buzz). The missing share is also audio/video drift (0.8% missing =
  0.7 s after 100 s). `bots/audio_backup.py` therefore records the PulseAudio sink
  (`DummyOutput.monitor`) with ffmpeg next to Chrome (about 5x cleaner under CPU stress);
  when Chrome's audio is under 99.9% complete after the recording, the backup replaces the
  audio track (video copied, offset found by cross-correlation of waveform, then volume
  envelope). A healthy recording is never touched; any failure keeps the original. The
  entrypoint unloads `module-suspend-on-idle` so the sink does not sleep in silence.
  Tested with a flashing/beeping page: repaired audio 100% complete and within 0.05 s of the
  video, with and without CPU stress. NOT yet seen on a real Meet/Zoom call. The
  silence-watch AudioContext was cleared as a cause (both versions measured the same).
- Hallucination loops: a phrase repeated 3+ lines in a row (e.g. "atau bisnisnya ya?" x31) is
  collapsed to one line by `_repeat_run_keep()` in `transcribe_worker.py`; the 60-minute
  meeting had 62 such lines, removed once from its transcript, fixed transcript and segments.
- Known gap: the transcriber image has no chromadb, so re-processing a meeting that is in
  the Knowledge Base leaves its KB entry stale (logged as `No module named 'chromadb'`);
  re-index it from a worker: `knowledge_base.index_meeting(id, load_summary(id))`.
- Free Zoom/Meet accounts cap group calls (Zoom Basic about 40 min, Meet about
  60 min with 3+ people; from memory, may have changed) -- check the host account.

## Known gaps

- **`worker-2` through `worker-10` aren't actually usable yet** — the
  compose services exist, but each needs its own Google account logged in
  once via `bots/google_login.py`, and nothing routes a join to a free
  worker automatically (see "Docker multi-worker" above).
- **Early-stop detection is untested against real screens.** `record()` now
  polls each bot's `meeting_state()` every 3s and stops on "ended" (twice in
  a row) or after `EMPTY_MEETING_MINUTES` (default 10, 0 = off) alone, but
  the Zoom/Meet phrases it looks for (`_ENDED_PHRASES` in `bots/zoom.py`/
  `bots/google_meet.py`) come from the platforms' wording, not a captured
  end-of-meeting screen. The loop logic itself is tested with a fake page;
  a miss only means the recording runs to its normal time limit. Confirm on
  the first real meeting that the host ends.
- **`_jobs` is in-memory, per-process** — lost on restart, not shared
  across the 10 worker processes. Only tracks the live join/record phase
  now (see "Recorder/transcriber split"); it was never meant to survive a
  restart mid-transcription anyway, and now doesn't need to, since Redis
  holds that hand-off instead.
- **`POST /upload` isn't on the transcriber queue** — it still runs
  transcribe→fix→summarize synchronously in the API process that received
  the upload (`_process_recording()`), same as before the recorder/
  transcriber split. No live recording to protect there (no Stop Rekam
  button, no OOM risk from Chrome+whisper sharing a container since
  uploads never launch Chrome at all), so it was left alone rather than
  queued for its own sake.
- **Job queue only retries crashes, not failures.** `pipeline/job_queue.py`
  moves a claimed job into a per-transcriber processing list (`BLMOVE`) and
  `ack()`s it when done; a transcriber that dies mid-job (OOM kill, `docker
  kill`) re-queues its own unfinished job on next start, up to 3 attempts,
  then dead-letters it and marks the meeting failed (verified live by killing
  `transcriber-2` mid-job — `transcriber-1` finished it). A job that fails
  *without* crashing (recording missing, transcription error) is marked
  failed once, not retried. Nothing reads the dead-letter list yet
  (`notulis:transcription_dead`).

## To resume on another machine

```bash
cd meeting-bot
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Fill in `.env` — see `.env.example`'s own comments for where each value
comes from: `SECRET_KEY` (session signing), `OPENAI_API_KEY`, `HF_TOKEN`
(diarization — remember the pyannote model terms, see above),
`DATABASE_URL` (Postgres/Supabase), `R2_ACCOUNT_ID`/`R2_ACCESS_KEY_ID`/
`R2_SECRET_ACCESS_KEY`/`R2_BUCKET_NAME` (Cloudflare R2), `XENDIT_SECRET_KEY`/
`XENDIT_WEBHOOK_TOKEN` (billing), `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/
`SMTP_PASSWORD` (optional — email notifications stay off if left blank).
The `users`/`meetings`/etc. tables are created automatically on first
connect, nothing to migrate by hand.

For Google Meet, also start the signed-in Chrome sidecar (README has the
exact command, including `--auto-accept-this-tab-capture` — and a warning to
use a separate Google account, not your personal one). Zoom needs no extra
setup. To run the Docker multi-worker setup instead of a bare `python
app.py`, see the comments at the top of `docker-compose.yml`.

For the frontend:

```bash
cd frontend
npm install --legacy-peer-deps
npm run web
```

Opens on `http://localhost:8081`. It expects the backend at
`http://localhost:5050` by default (override with `EXPO_PUBLIC_API_URL`) —
run `python app.py` in `meeting-bot/` first, or the join/upload pages will
just show a connection error.
