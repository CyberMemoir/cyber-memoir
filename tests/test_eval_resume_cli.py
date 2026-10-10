import json
import subprocess
import sys
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def test_cli_retries_failed_case_without_repeating_committed_cases(tmp_path):
    calls = Counter()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, payload, status=200):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/v1/universe":
                self.reply({"galaxies": [{"meme_id": q} for q in ("synthetic-a", "synthetic-b")]})
            else:
                query = self.path.rsplit("/", 1)[-1]
                self.reply(
                    {
                        "id": query,
                        "canonical_name": query,
                        "aliases": [],
                        "published_revision": 1,
                        "claims": [],
                        "events": [],
                        "relations": [],
                        "evidence": [],
                    }
                )

        def do_POST(self):
            query = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["query"]
            calls[(self.path, query)] += 1
            if self.path == "/v1/search":
                if query == "synthetic-b" and calls[(self.path, query)] == 1:
                    self.reply({"detail": "synthetic interruption"}, 503)
                else:
                    self.reply({"items": [{"canonical_name": query, "aliases": []}], "degraded": []})
            else:
                self.reply({"claims": [], "citations": []})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        gold = tmp_path / "gold.jsonl"
        gold.write_text(
            "".join(
                json.dumps({"query": q, "expected_names": [q], "answerable": True, "bucket": "description"})
                + "\n"
                for q in ("synthetic-a", "synthetic-b")
            ),
            encoding="utf-8",
        )
        context = tmp_path / "context.json"
        context.write_text(
            json.dumps(
                {
                    "model": {"identifier": "synthetic-test-only", "sha256": "0" * 64},
                    "configuration": {"fixture": True},
                }
            ),
            encoding="utf-8",
        )
        command = [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "evals/run.py"),
            str(gold),
            "--api",
            f"http://127.0.0.1:{server.server_port}",
            "--checkpoint",
            str(tmp_path / "audit.sqlite"),
            "--run-context",
            str(context),
        ]
        first = subprocess.run(command, capture_output=True, text=True, timeout=30, encoding="utf-8")
        assert first.returncode == 1, first.stderr
        assert json.loads(first.stdout)["recall_at_10"] is None
        second = subprocess.run(command, capture_output=True, text=True, timeout=30, encoding="utf-8")
        assert second.returncode == 0, second.stderr
        assert json.loads(second.stdout)["recall_at_10"] == 1
        assert calls[("/v1/search", "synthetic-a")] == 1
        assert calls[("/v1/answers", "synthetic-a")] == 1
        assert calls[("/v1/search", "synthetic-b")] == 2
        gold.write_text(gold.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        changed = subprocess.run(command, capture_output=True, text=True, timeout=30, encoding="utf-8")
        assert changed.returncode != 0
        assert "context changed" in changed.stdout
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
