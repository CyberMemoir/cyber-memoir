"""Exercise subprocess ownership and failures against an explicit local fixture server."""

import json
import os
import signal
import sqlite3
import subprocess
import sys
import threading
from collections import Counter
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


@contextmanager
def fixture(tmp_path, mode):
    calls = Counter()
    gold = tmp_path / "gold.jsonl"
    raw = (
        json.dumps(
            {
                "query": "synthetic-q",
                "expected_names": ["synthetic-target"],
                "answerable": True,
                "bucket": "canonical",
            }
        )
        + "\n"
    )
    if mode == "interrupted":
        row = json.loads(raw)
        raw = "".join(
            json.dumps({**row, "query": query}) + "\n" for query in ("synthetic-first", "synthetic-last")
        )
    gold.write_text(raw, encoding="utf-8")
    context = tmp_path / "context.json"
    context.write_text(
        json.dumps(
            {
                "model": {"identifier": "synthetic-only", "sha256": "0" * 64},
                "configuration": {"fixture": True},
            }
        ),
        encoding="utf-8",
    )
    evidence = {"id": "e1", "text": "synthetic evidence", "verified": True}
    claim = {
        "key": "definition",
        "statement": "synthetic statement",
        "meme_name": "synthetic-target",
        "evidence_ids": ["e1"],
    }
    record = {
        "id": "m1",
        "canonical_name": "synthetic-target",
        "aliases": [],
        "published_revision": 1,
        "claims": [claim],
        "events": [],
        "relations": [],
        "evidence": [evidence],
    }
    entered, release = threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, payload, status=200):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except ConnectionError:
                # An intentionally interrupted process no longer receives its reply.
                pass

        def do_GET(self):
            calls[self.path] += 1
            if self.path == "/v1/universe":
                if mode == "end_snapshot_failure" and calls[self.path] == 2:
                    self.reply({"detail": "synthetic end failure"}, 503)
                else:
                    self.reply({"galaxies": [] if mode == "missing_target" else [{"meme_id": "m1"}]})
            elif self.path == "/v1/memes/m1":
                self.reply(record)
            elif mode == "citation_failure" and calls[self.path] == 2:
                self.reply({"detail": "synthetic evidence request failure"}, 503)
            else:
                self.reply(evidence)

        def do_POST(self):
            query = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["query"]
            calls[self.path] += 1
            calls[(self.path, query)] += 1
            if (
                mode == "interrupted"
                and self.path == "/v1/search"
                and query == "synthetic-last"
                and calls[(self.path, query)] == 1
            ):
                entered.set()
                release.wait(timeout=15)
            if self.path == "/v1/search":
                if mode == "gold_changed":
                    gold.write_text(raw + "\n", encoding="utf-8")
                if mode == "malformed" and calls[self.path] == 1:
                    self.reply({"items": None})
                else:
                    self.reply(
                        {
                            "items": [record],
                            "degraded": ["corpus_changed_during_search"]
                            if mode == "changed_during_case"
                            else [],
                        }
                    )
            else:
                self.reply({"claims": [claim], "citations": [{"evidence_id": "e1"}]})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    journal = tmp_path / "audit.sqlite"
    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "evals/run.py"),
        str(gold),
        "--api",
        f"http://127.0.0.1:{server.server_port}",
        "--checkpoint",
        str(journal),
        "--run-context",
        str(context),
    ]

    def run():
        process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30)
        return process, json.loads(process.stdout)

    run.command = command
    run.entered, run.release = entered, release

    try:
        yield run, calls, journal, gold, raw
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("mode", ["citation_failure", "malformed"])
def test_failed_case_is_not_committed_and_retries(mode, tmp_path):
    with fixture(tmp_path, mode) as (run, calls, journal, gold, raw):
        first, report = run()
        assert first.returncode == 1
        assert report["status"] == "failed" and report["recall_at_10"] is None
        with sqlite3.connect(journal) as db:
            assert db.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 0
        second, report = run()
        assert second.returncode == 0, second.stderr
        assert report["recall_at_10"] == 1
        assert calls["/v1/search"] == 2


@pytest.mark.parametrize("mode", ["gold_changed", "changed_during_case"])
def test_content_changes_permanently_invalidate_journal(mode, tmp_path):
    with fixture(tmp_path, mode) as (run, calls, journal, gold, raw):
        first, report = run()
        assert first.returncode == 1
        assert report["recall_at_10"] is None
        with sqlite3.connect(journal) as db:
            assert db.execute("SELECT status FROM run").fetchone()[0] == "invalid"
        gold.write_text(raw, encoding="utf-8")
        second, report = run()
        assert second.returncode == 1
        assert "invalidated" in report["failed"][0]["detail"]
        assert calls["/v1/search"] == 1


def test_final_network_failure_keeps_completed_case_for_verified_resume(tmp_path):
    with fixture(tmp_path, "end_snapshot_failure") as (run, calls, journal, gold, raw):
        first, report = run()
        assert first.returncode == 1 and report["recall_at_10"] is None
        second, report = run()
        assert second.returncode == 0
        assert report["recall_at_10"] == 1
        assert calls["/v1/search"] == calls["/v1/answers"] == 1


def test_non_public_positive_target_is_not_misreported_as_retrieval_failure(tmp_path):
    with fixture(tmp_path, "missing_target") as (run, calls, journal, gold, raw):
        process, report = run()
        assert process.returncode == 1
        assert "not currently public" in report["failed"][0]["detail"]
        assert not calls["/v1/search"]
        assert not journal.exists()


def test_actual_interruption_releases_lock_and_resumes_only_unfinished_case(tmp_path):
    with fixture(tmp_path, "interrupted") as (run, calls, journal, gold, raw):
        process = subprocess.Popen(
            run.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8"
        )
        try:
            assert run.entered.wait(timeout=10), "The second case did not reach the fixture server"
            assert process.poll() is None
            if os.name == "nt":
                # Windows cannot deliver SIGINT to an arbitrary console process.
                process.terminate()
            else:
                process.send_signal(signal.SIGINT)
            process.communicate(timeout=10)
            assert process.returncode != 0
            with sqlite3.connect(journal) as db:
                assert db.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 1
            run.release.set()
            second, report = run()
            assert second.returncode == 0, second.stderr
            assert report["recall_at_10"] == 1
            assert calls[("/v1/search", "synthetic-first")] == calls[("/v1/answers", "synthetic-first")] == 1
            assert calls[("/v1/search", "synthetic-last")] == 2
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
