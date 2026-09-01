// Placeholder data standing in for the real API (Bot Service + main
// backend) until those are wired up. Shapes mirror what those endpoints
// already return today (see meeting-bot/app.py) or will return once the
// features in Tabel 2 of the proposal are built.

export const meetings = [
  { id: "1", title: "Standup Harian Tim Produk", platform: "google_meet", date: "Hari ini", time: "09:00", durationMinutes: 32, participants: 8, status: "completed" },
  { id: "2", title: "Weekly Sync All-Hands", platform: "zoom", date: "Hari ini", time: "10:30", durationMinutes: 58, participants: 24, status: "processing" },
  { id: "3", title: "Review Sprint Q3 — Engineering", platform: "google_meet", date: "Kemarin", time: "14:00", durationMinutes: 82, participants: 12, status: "completed" },
  { id: "4", title: "Demo ke Klien Baru", platform: "zoom", date: "Kemarin", time: "16:00", durationMinutes: 45, participants: 5, status: "failed" },
  { id: "5", title: "Rapat Direksi Bulanan", platform: "google_meet", date: "23 Agt", time: "09:00", durationMinutes: 135, participants: 7, status: "completed" },
];

export const dashboardStats = {
  totalMeetings: 148,
  totalMeetingsDelta: "+12 bulan ini",
  totalDurationHours: 312,
  totalDurationDelta: "+28 jam bulan ini",
  transcriptCount: 141,
  transcriptSuccessRate: "95% sukses",
  activeMembers: 24,
  totalMembers: 26,
};

export const aiInsight = {
  headline: "2 keputusan penting dari rapat kemarin",
  detail: "Tercatat otomatis lewat ringkasan AI",
  metric: "Cari kapan saja lewat Knowledge Base",
};

export const currentUser = {
  name: "Ahmad Suharto",
  role: "Admin",
  organization: "PT Maju Bersama",
  initials: "AS",
};
