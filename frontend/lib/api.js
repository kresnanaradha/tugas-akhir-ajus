// pembungkus tipis untuk API backend (backend/app.py). EXPO_PUBLIC_API_URL mengarahkannya ke backend yang di-deploy, defaultnya lokal
const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || "http://localhost:5050";

async function handleResponse(res) {
  const data = await res.json();
  if (!res.ok) {
    const err = new Error(data.error || `Request gagal (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
}

// credentials: "include" di setiap panggilan supaya cookie sesi selalu ikut
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

export async function forgotPassword(email) {
  const res = await apiFetch("/auth/forgot", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  return handleResponse(res);
}

export async function resetPassword(token, password) {
  const res = await apiFetch("/auth/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, password }),
  });
  return handleResponse(res);
}

export async function logout() {
  const res = await apiFetch("/auth/logout", { method: "POST" });
  return handleResponse(res);
}

// User yang sedang login, atau melempar error (401) kalau tidak ada - dipakai pemanggil
// untuk memutuskan apakah dialihkan ke /login.
export async function getMe() {
  const res = await apiFetch("/auth/me");
  return handleResponse(res);
}

// "hapus akun" menonaktifkan (rapat menunjuk ke user) dan membersihkan sesi
export async function deactivateAccount() {
  const res = await apiFetch("/auth/me/deactivate", { method: "POST" });
  return handleResponse(res);
}

// Edit profil sendiri (name, email, phone, email_notifications -
// kirim hanya yang berubah) - lihat PATCH /auth/me.
export async function updateProfile(fields) {
  const res = await apiFetch("/auth/me", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
  return handleResponse(res);
}

// Ganti password sendiri, butuh password saat ini - lihat
// POST /auth/me/password.
export async function changePassword(currentPassword, newPassword) {
  const res = await apiFetch("/auth/me/password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  return handleResponse(res);
}

// menjalankan pipeline pada file yang sudah direkam, bisa memakan menit. numSpeakers adalah tebakan pengunggah, membantu diarization
export async function uploadAudio(file, numSpeakers) {
  const formData = new FormData();
  formData.append("file", file);
  if (numSpeakers) formData.append("num_speakers", numSpeakers);
  const res = await apiFetch("/upload", { method: "POST", body: formData });
  return handleResponse(res);
}

// memulai join di latar belakang dan langsung mengembalikan job_id (bot tinggal selama rapat berjalan). Pantau
// getJobStatus(jobId), stopJob(jobId) mengakhiri rekaman lebih awal
export async function startJoinMeeting(platform, url, name, numSpeakers) {
  const endpoint = platform === "zoom" ? "/zoom/join" : "/google/join";
  const res = await apiFetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, name, num_speakers: numSpeakers || null }),
  });
  return handleResponse(res);
}

// {status: "joining"|"recording"|"stopping"|"processing"|"failed",
// elapsed_seconds?, error?} - lihat GET /jobs/<id> di app.py. 404 berarti job selesai atau tidak dikenal proses itu.
export async function getJobStatus(jobId) {
  const res = await apiFetch(`/jobs/${encodeURIComponent(jobId)}`);
  return handleResponse(res);
}

// Mengakhiri rekaman lebih awal - pipeline tetap jalan sesudahnya atas apa yang
// sudah terekam, sama seperti kalau durasi maksimum tercapai.
export async function stopJob(jobId) {
  const res = await apiFetch(`/jobs/${encodeURIComponent(jobId)}/stop`, { method: "POST" });
  return handleResponse(res);
}

// Rapat yang sudah direkam (terbaru dulu) - lihat GET /meetings.
export async function listMeetings() {
  const res = await apiFetch("/meetings");
  return handleResponse(res);
}

// Detail lengkap satu rapat lama - transcript/fixed_transcript/summary dibaca
// dari R2 (lihat GET /meetings/<id> di app.py).
export async function getMeeting(id) {
  const res = await apiFetch(`/meetings/${encodeURIComponent(id)}`);
  return handleResponse(res);
}

// menyimpan transkrip yang dikoreksi dan membuat ulang ringkasan darinya. lineSpeakers / lineTexts (satu per baris, urutan sama dengan
// segments.json) juga memperbaiki pembicara dan teks di segments.json supaya tab Transkrip menampilkan koreksinya.
// Mengembalikan {fixed_transcript, summary, segments?} atau {fixed_transcript, summary_error}
export async function updateTranscript(id, transcript, lineSpeakers, lineTexts) {
  const res = await apiFetch(`/meetings/${encodeURIComponent(id)}/transcript`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript, line_speakers: lineSpeakers, line_texts: lineTexts }),
  });
  return handleResponse(res);
}

// mengirim rekaman yang disimpan tanpa AI (status "limited") ke transkriber
export async function processMeeting(id) {
  const res = await apiFetch(`/meetings/${encodeURIComponent(id)}/process`, { method: "POST" });
  return handleResponse(res);
}

// menambahkan ringkasan singkat ke rapat yang diringkas sebelum kolom itu ada, mengembalikan ringkasan baru
export async function generateShortSummary(id) {
  const res = await apiFetch(`/meetings/${encodeURIComponent(id)}/short-summary`, { method: "POST" });
  return handleResponse(res);
}

// mengatur status selesai satu action item (nilai yang diinginkan, bukan membalik, supaya klik cepat tidak saling membatalkan)
export async function toggleActionItem(id, index, done) {
  const res = await apiFetch(`/meetings/${encodeURIComponent(id)}/action-items/${index}/toggle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ done }),
  });
  return handleResponse(res);
}

