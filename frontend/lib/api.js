// Thin wrapper around the meeting-bot Flask API (see meeting-bot/app.py).
// EXPO_PUBLIC_API_URL lets this point at a deployed bot service later;
// defaults to the local dev server.
const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || "http://localhost:5050";

async function handleResponse(res) {
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || `Request gagal (${res.status})`);
  }
  return data;
}

// Runs the bot's full pipeline (transcribe -> fix -> summarize) on an
// already-recorded file. Can take several minutes for long recordings.
// numSpeakers is optional — the uploader's best guess at how many people are
// in the recording, passed through to improve diarization (see transcribe()).
export async function uploadAudio(file, numSpeakers) {
  const formData = new FormData();
  formData.append("file", file);
  if (numSpeakers) formData.append("num_speakers", numSpeakers);
  const res = await fetch(`${API_BASE_URL}/upload`, { method: "POST", body: formData });
  return handleResponse(res);
}

// Starts a join in the background and returns immediately with a job_id —
// the bot can be in the meeting for as long as the meeting runs, so this
// doesn't block on that (unlike uploadAudio). Poll getJobStatus(jobId) for
// progress, and stopJob(jobId) to end the recording early.
export async function startJoinMeeting(platform, url, name, numSpeakers) {
  const endpoint = platform === "zoom" ? "/zoom/join" : "/google/join";
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, name, num_speakers: numSpeakers || null }),
  });
  return handleResponse(res);
}

// {status: "joining"|"recording"|"stopping"|"processing"|"done"|"failed",
// elapsed_seconds?, result?, error?} — see GET /jobs/<id> in app.py.
export async function getJobStatus(jobId) {
  const res = await fetch(`${API_BASE_URL}/jobs/${encodeURIComponent(jobId)}`);
  return handleResponse(res);
}

// Ends the recording early — the pipeline still runs afterward on whatever
// got recorded so far, same as if the max duration had been reached.
export async function stopJob(jobId) {
  const res = await fetch(`${API_BASE_URL}/jobs/${encodeURIComponent(jobId)}/stop`, { method: "POST" });
  return handleResponse(res);
}

// Real meetings recorded so far (newest first) — see GET /meetings.
export async function listMeetings() {
  const res = await fetch(`${API_BASE_URL}/meetings`);
  return handleResponse(res);
}

// One past meeting's full detail — transcript/fixed_transcript/summary read
// back from disk (see GET /meetings/<id> in app.py).
export async function getMeeting(id) {
  const res = await fetch(`${API_BASE_URL}/meetings/${encodeURIComponent(id)}`);
  return handleResponse(res);
}

// Saves the user-approved/edited transcript as this meeting's fixed
// transcript and re-runs the summary against it — see POST
// /meetings/<id>/transcript in app.py. lineSpeakers/lineTexts are optional:
// one entry per transcript line, same order as segments.json — when given
// and their length matches, also patches those speakers/text in
// segments.json so the synced Transkrip tab shows the same correction
// instead of the original ASR output. Returns
// {fixed_transcript, summary, segments?} or {fixed_transcript, summary_error}.
export async function updateTranscript(id, transcript, lineSpeakers, lineTexts) {
  const res = await fetch(`${API_BASE_URL}/meetings/${encodeURIComponent(id)}/transcript`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript, line_speakers: lineSpeakers, line_texts: lineTexts }),
  });
  return handleResponse(res);
}

// Flips one action item's done flag — see POST
// /meetings/<id>/action-items/<index>/toggle in app.py. Returns the updated
// summary object.
export async function toggleActionItem(id, index) {
  const res = await fetch(`${API_BASE_URL}/meetings/${encodeURIComponent(id)}/action-items/${index}/toggle`, {
    method: "POST",
  });
  return handleResponse(res);
}

// Current subscription — {id, plan: "free"|"pro"|"team", status, current_period_end}.
// Always returns something (Free with no row yet is the default, not an
// error) — see GET /billing/status in app.py.
export async function getBillingStatus() {
  const res = await fetch(`${API_BASE_URL}/billing/status`);
  return handleResponse(res);
}

// Starts a Xendit subscription checkout for "pro" or "team" — returns
// {checkout_url}; redirect the browser there. The plan only actually
// changes once the user finishes linking a payment method on that page and
// Xendit's webhook confirms it (see POST /billing/webhook in app.py) — this
// call alone doesn't upgrade anything.
export async function startCheckout(plan) {
  const res = await fetch(`${API_BASE_URL}/billing/checkout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plan }),
  });
  return handleResponse(res);
}

// Cancels the current paid subscription (downgrades to Free immediately).
export async function cancelSubscription() {
  const res = await fetch(`${API_BASE_URL}/billing/cancel`, { method: "POST" });
  return handleResponse(res);
}

// URL for a meeting's recording file — for <video>/<audio> playback or a
// direct download link, not fetched as JSON. See GET /meetings/<id>/recording.
export function getRecordingUrl(id) {
  return `${API_BASE_URL}/meetings/${encodeURIComponent(id)}/recording`;
}
