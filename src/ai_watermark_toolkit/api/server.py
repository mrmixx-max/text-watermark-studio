from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ..pipeline import detect_text, run_pipeline
from ..transform.clean import clean_text
from ..transform.dilute import dilute_text

WEB_ROOT = Path(__file__).resolve().parents[1] / "web"


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, path: Path):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self._html(WEB_ROOT / "index.html")
        if parsed.path == "/health":
            return self._json(200, {"ok": True})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        data = json.loads(raw)
        text = data.get("text", "")
        if parsed.path == "/api/detect":
            return self._json(200, detect_text(text, lang=data.get("lang", "auto")))
        if parsed.path == "/api/clean":
            return self._json(
                200,
                clean_text(
                    text, nfkc=data.get("nfkc", False), fold_confusables=data.get("fold_confusables", False)
                ).to_dict(),
            )
        if parsed.path == "/api/dilute":
            return self._json(200, dilute_text(text, intensity=data.get("intensity", "standard")).to_dict())
        if parsed.path == "/api/pipeline":
            out, report = run_pipeline(text, lang=data.get("lang", "auto"), intensity=data.get("intensity", "standard"))
            return self._json(200, {"text": out, "report": report})
        return self._json(404, {"error": "not found"})


def serve(host: str = "127.0.0.1", port: int = 8080):
    server = HTTPServer((host, port), Handler)
    server.serve_forever()
