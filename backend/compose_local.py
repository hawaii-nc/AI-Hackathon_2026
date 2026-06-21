"""Local email composer — edit the draft and click Send. No AWS, no Next.js.

    python compose_local.py                # draft with mock data, open composer
    python compose_local.py --placeholder  # skip Gemini (no API call / quota)
    python compose_local.py --port 9000    # use a different port

It starts a tiny local web server, opens a Gmail-style compose window in your
browser with the drafted email pre-filled, and lets you edit the recipient,
subject, and body. The "Send" button (bottom-right) routes through the same
email_service backend used everywhere else:

  * EMAIL_BACKEND=console (default) -> saves .eml + .html to backend/outbox/
                                       (nothing actually leaves your machine)
  * EMAIL_BACKEND=smtp              -> sends via your SMTP settings

Stop the server with Ctrl+C in the terminal.
"""

import argparse
import http.server
import json
import os
import socketserver
import sys
import webbrowser
from html import escape

# Make `from app...` imports work no matter where this is run from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.referral import draft_referral_email
from app.services.email_service import send_email

# Same mock data shape as Supabase rows (see test_referral_local.py).
MOCK_CLIENT = {
    "needs": ["housing", "mental_health", "food"],
    "urgency": "high",
    "has_children": True,
    "veteran": False,
    "summary": (
        "Single parent with two young children, recently lost housing after a "
        "job loss. Currently staying in a vehicle and needs short-term shelter "
        "plus help connecting to food and mental health support."
    ),
}
MOCK_SHELTER = {
    "name": "Aloha Family Shelter",
    "type": "family shelter",
    "city": "Honolulu",
    "island": "Oahu",
    "phone": "(808) 555-0142",
    "email": "intake@alohafamilyshelter.example.org",
}
MOCK_SENDER = {
    "name": "Jordan Rivera",
    "org": "Community Outreach Services",
    "email": "jordan.rivera@example.org",
    "phone": "(808) 555-0199",
}

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Referral email composer</title>
<style>
  * { box-sizing: border-box; }
  body { margin:0; font-family:-apple-system,Segoe UI,Roboto,sans-serif; background:#eef0f3; color:#1f2329; }
  .wrap { max-width:720px; margin:32px auto; padding:0 16px; }
  .card { background:#fff; border:1px solid #dfe1e6; border-radius:12px; box-shadow:0 6px 24px rgba(0,0,0,.06); overflow:hidden; display:flex; flex-direction:column; }
  .head { padding:14px 20px; border-bottom:1px solid #eceef1; font-weight:600; font-size:15px; }
  .banner { padding:10px 20px; font-size:13px; background:#fff7e6; color:#8a6d3b; border-bottom:1px solid #f0e3c0; }
  .field { display:flex; align-items:flex-start; border-bottom:1px solid #eceef1; }
  .field label { width:80px; padding:12px 0 12px 20px; color:#6b7280; font-size:13px; font-weight:600; flex:none; }
  .field input, .field textarea { flex:1; border:0; outline:none; padding:12px 20px; font-size:14px; font-family:inherit; color:#1f2329; resize:vertical; background:transparent; }
  .field textarea { min-height:340px; line-height:1.55; }
  .foot { display:flex; align-items:center; justify-content:space-between; padding:14px 20px; border-top:1px solid #eceef1; background:#fafbfc; }
  .meta { font-size:12px; color:#6b7280; }
  .btn { background:#2563eb; color:#fff; border:0; border-radius:8px; padding:10px 24px; font-size:14px; font-weight:600; cursor:pointer; }
  .btn:hover { background:#1d4ed8; }
  .btn:disabled { opacity:.6; cursor:default; }
  .toast { font-size:13px; margin-left:10px; }
  .toast.ok { color:#15803d; }
  .toast.err { color:#b91c1c; }
</style></head>
<body>
  <div class="wrap"><div class="card">
    <div class="head">New referral email</div>
    __STATUS_BANNER__
    <div class="field"><label>To</label><input id="to" value="__TO__" placeholder="recipient@example.org"></div>
    <div class="field"><label>Subject</label><input id="subject" value="__SUBJECT__"></div>
    <div class="field"><textarea id="body">__BODY__</textarea></div>
    <div class="foot">
      <div><span class="meta">Backend: __BACKEND__</span><span id="toast" class="toast"></span></div>
      <button id="send" class="btn">Send</button>
    </div>
  </div></div>
<script>
const btn = document.getElementById('send');
const toast = document.getElementById('toast');
btn.addEventListener('click', async () => {
  btn.disabled = true; toast.className = 'toast'; toast.textContent = 'Sending...';
  try {
    const r = await fetch('/send', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        to: document.getElementById('to').value,
        subject: document.getElementById('subject').value,
        body: document.getElementById('body').value
      })
    });
    const data = await r.json();
    toast.className = 'toast ' + (data.ok ? 'ok' : 'err');
    toast.textContent = data.ok ? (data.message || 'Sent.') : ('Error: ' + (data.error || 'unknown'));
  } catch (e) {
    toast.className = 'toast err';
    toast.textContent = 'Error: ' + e.message;
  } finally {
    btn.disabled = false;
  }
});
</script>
</body></html>"""


def render(email: dict, backend: str) -> bytes:
    banner = ""
    if email.get("status") == "placeholder":
        banner = (
            '<div class="banner">Placeholder draft - Gemini was unavailable. '
            "Please review and edit before sending.</div>"
        )
    html = (
        PAGE.replace("__STATUS_BANNER__", banner)
        .replace("__TO__", escape(email.get("to_email") or "", quote=True))
        .replace("__SUBJECT__", escape(email.get("subject") or "", quote=True))
        .replace("__BODY__", escape(email.get("body") or ""))
        .replace("__BACKEND__", escape(backend))
    )
    return html.encode("utf-8")


def make_handler(email: dict, backend: str):
    class Handler(http.server.BaseHTTPRequestHandler):
        def _write(self, code, body, content_type="text/html; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._write(200, render(email, backend))
            else:
                self._write(404, b"not found", "text/plain")

        def do_POST(self):
            if self.path != "/send":
                self._write(404, b"not found", "text/plain")
                return
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
            try:
                result = send_email(
                    to_email=data.get("to"),
                    subject=data.get("subject", ""),
                    body=data.get("body", ""),
                    from_email=email.get("from_email"),
                    from_name=email.get("from_name"),
                    to_name=email.get("to_name"),
                    backend=backend,
                )
                if result.get("backend") == "console":
                    msg = (
                        f"Saved to outbox ({os.path.basename(result['html'])}). "
                        "Console mode - nothing was actually emailed."
                    )
                else:
                    msg = f"Sent via SMTP to {data.get('to')}."
                payload = json.dumps({"ok": True, "message": msg, "result": result})
            except Exception as exc:
                payload = json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            self._write(200, payload.encode("utf-8"), "application/json")

        def log_message(self, *args):
            pass  # keep the terminal quiet

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Local editable email composer.")
    parser.add_argument("--placeholder", "--template", dest="placeholder", action="store_true",
                        help="Skip Gemini and use a placeholder draft.")
    parser.add_argument("--port", type=int, default=8765, help="Port to serve on (default 8765).")
    args = parser.parse_args()

    backend = (os.getenv("EMAIL_BACKEND", "console")).lower()
    print("Drafting referral email...")
    email = draft_referral_email(MOCK_CLIENT, MOCK_SHELTER, sender=MOCK_SENDER, use_llm=not args.placeholder)
    print(f"[info] draft status: {email['status']} | send backend: {backend}")

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("localhost", args.port), make_handler(email, backend)) as httpd:
        url = f"http://localhost:{args.port}"
        print(f"\nComposer running at {url}  (press Ctrl+C to stop)\n")
        webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
