-- Jalankan INI DULU di SQL Editor Supabase. Hanya SELECT, tidak mengubah data.
-- Tiap baris hasil = satu baris yatim yang akan membuat FK di 001_fk_rls.sql gagal.
-- Dua jenis pertama (usage dan meeting_viewers) dibersihkan otomatis oleh 001_fk_rls.sql, sisanya harus kamu lihat sendiri.

SELECT 'meetings.user_id -> users' AS cek, m.id AS baris, m.user_id AS nilai
FROM meetings m LEFT JOIN users u ON u.id = m.user_id
WHERE m.user_id IS NOT NULL AND u.id IS NULL
UNION ALL
SELECT 'subscriptions.id -> users', s.id, s.id
FROM subscriptions s LEFT JOIN users u ON u.id = s.id
WHERE u.id IS NULL
UNION ALL
SELECT 'users.team_id -> teams', u.id, u.team_id
FROM users u LEFT JOIN teams t ON t.id = u.team_id
WHERE u.team_id IS NOT NULL AND t.id IS NULL
UNION ALL
SELECT 'teams.owner_id -> users', t.id, t.owner_id
FROM teams t LEFT JOIN users u ON u.id = t.owner_id
WHERE u.id IS NULL
UNION ALL
SELECT 'team_invites.team_id -> teams', i.token, i.team_id
FROM team_invites i LEFT JOIN teams t ON t.id = i.team_id
WHERE t.id IS NULL
UNION ALL
SELECT 'team_invites.created_by -> users', i.token, i.created_by
FROM team_invites i LEFT JOIN users u ON u.id = i.created_by
WHERE u.id IS NULL
UNION ALL
-- dibersihkan otomatis: baris penonton untuk rapat/user yang sudah tidak ada
SELECT 'meeting_viewers (otomatis dibersihkan)', v.meeting_id || ' / ' || v.user_id, ''
FROM meeting_viewers v
LEFT JOIN meetings m ON m.id = v.meeting_id
LEFT JOIN users u ON u.id = v.user_id
WHERE m.id IS NULL OR u.id IS NULL
UNION ALL
-- dibersihkan otomatis: meeting_id diubah jadi NULL, biayanya tetap terhitung
SELECT 'api_usage.meeting_id (otomatis di-NULL-kan)', a.id::text, a.meeting_id
FROM api_usage a LEFT JOIN meetings m ON m.id = a.meeting_id
WHERE a.meeting_id IS NOT NULL AND m.id IS NULL
UNION ALL
SELECT 'replicate_usage.meeting_id (otomatis di-NULL-kan)', r.id::text, r.meeting_id
FROM replicate_usage r LEFT JOIN meetings m ON m.id = r.meeting_id
WHERE r.meeting_id IS NOT NULL AND m.id IS NULL;