// Mengganti seluruh daftar action item ({task, assignee, due, done}[]) - satu
// panggilan untuk edit, tambah, dan hapus. Lihat PUT /meetings/<id>/action-items.
export async function replaceActionItems(id, items) {
  const res = await apiFetch(`/meetings/${encodeURIComponent(id)}/action-items`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
  return handleResponse(res);
}

// Menghapus rapat permanen (file R2, potongan KB, baris DB) - hanya pemilik atau
// super admin, ditolak selagi masih merekam/memproses.
export async function deleteMeeting(id) {
  const res = await apiFetch(`/meetings/${encodeURIComponent(id)}`, { method: "DELETE" });
  return handleResponse(res);
}

// Memasukkan/mengeluarkan rapat dari Knowledge Base (hanya ringkasan eksekutif +
// keputusan utama yang diindeks) - lihat POST /meetings/<id>/knowledge-base.
export async function setKnowledgeBase(id, enabled) {
  const res = await apiFetch(`/meetings/${encodeURIComponent(id)}/knowledge-base`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  return handleResponse(res);
}

// langganan saat ini {id, plan, status, current_period_end}. Selalu mengembalikan sesuatu (Free tanpa baris adalah default)
export async function getBillingStatus() {
  const res = await apiFetch("/billing/status");
  return handleResponse(res);
}

// kartu paket di sidebar mendengarkan event ini, jadi diperbarui begitu ada yang bisa mengubah paket
// (masuk atau keluar team, membatalkan) tanpa menunggu pindah halaman
const changesPlan = async (promise) => {
  const result = await promise;
  if (typeof window !== "undefined") window.dispatchEvent(new Event("notulis:plan-changed"));
  return result;
};

export async function cancelPendingCheckout() {
  const res = await apiFetch("/billing/checkout/cancel", { method: "POST" });
  return changesPlan(handleResponse(res));
}

// memulai checkout Xendit untuk "pro" atau "team" dan mengembalikan {checkout_url} untuk tujuan redirect. Paket baru berubah setelah
// webhook mengonfirmasi pembayaran
export async function startCheckout(plan) {
  const res = await apiFetch("/billing/checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plan }),
  });
  return handleResponse(res);
}

// Membatalkan langganan berbayar saat ini (turun ke Free di akhir periode).
export async function cancelSubscription() {
  const res = await apiFetch("/billing/cancel", { method: "POST" });
  return changesPlan(handleResponse(res));
}

// URL file rekaman rapat - untuk pemutaran <video>/<audio> atau tautan
// unduh langsung, bukan diambil sebagai JSON. Lihat GET /meetings/<id>/recording.
export function getRecordingUrl(id) {
  return `${API_BASE_URL}/meetings/${encodeURIComponent(id)}/recording`;
}

// angka dashboard admin (403 untuk selain super admin)
export async function getAdminStats() {
  const res = await apiFetch("/admin/stats");
  return handleResponse(res);
}

// Manajemen user super admin - lihat /admin/users* di app.py.
export async function listUsers() {
  return handleResponse(await apiFetch("/admin/users"));
}

export async function createUser({ name, email, password, role }) {
  const res = await apiFetch("/admin/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password, role }),
  });
  return handleResponse(res);
}

