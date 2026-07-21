"""Local report viewer and bounded analysis bridge."""

import json
import sqlite3
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"
PYTHON = ROOT / ".venv/bin/python"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/card-names"):
            self.card_names()
            return
        path = "/index.html" if self.path == "/" else self.path
        target = (UI / path.lstrip("/")).resolve()
        if UI not in target.parents or not target.is_file():
            self.send_error(404)
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html" if target.suffix == ".html" else "text/css" if target.suffix == ".css" else "text/javascript")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def card_names(self):
        from urllib.parse import parse_qs, urlparse
        ids = [int(value) for value in parse_qs(urlparse(self.path).query).get("ids", [])][:200]
        if not ids:
            self._json(200, {})
            return
        connection = sqlite3.connect(ROOT / "assets/cards.cdb")
        rows = connection.execute(
            "SELECT id, name FROM texts WHERE id IN (%s)" % ",".join("?" * len(ids)), ids
        ).fetchall()
        connection.close()
        self._json(200, {str(card_id): name for card_id, name in rows})

    def do_POST(self):
        if self.path != "/api/analyze":
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", 0))
            request = json.loads(self.rfile.read(size))
            hands = max(1, min(int(request.get("hands", 4)), 100))
            nodes = max(1, min(int(request.get("max_nodes", 100)), 20000))
            depth = max(1, min(int(request.get("max_depth", 40)), 180))
            interruption = str(request.get("interruption", "ash"))
            if interruption != "all" and interruption not in {"ash", "veiler", "impermanence", "droll", "nibiru", "ghost_ogre"}:
                raise ValueError("unsupported interruption")
            interpreter = str(PYTHON) if PYTHON.is_file() else sys.executable
            command = [interpreter, "tools/analyze_consistency.py", "--hands", str(hands),
                       "--interruption", interruption, "--max-nodes", str(nodes),
                       "--max-depth", str(depth), "--workers", "1"]
            if request.get("extenders"):
                command.append("--extenders")
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=300, check=True)
            self._json(200, json.loads(result.stdout))
        except Exception as error:
            self._json(400, {"error": str(error)})

    def _json(self, status, value):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"YAPPING workbench: http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
