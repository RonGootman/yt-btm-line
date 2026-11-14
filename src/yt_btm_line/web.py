"""Local mobile-browser fallback. Put authenticated HTTPS in front for remote access."""

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from .extractor import extract
from .models import ExtractionError
from .summary import instructions

PAGE = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YouTube bottom line</title><style>
body{font:18px system-ui;max-width:44rem;margin:auto;padding:1rem}input,button,textarea{
font:inherit;box-sizing:border-box;width:100%;padding:.7rem;margin:.5rem 0}textarea{height:22rem}
</style><h1>Get the bottom line</h1><p>Extract public captions, then copy the result into your
AI assistant. Extraction is free of model API dependencies. A separate manual paste is required.</p>
<form id="form"><label>YouTube URL<input name="url" required maxlength="2048"></label>
<label>Language (optional)<input name="language" placeholder="en or he"></label>
<button>Extract captions</button></form><p id="status" role="status"></p>
<label>Summary instructions and transcript<textarea id="result" readonly></textarea></label>
<button id="copy">Copy for your assistant</button><script>
const result=document.getElementById('result'),status=document.getElementById('status');
document.getElementById('form').onsubmit=async e=>{e.preventDefault();status.textContent='Extracting…';
try{const r=await fetch('/extract',{method:'POST',body:new URLSearchParams(new FormData(e.target))});
const d=await r.json();if(!r.ok)throw Error(d.error.message);result.value=d.prompt+'\\n\\n'+
JSON.stringify(d.transcript);status.textContent='Ready. Copy and paste into your AI assistant.'}
catch(e){status.textContent=e.message}};
document.getElementById('copy').onclick=async()=>{try{await navigator.clipboard.writeText(result.value);
status.textContent='Copied'}catch(e){status.textContent='Select the text and copy manually'}};
</script></html>"""
SLOT = threading.BoundedSemaphore(2)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass  # Do not log personal video URLs or transcripts.

    def reply(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'unsafe-inline'; "
            "style-src 'unsafe-inline'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self.reply(
            200 if self.path == "/" else 404,
            PAGE.encode() if self.path == "/" else b"Not found",
            "text/html; charset=utf-8",
        )

    def do_POST(self) -> None:
        self.connection.settimeout(10)
        if self.path != "/extract":
            self.reply(404, b"{}", "application/json")
            return
        # Reject cross-site browser requests; no CORS and only form-encoded requests supported.
        if self.headers.get("Sec-Fetch-Site") == "cross-site" or (
            self.headers.get("Origin")
            and self.headers["Origin"] != f"http://{self.headers.get('Host')}"
        ):
            self.reply(403, b"{}", "application/json")
            return
        acquired = False
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ExtractionError("invalid_request", "Request body must be 1–4096 bytes.")
            acquired = SLOT.acquire(blocking=False)
            if not acquired:
                raise ExtractionError("busy", "Try again shortly.")
            form = parse_qs(self.rfile.read(length).decode("utf-8"))
            transcript = extract(form.get("url", [""])[0], form.get("language", [None])[0])
            self.reply(
                200,
                json.dumps(
                    {"transcript": transcript.model_dump(), "prompt": instructions()},
                    ensure_ascii=False,
                ).encode(),
                "application/json; charset=utf-8",
            )
        except (ExtractionError, ValueError, UnicodeError) as exc:
            error = (
                exc.as_dict()
                if isinstance(exc, ExtractionError)
                else {"code": "invalid_request", "message": "Invalid request body."}
            )
            self.reply(400, json.dumps({"error": error}).encode(), "application/json")
        finally:
            if acquired:
                SLOT.release()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Local web fallback; no hosted model or public service"
    )
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
