"""Sends the "your transcript is ready" email after a meeting's pipeline
finishes — stdlib smtplib only, no new dependency. Called from
_process_recording() in app.py (shared by the join endpoints and /upload),
best-effort: a mail failure must never fail the pipeline the same way a bad
summary shouldn't erase an otherwise-successful recording.

Deliberately not read at module level (see pipeline/storage.py's own note
on this) — load_dotenv() has to run before these are read, and app.py
already guarantees that at startup.
"""

import html
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Same palette as constants/theme.js on the frontend, so the email doesn't
# look like a different product from the app it's about.
_INK = "#1B1F2B"
_INK_SOFT = "#4A5064"
_INK_FAINT = "#8A8F9E"
_BG = "#F6F4EE"
_SURFACE = "#FFFFFF"
_BORDER = "#E4E0D2"
_GOLD = "#E3B54A"
_GOLD_DEEP = "#8A6416"


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


def _render_html(title: str, summary_excerpt: str, meeting_url: str) -> str:
    """Table-based layout with every style inline — the only markup that
    renders consistently across email clients (Gmail, Outlook, etc. strip or
    ignore <style> blocks and modern CSS in ways a browser never would).
    User-supplied text (title, summary) is HTML-escaped since it lands
    straight in the markup."""
    safe_title = html.escape(title)
    safe_excerpt = html.escape(summary_excerpt or "Ringkasan belum tersedia untuk rapat ini.").replace("\n", "<br>")
    font = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

    return f"""\
<div style="background-color:{_BG};padding:32px 16px;font-family:{font};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;">
    <tr>
      <td style="padding-bottom:20px;">
        <span style="font-size:18px;font-weight:700;color:{_INK};">Notulis</span>
      </td>
    </tr>
    <tr>
      <td style="background-color:{_SURFACE};border:1px solid {_BORDER};border-radius:12px;padding:28px;">
        <div style="display:inline-block;background-color:{_GOLD};color:{_INK};font-size:11px;font-weight:700;
                    letter-spacing:0.4px;text-transform:uppercase;border-radius:999px;padding:4px 12px;margin-bottom:14px;">
          Transkrip &amp; Ringkasan Siap
        </div>
        <h1 style="margin:0 0 6px;font-size:20px;line-height:1.3;color:{_INK};">{safe_title}</h1>
        <p style="margin:0 0 20px;font-size:13px;color:{_INK_FAINT};">
          Rekaman rapat ini sudah selesai ditranskripsi dan diringkas otomatis.
        </p>
        <div style="border-left:3px solid {_GOLD};background-color:{_BG};border-radius:6px;padding:14px 16px;margin-bottom:24px;">
          <div style="font-size:11px;font-weight:700;letter-spacing:0.4px;text-transform:uppercase;color:{_GOLD_DEEP};margin-bottom:6px;">
            Ringkasan
          </div>
          <div style="font-size:14px;line-height:1.6;color:{_INK_SOFT};">{safe_excerpt}</div>
        </div>
        <a href="{meeting_url}"
           style="display:inline-block;background-color:{_GOLD};color:{_INK};font-size:14px;font-weight:700;
                  text-decoration:none;border-radius:8px;padding:11px 22px;">
          Lihat Detail Rapat
        </a>
      </td>
    </tr>
    <tr>
      <td style="padding-top:20px;text-align:center;">
        <span style="font-size:12px;color:{_INK_FAINT};">Email ini dikirim otomatis oleh Notulis.</span>
      </td>
    </tr>
  </table>
</div>"""


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
    """Raises on failure — callers decide whether/how to swallow it (see
    app.py's _process_recording, which logs and moves on rather than
    failing the pipeline over a mail hiccup)."""
    config = _config()
    if config is None:
        return  # SMTP not configured — no-op rather than an error, so this
        # feature stays inert until someone fills in .env, same as the rest
        # of this app's optional integrations.

    text = (
        f"Transkrip dan ringkasan rapat \"{title}\" sudah selesai diproses.\n\n"
        f"Ringkasan:\n{summary_excerpt}\n\n"
        f"Lihat detail lengkapnya: {meeting_url}\n\n"
        "-- Notulis"
    )
    _send(config, to_email, f"Transkrip siap: {title}", text, _render_html(title, summary_excerpt, meeting_url))


