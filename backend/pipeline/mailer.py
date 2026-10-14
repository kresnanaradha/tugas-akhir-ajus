"""Email lewat smtplib biasa. Setiap send_* tidak melakukan apa-apa kalau SMTP belum dikonfigurasi di .env, dan melempar
error kalau gagal, pemanggil yang memutuskan menelannya atau tidak (masalah email tidak boleh menggagalkan pipeline).
Konfigurasi dibaca di dalam fungsi, bukan saat import, jadi .env harus dimuat dulu (app.py melakukannya)."""

import html
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# palet yang sama dengan frontend/constants/theme.js
_INK = "#1B1F2B"
_INK_SOFT = "#4A5064"
_INK_FAINT = "#8A8F9E"
_BG = "#F6F4EE"
_SURFACE = "#FFFFFF"
_BORDER = "#ECE8DC"
_GOLD = "#E3B54A"
_GOLD_DEEP = "#8A6416"
_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _config() -> dict | None:
    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    if not host or not user or not password:
        return None
    return {
        "host": host,
        "port": int(os.getenv("SMTP_PORT") or 587),
        "user": user,
        "password": password,
        "from": os.getenv("SMTP_FROM") or user,
    }


def _layout(content: str, footer: bool = False) -> str:
    """Kartu yang dipakai semua email. Tabel dengan style inline, satu-satunya markup yang dirender konsisten oleh klien email
    (Gmail, Outlook). Teks dari user harus di-html.escape() sebelum masuk ke sini."""
    footer_row = (
        f'<tr><td style="padding-top:20px;text-align:center;">'
        f'<span style="font-size:12px;color:{_INK_FAINT};">Email ini dikirim otomatis oleh Notulis.</span></td></tr>'
        if footer
        else ""
    )
    return f"""<div style="background-color:{_BG};padding:32px 16px;font-family:{_FONT};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;">
    <tr><td style="padding-bottom:20px;"><span style="font-size:18px;font-weight:700;color:{_INK};">Notulis</span></td></tr>
    <tr>
      <td style="background-color:{_SURFACE};border:1px solid {_BORDER};border-radius:12px;padding:28px;">
{content}
      </td>
    </tr>
    {footer_row}
  </table>
</div>"""


def _heading(text: str) -> str:
    return f'<h1 style="margin:0 0 6px;font-size:20px;line-height:1.3;color:{_INK};">{text}</h1>'


def _paragraph(text: str, size: int = 14, color: str = _INK_SOFT, margin: str = "0 0 20px") -> str:
    return f'<p style="margin:{margin};font-size:{size}px;line-height:1.6;color:{color};">{text}</p>'


def _button(url: str, label: str, padding: str = "11px 22px") -> str:
    return (
        f'<a href="{url}" style="display:inline-block;background-color:{_GOLD};color:{_INK};font-size:14px;'
        f'font-weight:700;text-decoration:none;border-radius:8px;padding:{padding};">{label}</a>'
    )