// fields: salah satu dari {name, role, active} - menonaktifkan menggantikan menghapus.
export async function updateUser(id, fields) {
  const res = await apiFetch(`/admin/users/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
  return handleResponse(res);
}

export async function resetUserPassword(id, password) {
  const res = await apiFetch(`/admin/users/${encodeURIComponent(id)}/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  return handleResponse(res);
}

// URL laporan PDF resmi - untuk tautan/anchor biasa, bukan diambil sebagai
// JSON (browser yang menangani unduhan). Lihat GET /admin/export.
export function getAdminExportUrl() {
  return `${API_BASE_URL}/admin/export`;
}

// statistik rapat milik user ini, bentuk sama dengan getAdminStats() untuk rapat mereka saja
export async function getReportStats() {
  const res = await apiFetch("/reports/stats");
  return handleResponse(res);
}

// semua action item di seluruh rapat user ini, panggilan terpisah karena lambat saat dingin
// pemakaian team si pemanggil, null kalau mereka tidak punya team
export async function getReportTeam() {
  const res = await apiFetch("/reports/team");
  return handleResponse(res);
}

export async function getReportActionItems() {
  return handleResponse(await apiFetch("/reports/action-items"));
}

// URL laporan PDF milik user sendiri - untuk tautan/anchor biasa, bukan diambil
// sebagai JSON (browser yang menangani unduhan). Lihat GET /reports/export.
export function getReportExportUrl() {
  return `${API_BASE_URL}/reports/export`;
}

// URL ekspor PDF halaman Perbandingan Rapat - lihat GET /perbandingan/export.
export async function getComparisonAnalysis(a, b) {
  const res = await apiFetch(`/perbandingan/analisis?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
  return handleResponse(res);
}

export function getComparisonExportUrl(meetingIdA, meetingIdB) {
  return `${API_BASE_URL}/perbandingan/export?a=${encodeURIComponent(meetingIdA)}&b=${encodeURIComponent(meetingIdB)}`;
}

// Team si pemanggil + daftar anggota, atau null kalau tidak punya - lihat GET /teams/me.
export async function getMyTeam() {
  return handleResponse(await apiFetch("/teams/me"));
}

export async function createTeam(name) {
  const res = await apiFetch("/teams", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return handleResponse(res);
}

export async function renameTeam(teamId, name) {
  const res = await apiFetch(`/teams/${encodeURIComponent(teamId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return handleResponse(res);
}

// Hanya admin. `email` opsional - hilangkan untuk mendapat tautan yang bisa dibagikan tanpa
// mengirim email. Mengembalikan {token, invite_url, expires_at}.
export async function inviteToTeam(email) {
  const res = await apiFetch("/teams/invite", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: email || null }),
  });
  return handleResponse(res);
}

// {team_name} untuk ditampilkan halaman gabung sebelum user memutuskan.
export async function previewTeamInvite(token) {
  return handleResponse(await apiFetch(`/teams/invite/${encodeURIComponent(token)}`));
}

export async function joinTeam(token) {
  const res = await apiFetch("/teams/join", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
  return changesPlan(handleResponse(res));
}

// Keluar mandiri (peran apa pun) - efek di server sama dengan admin
// mengeluarkan user yang sama lewat removeTeamMember().
export async function leaveTeam() {
  return changesPlan(handleResponse(await apiFetch("/teams/leave", { method: "POST" })));
}

export async function removeTeamMember(userId) {
  return handleResponse(await apiFetch(`/teams/members/${encodeURIComponent(userId)}`, { method: "DELETE" }));
}

export async function updateTeamMemberRole(userId, role) {
  const res = await apiFetch(`/teams/members/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role }),
  });
  return handleResponse(res);
}

// Opt in berbagi ke team per rapat - lihat POST /meetings/<id>/share-team.
export async function shareMeetingWithTeam(id, enabled) {
  const res = await apiFetch(`/meetings/${encodeURIComponent(id)}/share-team`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  return handleResponse(res);
}

// Pencarian Knowledge Base: {answer, results}. `answer` adalah satu paragraf singkat dari potongan yang cocok (null kalau gagal atau
// tidak ada yang cocok), `results` adalah potongan itu {meeting_id, meeting_title, meeting_created_at, meeting_platform, kind, text, similarity}
export async function searchKnowledgeBase(query) {
  const res = await apiFetch(`/knowledge-base/search?q=${encodeURIComponent(query)}`);
  return handleResponse(res);
}