def send_password_reset_email(to_email: str, name: str, reset_url: str) -> None:
    """Raises on failure (the caller logs it); no-op if SMTP isn't configured."""
    config = _config()
    if config is None:
        return

    text = (
        f"Halo {name},\n\n"
        f"Kami menerima permintaan untuk mengatur ulang password akun Notulis Anda.\n"
        f"Atur password baru lewat tautan ini: {reset_url}\n\n"
        "Tautan berlaku selama 1 jam dan hanya bisa dipakai sekali. "
        "Jika bukan Anda yang meminta, abaikan email ini.\n\n"
        "-- Notulis"
    )
    font = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
    html_body = f"""<div style="background-color:{_BG};padding:32px 16px;font-family:{font};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;">
    <tr><td style="padding-bottom:20px;"><span style="font-size:18px;font-weight:700;color:{_INK};">Notulis</span></td></tr>
    <tr>
      <td style="background-color:{_SURFACE};border:1px solid {_BORDER};border-radius:12px;padding:28px;">
        <h1 style="margin:0 0 6px;font-size:20px;line-height:1.3;color:{_INK};">Atur Ulang Password</h1>
        <p style="margin:0 0 20px;font-size:14px;line-height:1.6;color:{_INK_SOFT};">
          Halo {html.escape(name)}, klik tombol di bawah untuk membuat password baru.
        </p>
        <a href="{reset_url}"
           style="display:inline-block;background-color:{_GOLD};color:{_INK};font-size:14px;font-weight:700;
                  text-decoration:none;border-radius:8px;padding:11px 22px;">
          Atur Password Baru
        </a>
        <p style="margin:20px 0 0;font-size:12px;color:{_INK_FAINT};">
          Berlaku 1 jam dan hanya bisa dipakai sekali. Jika bukan Anda yang meminta, abaikan email ini.
        </p>
      </td>
    </tr>
  </table>
</div>"""
    _send(config, to_email, "Atur ulang password Notulis", text, html_body)


def send_quota_exhausted_email(to_email: str, name: str, limit_minutes: float, upgrade_url: str, cut_off: bool = False) -> None:
    """Raises on failure (the caller logs it); no-op if SMTP isn't configured."""
    config = _config()
    if config is None:
        return

    note = "Rekaman rapat Anda yang sedang berjalan sudah dihentikan otomatis. " if cut_off else ""
    text = (
        f"Halo {name},\n\n"
        f"Kuota rekaman paket Free Anda minggu ini ({limit_minutes:g} menit) sudah habis. "
        f"{note}"
        "Kuota baru tersedia Minggu pukul 08.00 WITA.\n\n"
        "Rapat penting tidak harus menunggu. Dengan Pro (Rp99rb / bulan):\n"
        "- Rapat dan durasi rekaman tanpa batas\n"
        "- Video + transkrip tersinkron, editor transkrip\n"
        "- Knowledge Base: cari keputusan dari semua rapat lama\n\n"
        f"Upgrade sekarang: {upgrade_url}\n\n"
        "-- Notulis"
    )
    font = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
    perks = "".join(
        f'<li style="margin:0 0 6px;">{p}</li>'
        for p in (
            "<strong>Rapat dan durasi rekaman tanpa batas</strong>, tidak ada kuota mingguan",
            "Video + transkrip tersinkron dan editor transkrip",
            "Knowledge Base: cari keputusan dari semua rapat lama",
        )
    )
    html_body = f"""<div style="background-color:{_BG};padding:32px 16px;font-family:{font};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;">
    <tr><td style="padding-bottom:20px;"><span style="font-size:18px;font-weight:700;color:{_INK};">Notulis</span></td></tr>
    <tr>
      <td style="background-color:{_SURFACE};border:1px solid {_BORDER};border-radius:12px;padding:28px;">
        <h1 style="margin:0 0 6px;font-size:20px;line-height:1.3;color:{_INK};">Kuota rekaman minggu ini habis</h1>
        <p style="margin:0 0 20px;font-size:14px;line-height:1.6;color:{_INK_SOFT};">
          Halo {html.escape(name)}, {limit_minutes:g} menit rekaman paket Free Anda minggu ini sudah terpakai.
          {"Rekaman rapat Anda yang sedang berjalan <strong>sudah dihentikan otomatis</strong>. " if cut_off else ""}Kuota baru tersedia <strong>Minggu pukul 08.00 WITA</strong>.
        </p>
        <div style="background-color:{_BG};border:1px solid {_BORDER};border-radius:10px;padding:18px 20px;margin-bottom:22px;">
          <p style="margin:0 0 4px;font-size:15px;font-weight:700;color:{_INK};">Rapat penting tidak harus menunggu.</p>
          <p style="margin:0 0 12px;font-size:13px;color:{_GOLD_DEEP};font-weight:600;">Pro, Rp99rb / bulan</p>
          <ul style="margin:0;padding-left:18px;font-size:14px;line-height:1.5;color:{_INK_SOFT};">{perks}</ul>
        </div>
        <a href="{upgrade_url}"
           style="display:inline-block;background-color:{_GOLD};color:{_INK};font-size:14px;font-weight:700;
                  text-decoration:none;border-radius:8px;padding:12px 26px;">
          Upgrade ke Pro
        </a>
        <p style="margin:18px 0 0;font-size:12px;color:{_INK_FAINT};">Bisa berhenti kapan saja dari menu Pengaturan.</p>
      </td>
    </tr>
  </table>
</div>"""
    _send(config, to_email, "Kuota rekaman habis: lanjutkan rapat dengan Pro", text, html_body)