def _send(config: dict, to_email: str, subject: str, text: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config["from"]
    msg["To"] = to_email
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(config["host"], config["port"], timeout=15) as server:
        server.starttls()
        server.login(config["user"], config["password"])
        server.sendmail(config["from"], [to_email], msg.as_string())


def send_meeting_ready_email(to_email: str, title: str, summary_excerpt: str, meeting_url: str) -> None:
    config = _config()
    if config is None:
        return

    text = (
        f"Transkrip dan ringkasan rapat \"{title}\" sudah selesai diproses.\n\n"
        f"Ringkasan:\n{summary_excerpt}\n\n"
        f"Lihat detail lengkapnya: {meeting_url}\n\n"
        "-- Notulis"
    )
    excerpt = html.escape(summary_excerpt or "Ringkasan belum tersedia untuk rapat ini.").replace("\n", "<br>")
    badge = (
        f'<div style="display:inline-block;background-color:{_GOLD};color:{_INK};font-size:11px;font-weight:700;'
        f'letter-spacing:0.4px;text-transform:uppercase;border-radius:999px;padding:4px 12px;margin-bottom:14px;">'
        "Transkrip &amp; Ringkasan Siap</div>"
    )
    quote = (
        f'<div style="border-left:3px solid {_GOLD};background-color:{_BG};border-radius:6px;padding:14px 16px;margin-bottom:24px;">'
        f'<div style="font-size:11px;font-weight:700;letter-spacing:0.4px;text-transform:uppercase;color:{_GOLD_DEEP};'
        f'margin-bottom:6px;">Ringkasan</div>'
        f'<div style="font-size:14px;line-height:1.6;color:{_INK_SOFT};">{excerpt}</div></div>'
    )
    content = "\n".join([
        badge,
        _heading(html.escape(title)),
        _paragraph("Rekaman rapat ini sudah selesai ditranskripsi dan diringkas otomatis.", size=13, color=_INK_FAINT),
        quote,
        _button(meeting_url, "Lihat Detail Rapat"),
    ])
    _send(config, to_email, f"Transkrip siap: {title}", text, _layout(content, footer=True))


def send_password_reset_email(to_email: str, name: str, reset_url: str) -> None:
    config = _config()
    if config is None:
        return

    text = (
        f"Halo {name},\n\n"
        "Kami menerima permintaan untuk mengatur ulang password akun Notulis Anda.\n"
        f"Atur password baru lewat tautan ini: {reset_url}\n\n"
        "Tautan berlaku selama 1 jam dan hanya bisa dipakai sekali. "
        "Jika bukan Anda yang meminta, abaikan email ini.\n\n"
        "-- Notulis"
    )
    content = "\n".join([
        _heading("Atur Ulang Password"),
        _paragraph(f"Halo {html.escape(name)}, klik tombol di bawah untuk membuat password baru."),
        _button(reset_url, "Atur Password Baru"),
        _paragraph(
            "Berlaku 1 jam dan hanya bisa dipakai sekali. Jika bukan Anda yang meminta, abaikan email ini.",
            size=12, color=_INK_FAINT, margin="20px 0 0",
        ),
    ])
    _send(config, to_email, "Atur ulang password Notulis", text, _layout(content))


def send_meeting_unprocessed_email(
    to_email: str, name: str, title: str, duration_minutes: float, remaining_minutes: float,
    limit_minutes: float, meeting_url: str, upgrade_url: str,
) -> None:
    """Rekaman Free yang lebih panjang dari sisa menit AI minggu ini: disimpan utuh, tidak diproses."""
    config = _config()
    if config is None:
        return

    summary = (
        f"Rekaman rapat \"{title}\" ({duration_minutes:g} menit) sudah tersimpan utuh dan bisa diputar, "
        f"tetapi belum diproses AI (transkrip dan ringkasan) karena sisa kuota paket Free minggu ini "
        f"{remaining_minutes:g} dari {limit_minutes:g} menit."
    )
    text = (
        f"Halo {name},\n\n{summary}\n\n"
        "Dengan Pro (Rp99rb / bulan) rapat ini bisa langsung diproses, dan rapat berikutnya tanpa batas menit:\n"
        "- Transkrip + ringkasan AI untuk semua rapat, tanpa kuota mingguan\n"
        "- Video + transkrip tersinkron, editor transkrip\n"
        "- Knowledge Base: cari keputusan dari semua rapat lama\n\n"
        f"Upgrade sekarang: {upgrade_url}\n"
        f"Lihat rekaman: {meeting_url}\n\n"
        "-- Notulis"
    )
    perks = "".join(
        f'<li style="margin:0 0 6px;">{p}</li>'
        for p in (
            "<strong>Transkrip + ringkasan AI untuk semua rapat</strong>, tanpa kuota mingguan",
            "Video + transkrip tersinkron dan editor transkrip",
            "Knowledge Base: cari keputusan dari semua rapat lama",
        )
    )
    offer = (
        f'<div style="background-color:{_BG};border:1px solid {_BORDER};border-radius:10px;padding:18px 20px;margin-bottom:22px;">'
        f'<p style="margin:0 0 4px;font-size:15px;font-weight:700;color:{_INK};">Rapat ini bisa langsung diproses.</p>'
        f'<p style="margin:0 0 12px;font-size:13px;color:{_GOLD_DEEP};font-weight:600;">Pro, Rp99rb / bulan</p>'
        f'<ul style="margin:0;padding-left:18px;font-size:14px;line-height:1.5;color:{_INK_SOFT};">{perks}</ul></div>'
    )
    intro = (
        f"Halo {html.escape(name)}, rekaman rapat <strong>{html.escape(title)}</strong> ({duration_minutes:g} menit) "
        "<strong>sudah tersimpan utuh</strong> dan bisa diputar. Transkrip dan ringkasan AI belum dibuat karena sisa "
        f"kuota paket Free minggu ini {remaining_minutes:g} dari {limit_minutes:g} menit."
    )
    content = "\n".join([
        _heading("Rekaman tersimpan, belum diproses AI"),
        _paragraph(intro),
        offer,
        _button(upgrade_url, "Upgrade ke Pro", padding="12px 26px"),
        f'<p style="margin:18px 0 0;font-size:13px;"><a href="{meeting_url}" style="color:{_GOLD_DEEP};">Lihat rekaman</a></p>',
        _paragraph('Setelah upgrade, buka rapat ini lalu klik "Proses Sekarang".', size=12, color=_INK_FAINT, margin="10px 0 0"),
    ])
    _send(config, to_email, "Rekaman tersimpan, upgrade untuk memprosesnya dengan AI", text, _layout(content))


def send_team_invite_email(to_email: str, team_name: str, inviter_name: str, invite_url: str) -> None:
    config = _config()
    if config is None:
        return

    text = (
        f"{inviter_name} mengundang Anda bergabung ke team \"{team_name}\" di Notulis.\n\n"
        f"Gabung lewat tautan ini: {invite_url}\n\n"
        "Tautan ini berlaku selama 7 hari.\n\n"
        "-- Notulis"
    )
    intro = f"<strong>{html.escape(inviter_name)}</strong> mengundang Anda bergabung ke team <strong>{html.escape(team_name)}</strong> di Notulis."
    content = "\n".join([
        _heading("Undangan Team"),
        _paragraph(intro),
        _button(invite_url, "Gabung Team"),
        _paragraph("Tautan ini berlaku selama 7 hari.", size=12, color=_INK_FAINT, margin="20px 0 0"),
    ])
    _send(config, to_email, f"Undangan bergabung ke team {team_name}", text, _layout(content, footer=True))
