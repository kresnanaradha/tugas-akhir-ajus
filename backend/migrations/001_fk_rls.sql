-- Foreign key + RLS untuk Notulis. Jalankan SETELAH 001_cek_yatim.sql bersih (kecuali dua jenis yang dibersihkan di sini).
-- Aman dijalankan ulang: tiap constraint dicek dulu di pg_constraint. Backend memakai peran postgres (BYPASSRLS), jadi
-- RLS tanpa policy hanya menutup REST API Supabase (anon/authenticated), aplikasi tidak terpengaruh.

-- 1. Bersihkan yatim yang aman dibuang
DELETE FROM meeting_viewers v
WHERE NOT EXISTS (SELECT 1 FROM meetings m WHERE m.id = v.meeting_id)
   OR NOT EXISTS (SELECT 1 FROM users u WHERE u.id = v.user_id);

-- biaya tetap tercatat, hanya tautan ke rapat yang sudah dihapus yang dilepas
UPDATE api_usage SET meeting_id = NULL
WHERE meeting_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM meetings m WHERE m.id = api_usage.meeting_id);
UPDATE replicate_usage SET meeting_id = NULL
WHERE meeting_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM meetings m WHERE m.id = replicate_usage.meeting_id);

-- 2. Foreign key (NOT VALID dulu supaya tidak mengunci lama, lalu VALIDATE)
DO $$
DECLARE
    fk record;
BEGIN
    FOR fk IN
        SELECT * FROM (VALUES
            ('fk_meetings_user',          'meetings',         'user_id',     'users',    'id', 'NO ACTION'),
            ('fk_viewers_meeting',        'meeting_viewers',  'meeting_id',  'meetings', 'id', 'CASCADE'),
            ('fk_viewers_user',           'meeting_viewers',  'user_id',     'users',    'id', 'CASCADE'),
            ('fk_subscriptions_user',     'subscriptions',    'id',          'users',    'id', 'CASCADE'),
            ('fk_users_team',             'users',            'team_id',     'teams',    'id', 'SET NULL'),
            ('fk_teams_owner',            'teams',            'owner_id',    'users',    'id', 'NO ACTION'),
            ('fk_invites_team',           'team_invites',     'team_id',     'teams',    'id', 'CASCADE'),
            ('fk_invites_creator',        'team_invites',     'created_by',  'users',    'id', 'NO ACTION'),
            -- SET NULL, bukan CASCADE: menghapus rapat tidak boleh menghapus catatan biayanya (dashboard admin)
            ('fk_api_usage_meeting',      'api_usage',        'meeting_id',  'meetings', 'id', 'SET NULL'),
            ('fk_replicate_meeting',      'replicate_usage',  'meeting_id',  'meetings', 'id', 'SET NULL')
        ) AS t(name, tbl, col, ref_tbl, ref_col, on_delete)
    LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = fk.name) THEN
            EXECUTE format(
                'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES %I (%I) ON DELETE %s NOT VALID',
                fk.tbl, fk.name, fk.col, fk.ref_tbl, fk.ref_col, fk.on_delete);
        END IF;
        EXECUTE format('ALTER TABLE %I VALIDATE CONSTRAINT %I', fk.tbl, fk.name);
    END LOOP;
END $$;

-- 3. Indeks untuk kolom FK yang dicari saat rapat dihapus (PK tabel lain sudah berindeks sendiri)
CREATE INDEX IF NOT EXISTS idx_api_usage_meeting ON api_usage (meeting_id);
CREATE INDEX IF NOT EXISTS idx_replicate_usage_meeting ON replicate_usage (meeting_id);
CREATE INDEX IF NOT EXISTS idx_meetings_user ON meetings (user_id);
CREATE INDEX IF NOT EXISTS idx_users_team ON users (team_id);
CREATE INDEX IF NOT EXISTS idx_viewers_user ON meeting_viewers (user_id);

-- 4. RLS tanpa policy: tolak semua akses lewat REST API Supabase. Peran postgres (backend) memintas RLS
ALTER TABLE users            ENABLE ROW LEVEL SECURITY;
ALTER TABLE meetings         ENABLE ROW LEVEL SECURITY;
ALTER TABLE meeting_viewers  ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions    ENABLE ROW LEVEL SECURITY;
ALTER TABLE teams            ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_invites     ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_usage        ENABLE ROW LEVEL SECURITY;
ALTER TABLE replicate_usage  ENABLE ROW LEVEL SECURITY;

-- Verifikasi (harus 10 baris FK dan 8 tabel rowsecurity = true):
-- SELECT conname FROM pg_constraint WHERE contype = 'f' AND connamespace = 'public'::regnamespace;
-- SELECT relname, relrowsecurity FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'r';