def send_team_invite_email(to_email: str, team_name: str, inviter_name: str, invite_url: str) -> None:
    """Best-effort, same as send_meeting_ready_email — a failed invite email
    doesn't block the invite link itself from working (app.py still returns
    it in the response either way)."""
    config = _config()
    if config is None:
        return

    safe_team = html.escape(team_name)
    safe_inviter = html.escape(inviter_name)
    text = (
        f"{inviter_name} mengundang Anda bergabung ke team \"{team_name}\" di Notulis.\n\n"
        f"Gabung lewat tautan ini: {invite_url}\n\n"
        "Tautan ini berlaku selama 7 hari.\n\n"
        "-- Notulis"
    )
    font = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
    html_body = f"""\
<div style="background-color:{_BG};padding:32px 16px;font-family:{font};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;">
    <tr>
      <td style="padding-bottom:20px;">
        <span style="font-size:18px;font-weight:700;color:{_INK};">Notulis</span>
      </td>
    </tr>
    <tr>
      <td style="background-color:{_SURFACE};border:1px solid {_BORDER};border-radius:12px;padding:28px;">
        <h1 style="margin:0 0 6px;font-size:20px;line-height:1.3;color:{_INK};">Undangan Team</h1>
        <p style="margin:0 0 20px;font-size:14px;line-height:1.6;color:{_INK_SOFT};">
          <strong>{safe_inviter}</strong> mengundang Anda bergabung ke team <strong>{safe_team}</strong> di Notulis.
        </p>
        <a href="{invite_url}"
           style="display:inline-block;background-color:{_GOLD};color:{_INK};font-size:14px;font-weight:700;
                  text-decoration:none;border-radius:8px;padding:11px 22px;">
          Gabung Team
        </a>
        <p style="margin:20px 0 0;font-size:12px;color:{_INK_FAINT};">Tautan ini berlaku selama 7 hari.</p>
      </td>
    </tr>
    <tr>
      <td style="padding-top:20px;text-align:center;">
        <span style="font-size:12px;color:{_INK_FAINT};">Email ini dikirim otomatis oleh Notulis.</span>
      </td>
    </tr>
  </table>
</div>"""
    _send(config, to_email, f"Undangan bergabung ke team {team_name}", text, html_body)
