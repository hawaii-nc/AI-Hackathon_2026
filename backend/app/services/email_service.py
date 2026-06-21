"""Local-first email sending.

Backends (chosen via the EMAIL_BACKEND env var):

  * "console"  (default) — does NOT send anything over the network. It saves
                the message as both .eml and .html into backend/outbox/, prints
                a summary to the terminal, and (optionally) opens the .html
                preview in your browser. This is the "test locally instead of
                AWS" path: you can see exactly what would be sent.

  * "smtp"     — sends via a real SMTP server. Point it at a local catcher
                (e.g. `python -m aiosmtpd -n -l localhost:1025`, or MailHog /
                Mailpit) for local testing, or at a real provider later.

Swapping to AWS SES down the road is just adding an "ses" branch here; nothing
else in the app has to change.
"""

import os
import smtplib
import webbrowser
from datetime import datetime
from email.message import EmailMessage
from email.utils import make_msgid
from html import escape
from pathlib import Path

# backend/outbox  (two parents up: services -> app -> backend)
OUTBOX = Path(__file__).resolve().parents[2] / "outbox"


def _build_message(to_email, subject, body, from_email, from_name=None, to_name=None) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    msg["To"] = f"{to_name} <{to_email}>" if (to_name and to_email) else (to_email or "")
    msg["Message-ID"] = make_msgid()
    msg["Date"] = datetime.now().astimezone().strftime("%a, %d %b %Y %H:%M:%S %z")
    msg.set_content(body)
    return msg


def _render_html(msg: EmailMessage, body: str) -> str:
    rows = "".join(
        f'<tr><td class="k">{escape(k)}</td><td class="v">{escape(str(msg[k]))}</td></tr>'
        for k in ("From", "To", "Subject", "Date")
        if msg[k]
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{escape(msg["Subject"] or "Email preview")}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; background:#f4f5f7; margin:0; padding:24px; }}
  .card {{ max-width:680px; margin:0 auto; background:#fff; border:1px solid #e3e5e8; border-radius:10px; overflow:hidden; }}
  .banner {{ background:#fff7e6; color:#8a6d3b; font-size:13px; padding:8px 20px; border-bottom:1px solid #f0e3c0; }}
  table.hdr {{ width:100%; border-collapse:collapse; }}
  table.hdr td {{ padding:6px 20px; font-size:14px; border-bottom:1px solid #f0f1f3; }}
  td.k {{ color:#6b7280; width:80px; font-weight:600; vertical-align:top; }}
  td.v {{ color:#111827; }}
  pre.body {{ white-space:pre-wrap; word-wrap:break-word; font-family:inherit; font-size:15px; line-height:1.55; color:#111827; padding:20px; margin:0; }}
</style></head>
<body>
  <div class="card">
    <div class="banner">📨 LOCAL PREVIEW — this email was NOT sent. (EMAIL_BACKEND=console)</div>
    <table class="hdr">{rows}</table>
    <pre class="body">{escape(body)}</pre>
  </div>
</body></html>"""


def _send_console(msg: EmailMessage, body: str, open_preview: bool) -> dict:
    OUTBOX.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    eml_path = OUTBOX / f"{stamp}.eml"
    html_path = OUTBOX / f"{stamp}.html"

    eml_path.write_bytes(bytes(msg))
    html_path.write_text(_render_html(msg, body), encoding="utf-8")

    print("\n" + "=" * 70)
    print("EMAIL (console backend - NOT actually sent)")
    print("=" * 70)
    print(f"From:    {msg['From']}")
    print(f"To:      {msg['To']}")
    print(f"Subject: {msg['Subject']}")
    print("-" * 70)
    print(body)
    print("=" * 70)
    print(f"Saved preview: {html_path}")
    print(f"Saved .eml:    {eml_path}\n")

    if open_preview:
        webbrowser.open(html_path.as_uri())

    return {"backend": "console", "eml": str(eml_path), "html": str(html_path), "sent": False}


def _send_smtp(msg: EmailMessage) -> dict:
    host = os.getenv("SMTP_HOST", "localhost")
    port = int(os.getenv("SMTP_PORT", "1025"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    use_tls = os.getenv("SMTP_USE_TLS", "false").lower() == "true"
    timeout = int(os.getenv("SMTP_TIMEOUT", "30"))

    # Port 465 (or SMTP_SSL=true) = implicit SSL from the start. Port 587 =
    # plain connect then STARTTLS. Some networks block one but not the other.
    use_ssl = os.getenv("SMTP_SSL", "").lower() == "true" or port == 465

    if use_ssl:
        server = smtplib.SMTP_SSL(host, port, timeout=timeout)
    else:
        server = smtplib.SMTP(host, port, timeout=timeout)
    with server:
        if not use_ssl and use_tls:
            server.starttls()
        if user and password:
            server.login(user, password)
        server.send_message(msg)

    print(f"Email sent via SMTP to {msg['To']} through {host}:{port}")
    return {"backend": "smtp", "host": host, "port": port, "sent": True}


def send_email(
    to_email,
    subject,
    body,
    from_email="referrals@example.org",
    from_name=None,
    to_name=None,
    backend=None,
    open_preview=False,
) -> dict:
    """Send (or locally preview) an email. Returns a small result dict."""
    backend = (backend or os.getenv("EMAIL_BACKEND", "console")).lower()

    # Some providers (e.g. Gmail) only let you send "From" the authenticated
    # account, so allow MAIL_FROM / MAIL_FROM_NAME to override the draft's
    # sender. Keeps the visible From consistent with who actually sent it.
    from_email = os.getenv("MAIL_FROM") or from_email
    from_name = os.getenv("MAIL_FROM_NAME") or from_name

    # In console mode there may be no recipient address yet — that's fine.
    if backend != "console" and not to_email:
        raise ValueError("to_email is required to actually send an email")

    msg = _build_message(to_email, subject, body, from_email, from_name, to_name)

    if backend == "console":
        return _send_console(msg, body, open_preview)
    if backend == "smtp":
        return _send_smtp(msg)
    raise ValueError(f"Unknown EMAIL_BACKEND: {backend!r} (expected 'console' or 'smtp')")
