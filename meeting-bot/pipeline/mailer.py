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


def send_meeting_ready_email(to_email: str, title: str, summary_excerpt: str, meeting_url: str) -> None:
    """Raises on failure — callers decide whether/how to swallow it (see
    app.py's _process_recording, which logs and moves on rather than
    failing the pipeline over a mail hiccup)."""
    config = _config()
    if config is None:
        return  # SMTP not configured — no-op rather than an error, so this
        # feature stays inert until someone fills in .env, same as the rest
        # of this app's optional integrations.

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Transkrip siap: {title}"
    msg["From"] = config["from"]
    msg["To"] = to_email

    text = (
        f"Transkrip dan ringkasan rapat \"{title}\" sudah selesai diproses.\n\n"
        f"Ringkasan:\n{summary_excerpt}\n\n"
        f"Lihat detail lengkapnya: {meeting_url}\n\n"
        "-- Notulis"
    )
    html_body = _render_html(title, summary_excerpt, meeting_url)
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(config["host"], config["port"], timeout=15) as server:
        server.starttls()
        server.login(config["user"], config["password"])
        server.sendmail(config["from"], [to_email], msg.as_string())
