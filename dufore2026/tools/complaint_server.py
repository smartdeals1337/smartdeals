#!/usr/bin/env python3
"""Dufore Open complaint logger. Standard library only, no installs needed.

What it does
  * Receives the complaint the website sends when a player taps "Send by email".
  * Appends every complaint to a log file (one JSON object per line).
  * Optionally also emails it to the committee (guaranteed delivery, even if the
    player never presses Send in their mail app). The recipient address lives only in
    the server's environment, never in this file or on the website.

Run it
  COMPLAINT_LOG=/var/log/dufore/complaints.jsonl \\
  ALLOWED_ORIGIN=https://smartdealsclub.com \\
  python3 complaint_server.py            # listens on 127.0.0.1:8787

  Put it behind your web server over HTTPS, for example an nginx block:
      location /dufore-api/ { proxy_pass http://127.0.0.1:8787/; proxy_set_header X-Forwarded-For $remote_addr; }
  and set TRUST_PROXY=1 so the real visitor IP is logged.
  Then set "logEndpoint" under "complaints" in dufore2026/scores.json to
      https://smartdealsclub.com/dufore-api/complaint

Optional email (all must be set to turn it on)
  MAIL_TO         recipient address
  SMTP_HOST, SMTP_PORT (default 465), SMTP_USER, SMTP_PASS   (most providers need an app password)
  MAIL_FROM       defaults to SMTP_USER
"""
import json, os, smtplib, ssl, sys, threading, time
from datetime import datetime, timezone
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = os.environ.get("COMPLAINT_LOG", "complaints.jsonl")
ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://smartdealsclub.com")
HOST = os.environ.get("BIND", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8787"))
TRUST_PROXY = os.environ.get("TRUST_PROXY") == "1"
MAX_BODY = 8 * 1024
RATE_N, RATE_S = 20, 600  # max 20 posts per IP per 10 minutes (a resort shares one Wi-Fi address)
CATEGORIES = {"Golf rules", "Wellness", "Cleanliness", "Etiquette", "Security", "Accommodation", "Drinks", "Other"}

_hits, _lock = {}, threading.Lock()


def limited(ip):
    now = time.time()
    with _lock:
        q = [t for t in _hits.get(ip, []) if now - t < RATE_S]
        if len(q) >= RATE_N:
            _hits[ip] = q
            return True
        q.append(now)
        _hits[ip] = q
        return False


def clean(v, n):
    return " ".join(str(v or "").replace("\r", " ").split())[:n] if n < 200 else str(v or "").replace("\r", "").strip()[:n]


def write_log(rec):
    d = os.path.dirname(os.path.abspath(LOG))
    os.makedirs(d, exist_ok=True)
    fd = os.open(LOG, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def send_mail(rec):
    need = [os.environ.get(k) for k in ("MAIL_TO", "SMTP_HOST", "SMTP_USER", "SMTP_PASS")]
    if not all(need):
        return None
    m = EmailMessage()
    m["Subject"] = "Dufore Open 2026 complaint · " + rec["category"]
    m["From"] = os.environ.get("MAIL_FROM") or os.environ["SMTP_USER"]
    m["To"] = os.environ["MAIL_TO"]
    m.set_content("Category: %s\nFrom: %s\nContact: %s\nTime: %s\n\n%s\n" % (rec["category"], rec["name"], rec["contact"], rec["time"], rec["message"]))
    try:
        with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "465")), context=ssl.create_default_context(), timeout=20) as s:
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            s.send_message(m)
        return "sent"
    except Exception as e:  # never lose the complaint because mail failed
        return "mail error: %s" % e.__class__.__name__


class H(BaseHTTPRequestHandler):
    server_version = "dufore"

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", ORIGIN)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, code, body=b"{}"):
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _ip(self):
        if TRUST_PROXY:
            xf = self.headers.get("X-Forwarded-For", "")
            if xf:
                return xf.split(",")[0].strip()
        return self.client_address[0]

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_GET(self):
        if self.path.rstrip("/").endswith("/health"):
            return self._send(200, b'{"ok":true}')
        self._send(404)

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/complaint"):
            return self._send(404)
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = 0
        if n <= 0 or n > MAX_BODY:
            return self._send(413)
        ip = self._ip()
        if limited(ip):
            return self._send(429)
        try:
            d = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return self._send(400)
        msg = clean(d.get("message"), 1500)
        if len(msg) < 5 or d.get("_gotcha"):
            return self._send(400 if len(msg) < 5 else 200)
        cat = clean(d.get("category"), 40)
        rec = {
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "ip": ip,
            "ua": clean(self.headers.get("User-Agent"), 160),
            "category": cat if cat in CATEGORIES else "Other",
            "name": clean(d.get("name"), 80) or "Anonymous",
            "contact": clean(d.get("contact"), 120) or "(none given)",
            "message": msg,
        }
        try:
            write_log(rec)
        except Exception as e:
            sys.stderr.write("LOG WRITE FAILED: %s\n" % e)
            return self._send(500)
        status = send_mail(rec)
        if status:
            rec2 = {"time": rec["time"], "mail": status}
            try:
                write_log(rec2)
            except Exception:
                pass
        self._send(200, b'{"ok":true}')

    def log_message(self, fmt, *a):  # keep complaint text out of the access log
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % a if a else fmt))


if __name__ == "__main__":
    print("Dufore complaint logger on http://%s:%d  log=%s  mail=%s" % (HOST, PORT, os.path.abspath(LOG), "on" if os.environ.get("MAIL_TO") else "off"))
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
