"""Setiap email membangun subjek dan html-nya (teks user di-escape) dan diam tanpa konfigurasi SMTP.

Jalankan: python -m tests.test_mailer   (dari backend/)"""
import os

from pipeline import mailer

sent = []
mailer._send = lambda config, to, subject, text, html_body: sent.append((to, subject, text, html_body))

# tanpa pengaturan SMTP: tidak ada yang dikirim
for key in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
    os.environ.pop(key, None)
mailer.send_meeting_ready_email("a@b.c", "T", "x", "http://u")
assert sent == []

os.environ.update(SMTP_HOST="h", SMTP_USER="u", SMTP_PASSWORD="p")
evil = "<b>x</b> & y"

mailer.send_meeting_ready_email("a@b.c", evil, "baris 1\nbaris 2", "http://u/rapat/1")
mailer.send_password_reset_email("a@b.c", evil, "http://u/reset/t")
mailer.send_meeting_unprocessed_email("a@b.c", evil, evil, 65, 40, 60, "http://u/rapat/1", "http://u/billing")
mailer.send_team_invite_email("a@b.c", evil, evil, "http://u/team/gabung/t")

assert len(sent) == 4
for to, subject, text, body in sent:
    assert to == "a@b.c" and subject and text
    assert "&lt;b&gt;x&lt;/b&gt; &amp; y" in body or "http://u/reset/t" in body  # di-escape, atau tidak ada teks user selain nama
    assert "<b>x</b>" not in body
    assert "Notulis" in body
assert "baris 1<br>baris 2" in sent[0][3]
assert "http://u/billing" in sent[2][3] and "65" in sent[2][3]
assert "7 hari" in sent[3][3]
print("ok")
