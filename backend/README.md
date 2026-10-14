# Notulis backend

Flask API plus the bots. A bot joins a Google Meet or Zoom call as a guest (Playwright), records the tab,
and the recording is transcribed with speaker labels (whisperx), cleaned up and summarized (GPT-4o mini). On
top of that sits the rest of the product: login and roles, meeting history, a Knowledge Base, PDF reports,
Xendit billing, teams and the admin dashboard. `../CLAUDE.md` is the status file (what is built, what to watch
out for), this one is how to run it.

Join flow adapted from [screenappai/meeting-bot](https://github.com/screenappai/meeting-bot) (MIT license).

## Layout

- `app.py`: every route (auth, meetings, billing, teams, admin, reports) and the join jobs
- `bots/`: `base.py` records (getDisplayMedia + MediaRecorder), `google_meet.py` / `zoom.py` join the call,
  `audio_backup.py` repairs damaged audio, `google_login.py` saves a Google session
- `pipeline/`: stores (Postgres), R2 storage, `process.py` (transcribe -> fix -> summarize -> email), summaries,
  Knowledge Base, PDFs, mailer, Redis queue
- `transcriber_service.py`: the worker loop of the transcriber containers
- `tests/`: plain scripts, no framework

A recording is uploaded to R2 when it ends and queued in Redis, a transcriber picks it up (separate container
so Chrome and whisper never share memory). `POST /upload` skips the queue and runs the pipeline in the API process.

## Setup

```bash
cp .env.example .env     # then fill it in, every value says where it comes from
docker compose up -d redis transcriber-1 worker-1
```

Without Docker: `pip install -r requirements.txt`, `playwright install chromium`, `python app.py` (also needs
`ffmpeg` on PATH, and Redis plus `python transcriber_service.py` if you want recordings transcribed).

The tables are created on the first connection, nothing to migrate. Code is baked into the images, so after a
change: `docker compose build worker-1 && docker compose up -d --force-recreate worker-1`. Run only ONE
transcriber for long meetings (`docker compose stop transcriber-2`), a long job needs ~6GB.

### Google Meet needs a saved login

Google refuses anonymous automated joins and also refuses to sign in a browser that Playwright controls, so the
bot never logs in. A human does it once, on the host (not in Docker):

```bash
python -m bots.google_login
```

It opens a real Chrome, you sign in to a separate Google account (not your own), press Enter, and the session is
saved to `GOOGLE_AUTH_STATE_PATH` (default `auth/google.json`). Run it again when joins start failing with a login
redirect. For more workers, one account and one file each (`auth/worker-N.json`, see `docker-compose.yml`).
Zoom needs none of this.

### First admin

`python create_super_admin.py` creates the first super admin. Registering always makes a plain user.

## Try it

```bash
curl -X POST http://localhost:5050/zoom/join -H "Content-Type: application/json" -b cookies.txt \
  -d '{"url": "https://zoom.us/j/1234567890", "name": "Notulis Bot"}'
```

Needs a login cookie (`POST /auth/login`). It returns `{"job_id": ...}` right away: poll `GET /jobs/<id>` while
the bot joins and records, then `GET /meetings/<id>` once it is processing or done. `POST /jobs/<id>/stop`
ends the recording early.

## Tests

```bash
docker compose exec -T worker-1 python -m tests.test_routes      # also test_pdf, test_mailer, test_process, test_free_quota_flow
```

They use fake data (no database, R2 or model calls). Joining real meetings can only be tried by hand.

## What tends to break

- **Google detection.** An unauthenticated or Playwright-driven login gets "You can't join this video call"
  or "This browser or app may not be secure". It keeps changing, expect to adjust.
- **Meet and Zoom page text.** The bots rely on button text and aria-labels from the current web UI, and the
  phrases that detect "meeting ended" come from their wording, not from captured screens. Check them first when
  a join or an early stop stops working.
- **Zoom's bot check** (`playwright-stealth`) passes most of the time. Repeated joins from one IP in a short
  window make it suspicious, space out test runs.
- **Zoom's join path is simplified**: it goes straight to `/wc/join/<id>` and has no fallback chain for
  meetings that don't land there.

## Limits

- One recording per worker at a time (the whole display is captured, two bots would record each other).
  Nothing sends a join to a free worker yet, and only worker-1 has a Google login.
- The recording is the whole virtual display, not just the tab. Fine in a container, where nothing else is on it.
- `num_speakers` is a guess from the user ("Perkiraan Jumlah Peserta"), there is no reliable way to read the real
  count from Meet or Zoom. It helps diarization a lot.
