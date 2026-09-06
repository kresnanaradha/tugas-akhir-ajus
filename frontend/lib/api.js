// Thin wrapper around the meeting-bot Flask API (see meeting-bot/app.py).
// EXPO_PUBLIC_API_URL lets this point at a deployed bot service later;
// defaults to the local dev server.
const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || "http://localhost:5000";

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
// /meetings/<id>/transcript in app.py. lineSpeakers is optional: one label
// (or null) per transcript line, same order as segments.json — when given
// and its length matches, also renames those speakers in segments.json so
// the synced Transkrip tab picks up the same names. Returns
// {fixed_transcript, summary, segments?} or {fixed_transcript, summary_error}.
export async function updateTranscript(id, transcript, lineSpeakers) {
  const res = await fetch(`${API_BASE_URL}/meetings/${encodeURIComponent(id)}/transcript`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript, line_speakers: lineSpeakers }),
  });
  return handleResponse(res);
}

// URL for a meeting's recording file — for <video>/<audio> playback or a
// direct download link, not fetched as JSON. See GET /meetings/<id>/recording.
export function getRecordingUrl(id) {
  return `${API_BASE_URL}/meetings/${encodeURIComponent(id)}/recording`;
}
