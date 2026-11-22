-- Membuang tabel meeting_viewers (fitur penonton sudah diganti rapat salinan, tidak ada kode yang memakainya lagi).
-- JALANKAN SETELAH backend versi baru ter-deploy: backend lama masih membaca tabel ini dan akan error kalau tabelnya hilang.
-- Dijalankan sekali di Supabase SQL Editor, aman diulang. Dua foreign key tabel ini ikut terbuang bersama tabelnya.
DROP TABLE IF EXISTS meeting_viewers;
