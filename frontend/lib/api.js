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

// credentials: "include" on every call (not just the /auth/* ones) — the
// session cookie /auth/login sets has to ride along on every request that
// might hit a login_required/super_admin_required route, and there's no
// harm sending it on the ones that don't check it (yet).
function apiFetch(path, options) {
  return fetch(`${API_BASE_URL}${path}`, { ...options, credentials: "include" });
}

// {id, email, name, role: "user"|"super_admin"}
export async function register(email, password, name) {
  const res = await apiFetch("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, name }),
  });
  return handleResponse(res);
}

export async function login(email, password) {
  const res = await apiFetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return handleResponse(res);
}

export async function logout() {
  const res = await apiFetch("/auth/logout", { method: "POST" });
  return handleResponse(res);
}

// The signed-in user, or throws (401) if there isn't one — callers use this
// to decide whether to redirect to /login.
export async function getMe() {
  const res = await apiFetch("/auth/me");
  return handleResponse(res);
}

// Runs the bot's full pipeline (transcribe -> fix -> summarize) on an
// already-recorded file. Can take several minutes for long recordings.
// numSpeakers is optional — the uploader's best guess at how many people are
// in the recording, passed through to improve diarization (see transcribe()).
export async function uploadAudio(file, numSpeakers) {
  const formData = new FormData();
  formData.append("file", file);
  if (numSpeakers) formData.append("num_speakers", numSpeakers);
  const res = await apiFetch("/upload", { method: "POST", body: formData });
  return handleResponse(res);
}

// Starts a join in the background and returns immediately with a job_id —
// the bot can be in the meeting for as long as the meeting runs, so this
// doesn't block on that (unlike uploadAudio). Poll getJobStatus(jobId) for
// progress, and stopJob(jobId) to end the recording early.
export async function startJoinMeeting(platform, url, name, numSpeakers) {
  const endpoint = platform === "zoom" ? "/zoom/join" : "/google/join";
  const res = await apiFetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, name, num_speakers: numSpeakers || null }),
  });
  return handleResponse(res);
}

// {status: "joining"|"recording"|"stopping"|"processing"|"done"|"failed",
// elapsed_seconds?, result?, error?} — see GET /jobs/<id> in app.py.
export async function getJobStatus(jobId) {
  const res = await apiFetch(`/jobs/${encodeURIComponent(jobId)}`);
  return handleResponse(res);
}

// Ends the recording early — the pipeline still runs afterward on whatever
// got recorded so far, same as if the max duration had been reached.
export async function stopJob(jobId) {
  const res = await apiFetch(`/jobs/${encodeURIComponent(jobId)}/stop`, { method: "POST" });
  return handleResponse(res);
}

// Real meetings recorded so far (newest first) — see GET /meetings.
export async function listMeetings() {
  const res = await apiFetch("/meetings");
  return handleResponse(res);
}

// One past meeting's full detail — transcript/fixed_transcript/summary read
// back from disk (see GET /meetings/<id> in app.py).
export async function getMeeting(id) {
  const res = await apiFetch(`/meetings/${encodeURIComponent(id)}`);
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
  const res = await apiFetch(`/meetings/${encodeURIComponent(id)}/transcript`, {
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
  const res = await apiFetch(`/meetings/${encodeURIComponent(id)}/action-items/${index}/toggle`, {
    method: "POST",
  });
  return handleResponse(res);
}

// Current subscription — {id, plan: "free"|"pro"|"team", status, current_period_end}.
// Always returns something (Free with no row yet is the default, not an
// error) — see GET /billing/status in app.py.
export async function getBillingStatus() {
  const res = await apiFetch("/billing/status");
  return handleResponse(res);
}

// Starts a Xendit subscription checkout for "pro" or "team" — returns
// {checkout_url}; redirect the browser there. The plan only actually
// changes once the user finishes linking a payment method on that page and
// Xendit's webhook confirms it (see POST /billing/webhook in app.py) — this
// call alone doesn't upgrade anything.
export async function startCheckout(plan) {
  const res = await apiFetch("/billing/checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plan }),
  });
  return handleResponse(res);
}

// Cancels the current paid subscription (downgrades to Free immediately).
export async function cancelSubscription() {
  const res = await apiFetch("/billing/cancel", { method: "POST" });
  return handleResponse(res);
}

// URL for a meeting's recording file — for <video>/<audio> playback or a
// direct download link, not fetched as JSON. See GET /meetings/<id>/recording.
export function getRecordingUrl(id) {
  return `${API_BASE_URL}/meetings/${encodeURIComponent(id)}/recording`;
}

// Super admin dashboard: meeting volume, active subscriptions + MRR, OpenAI
// cost (real tracked usage, see openai_cost.since — not retroactive),
// R2 storage used, total registered users. 403s for a non-super_admin user,
// 401 if not logged in at all — see GET /admin/stats in app.py.
export async function getAdminStats() {
  const res = await apiFetch("/admin/stats");
  return handleResponse(res);
}

// URL for the formal PDF report — for a plain link/anchor, not fetched as
// JSON (the browser handles the download). See GET /admin/export.
export function getAdminExportUrl() {
  return `${API_BASE_URL}/admin/export`;
}

// This user's own meeting stats — volume, platform breakdown, total
// duration (see GET /reports/stats in app.py). Same shape of aggregation as
// getAdminStats(), just scoped to "my meetings" instead of the whole system.
export async function getReportStats() {
  const res = await apiFetch("/reports/stats");
  return handleResponse(res);
}

// URL for this user's own PDF report — for a plain link/anchor, not fetched
// as JSON (the browser handles the download). See GET /reports/export.
export function getReportExportUrl() {
  return `${API_BASE_URL}/reports/export`;
}

// RAG Knowledge Base search — returns {answer, results}. `answer` is one
// GPT-synthesized paragraph grounded only in the matched chunks (null if
// synthesis failed or nothing matched); `results` is those matched chunks
// themselves (each {meeting_id, meeting_title, meeting_created_at,
// meeting_platform, kind, text, similarity}), ranked closest-first — always
// populated so the UI can show sources even if `answer` is null. One query
// in, one answer out: no conversation history is kept or sent anywhere, by
// design — see GET /knowledge-base/search in app.py.
export async function searchKnowledgeBase(query) {
  const res = await apiFetch(`/knowledge-base/search?q=${encodeURIComponent(query)}`);
  return handleResponse(res);
}
