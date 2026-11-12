// pembungkus tipis untuk API backend (backend/app.py). EXPO_PUBLIC_API_URL mengarahkannya ke backend yang di-deploy, defaultnya lokal
const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || "http://localhost:5050";

// satu-satunya tempat yang memanggil fetch. credentials: "include" supaya cookie sesi selalu ikut. body objek dikirim
// sebagai JSON, FormData (upload) apa adanya. Respons bukan 2xx dilempar sebagai Error dengan .status
async function api(path, method = "GET", body) {
  const isJson = body !== undefined && !(body instanceof FormData);
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    credentials: "include",
    headers: isJson ? { "Content-Type": "application/json" } : undefined,
    body: isJson ? JSON.stringify(body) : body,
  });
  const data = await res.json();
  if (!res.ok) {
    const err = new Error(data.error || `Request gagal (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
}

const enc = encodeURIComponent;
const meeting = (id) => `/meetings/${enc(id)}`;

// kartu paket di sidebar mendengarkan event ini, jadi diperbarui begitu ada yang bisa mengubah paket
// (masuk atau keluar team, membatalkan) tanpa menunggu pindah halaman
const changesPlan = async (promise) => {
  const result = await promise;
  if (typeof window !== "undefined") window.dispatchEvent(new Event("notulis:plan-changed"));
  return result;
};

// --- akun. {id, email, name, role: "user"|"super_admin"}
export const register = (email, password, name) => api("/auth/register", "POST", { email, password, name });
export const login = (email, password) => api("/auth/login", "POST", { email, password });
export const forgotPassword = (email) => api("/auth/forgot", "POST", { email });
export const resetPassword = (token, password) => api("/auth/reset", "POST", { token, password });
export const logout = () => api("/auth/logout", "POST");
// user yang sedang login, atau melempar error 401 (pemanggil lalu mengalihkan ke /login)
export const getMe = () => api("/auth/me");
// "hapus akun" menonaktifkan (rapat menunjuk ke user) dan membersihkan sesi
export const deactivateAccount = () => api("/auth/me/deactivate", "POST");
// kirim hanya yang berubah: name, email, phone, email_notifications
export const updateProfile = (fields) => api("/auth/me", "PATCH", fields);
export const changePassword = (currentPassword, newPassword) =>
  api("/auth/me/password", "POST", { current_password: currentPassword, new_password: newPassword });

// --- rekam dan unggah
// menjalankan pipeline pada file yang sudah direkam, bisa memakan menit. numSpeakers adalah tebakan pengunggah, membantu diarization
export function uploadAudio(file, numSpeakers) {
  const form = new FormData();
  form.append("file", file);
  if (numSpeakers) form.append("num_speakers", numSpeakers);
  return api("/upload", "POST", form);
}
// memasukkan join ke antrean dan langsung mengembalikan {job_id}. Pantau getJobStatus, stopJob mengakhiri rekaman lebih awal
export const startJoinMeeting = (platform, url, name, numSpeakers) =>
  api(platform === "zoom" ? "/zoom/join" : "/google/join", "POST", { url, name, num_speakers: numSpeakers || null });
// {status: "queued"|"joining"|"recording"|"stopping"|"processing"|"failed", elapsed_seconds?, error?}. 404 berarti job selesai
export const getJobStatus = (jobId) => api(`/jobs/${enc(jobId)}`);
// pipeline tetap jalan atas apa yang sudah terekam, sama seperti kalau durasi maksimum tercapai
export const stopJob = (jobId) => api(`/jobs/${enc(jobId)}/stop`, "POST");

// --- rapat
export const listMeetings = () => api("/meetings");
// transcript, fixed_transcript, summary, segments dibaca dari R2
export const getMeeting = (id) => api(meeting(id));
// simpan transkrip yang dikoreksi lalu ringkas ulang. lineSpeakers / lineTexts (satu per baris, urutan sama dengan segments.json)
// ikut memperbaiki tab Transkrip. Mengembalikan {fixed_transcript, summary, segments?} atau {fixed_transcript, summary_error}
export const updateTranscript = (id, transcript, lineSpeakers, lineTexts) =>
  api(`${meeting(id)}/transcript`, "POST", { transcript, line_speakers: lineSpeakers, line_texts: lineTexts });
// kirim rekaman ke transkriber: yang disimpan tanpa AI ("limited") atau proses ulang yang gagal ("failed")
export const processMeeting = (id) => api(`${meeting(id)}/process`, "POST");
// ringkasan singkat untuk rapat yang diringkas sebelum kolom itu ada, mengembalikan ringkasan baru
export const generateShortSummary = (id) => api(`${meeting(id)}/short-summary`, "POST");
// nilai yang diinginkan, bukan membalik, supaya klik cepat tidak saling membatalkan
export const toggleActionItem = (id, index, done) => api(`${meeting(id)}/action-items/${index}/toggle`, "POST", { done });
// ganti seluruh daftar ({task, assignee, due, done}[]): satu panggilan untuk edit, tambah, dan hapus
export const replaceActionItems = (id, items) => api(`${meeting(id)}/action-items`, "PUT", { items });
// hapus permanen (R2, Knowledge Base, DB). Hanya pemilik atau super admin, ditolak selagi merekam/memproses
export const deleteMeeting = (id) => api(meeting(id), "DELETE");
// hanya ringkasan eksekutif dan keputusan utama yang diindeks
export const setKnowledgeBase = (id, enabled) => api(`${meeting(id)}/knowledge-base`, "POST", { enabled });
export const shareMeetingWithTeam = (id, enabled) => api(`${meeting(id)}/share-team`, "POST", { enabled });
// URL untuk <video> atau tautan unduh, bukan diambil sebagai JSON
export const getRecordingUrl = (id) => `${API_BASE_URL}${meeting(id)}/recording`;
// {answer, results}: answer satu paragraf dari potongan yang cocok (null kalau gagal atau kosong), results potongannya
// {meeting_id, meeting_title, meeting_created_at, meeting_platform, kind, text, similarity}
export const searchKnowledgeBase = (query) => api(`/knowledge-base/search?q=${enc(query)}`);

// --- billing. Free tanpa baris tetap mengembalikan status
export const getBillingStatus = () => api("/billing/status");
// checkout Xendit untuk "pro" atau "team", mengembalikan {checkout_url}. Paket berubah setelah webhook mengonfirmasi pembayaran
export const startCheckout = (plan) => api("/billing/checkout", "POST", { plan });
export const cancelPendingCheckout = () => changesPlan(api("/billing/checkout/cancel", "POST"));
// turun ke Free di akhir periode
export const cancelSubscription = () => changesPlan(api("/billing/cancel", "POST"));

// --- super admin (403 untuk yang lain)
export const getAdminStats = () => api("/admin/stats");
// worker perekam yang hidup: [{id, platforms, busy, google_expired}]
export const getAdminWorkers = () => api("/admin/workers");
export const getAdminExportUrl = () => `${API_BASE_URL}/admin/export`;
export const listUsers = () => api("/admin/users");
export const createUser = ({ name, email, password, role }) => api("/admin/users", "POST", { name, email, password, role });
// fields: name, role, atau active (menonaktifkan menggantikan menghapus)
export const updateUser = (id, fields) => api(`/admin/users/${enc(id)}`, "PATCH", fields);
export const resetUserPassword = (id, password) => api(`/admin/users/${enc(id)}/reset-password`, "POST", { password });

// --- laporan dan perbandingan
// bentuk sama dengan getAdminStats, hanya untuk rapat user ini
export const getReportStats = () => api("/reports/stats");
// pemakaian team si pemanggil, null kalau tidak punya team
export const getReportTeam = () => api("/reports/team");
// panggilan terpisah karena lambat saat cache dingin
export const getReportActionItems = () => api("/reports/action-items");
export const getReportExportUrl = () => `${API_BASE_URL}/reports/export`;
export const getComparisonAnalysis = (a, b) => api(`/perbandingan/analisis?a=${enc(a)}&b=${enc(b)}`);
export const getComparisonExportUrl = (a, b) => `${API_BASE_URL}/perbandingan/export?a=${enc(a)}&b=${enc(b)}`;

// --- team
// team si pemanggil beserta anggotanya, atau null
export const getMyTeam = () => api("/teams/me");
export const createTeam = (name) => api("/teams", "POST", { name });
export const renameTeam = (teamId, name) => api(`/teams/${enc(teamId)}`, "PATCH", { name });
// hanya admin. Tanpa email: hanya tautan, tidak ada email terkirim. Mengembalikan {token, invite_url, expires_at}
export const inviteToTeam = (email) => api("/teams/invite", "POST", { email: email || null });
// {team_name} untuk halaman gabung sebelum user memutuskan
export const previewTeamInvite = (token) => api(`/teams/invite/${enc(token)}`);
export const joinTeam = (token) => changesPlan(api("/teams/join", "POST", { token }));
export const leaveTeam = () => changesPlan(api("/teams/leave", "POST"));
export const removeTeamMember = (userId) => api(`/teams/members/${enc(userId)}`, "DELETE");
export const updateTeamMemberRole = (userId, role) => api(`/teams/members/${enc(userId)}`, "PATCH", { role });
