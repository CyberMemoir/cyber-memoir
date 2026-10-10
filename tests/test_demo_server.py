"""Real subprocess demo smoke test; only fictional fixtures, no external services."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from review_requests import matching_revision

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "local-synthetic-demo-only"
URL = "https://www.bilibili.com/video/BV1DEMO00002"


def test_demo_port_probe_refuses_live_server_but_allows_recent_restart(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "ops"))
    from demo import unused_port

    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        server.listen(1)
        with pytest.raises(OSError):
            unused_port(port)
        with socket.create_connection(("127.0.0.1", port)):
            connection, _ = server.accept()
            connection.close()  # server-side TIME_WAIT must not block a restart
    unused_port(port)


def eventually(get, predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = get()
            if predicate(value):
                return value
        except httpx.TransportError:
            pass
        time.sleep(0.15)
    raise AssertionError("demo did not reach the expected state")


def test_demo_is_isolated_and_runs_real_search_review_and_worker(tmp_path):
    business = tmp_path / "business.sqlite"
    marker = b"do not open this deployment database"
    business.write_bytes(marker)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with (tmp_path / "server.log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "ops/demo_server.py"), "--port", str(port)],
            cwd=ROOT / "apps/backend",
            env={
                **os.environ,
                "DATABASE_URL": f"sqlite:///{business}",
                "REVIEWER_TOKEN": "deployment-token-not-for-demo",
                "LLM_BASE_URL": "https://example.invalid/should-not-be-called",
                "LLM_MODEL": "must-be-disabled",
                "EMBEDDING_BACKEND": "bge",
                "RERANKER_BACKEND": "bge",
                "TMPDIR": str(runtime),
                "TEMP": str(runtime),
                "TMP": str(runtime),
            },
            stdout=log,
            stderr=log,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5) as client:
                ready = eventually(lambda: client.get("/health/ready"), lambda r: r.status_code == 200)
                assert ready.headers["X-Cyber-Memoir-Demo"] == "synthetic-only"
                assert business.read_bytes() == marker
                auth = {"Authorization": f"Bearer {TOKEN}"}
                assert client.get("/v1/reviews").status_code == 401
                assert (
                    client.get(
                        "/v1/reviews", headers={"Authorization": "Bearer deployment-token-not-for-demo"}
                    ).status_code
                    == 401
                )
                search = client.post("/v1/search", json={"query": "合成星灯"})
                assert search.status_code == 200, search.text
                public_id = search.json()["items"][0]["id"]
                detail = client.get(f"/v1/memes/{public_id}").json()
                assert "虚构" in detail["definition"]
                assert detail["origin_status"] == "unknown"
                assert detail["events"][0]["time_precision"] == "month"
                atlas = client.get("/v1/universe").json()
                assert len(atlas["galaxies"]) == 2
                assert all(g["stars"] and g["emergence"]["date"] for g in atlas["galaxies"])
                assert len(atlas["links"]) == 1
                answer = client.post("/v1/answers", json={"query": "合成星灯"})
                assert answer.status_code == 200, answer.text
                assert answer.json()["citations"]
                citation = answer.json()["citations"][0]
                assert client.get(f"/v1/evidence/{citation['evidence_id']}").status_code == 200

                queue = client.get("/v1/reviews/queue", headers=auth).json()
                assert len(queue["items"]) == 1
                draft = queue["items"][0]
                assert draft["payload"]["canonical_name"] == "合成演示：等待审核"
                ids = draft["payload"]["claims"][0]["evidence_ids"]
                approved = client.post(
                    f"/v1/reviews/{draft['id']}/decision",
                    json={
                        "decision": "approve",
                        "reason": "合成演示软件验收，不是真实文化审核。",
                        "verified_evidence_ids": ids,
                    },
                    headers=matching_revision(client, auth, f"/v1/reviews/{draft['id']}/decision"),
                )
                assert approved.status_code == 200, approved.text
                meme_id = approved.json()["meme_id"]
                assert client.get(f"/v1/memes/{meme_id}").status_code == 200
                retracted = client.post(
                    f"/v1/reviews/memes/{meme_id}/retract",
                    json={"reason": "合成演示闭环验收结束"},
                    headers=auth,
                )
                assert retracted.status_code == 200, retracted.text
                assert client.get(f"/v1/memes/{meme_id}").status_code == 404

                for url in ("https://b23.tv/synthetic", "https://www.bilibili.com/video/BV1TEST00001"):
                    assert client.post("/v1/submissions", json={"url": url}).status_code == 422
                assert client.post("/v1/submissions", content="[]").status_code == 422
                submitted = client.post("/v1/submissions", json={"url": URL})
                assert submitted.status_code == 202, submitted.text
                source_id = submitted.json()["source"]["id"]
                media = client.post(f"/v1/sources/{source_id}/media")
                assert media.status_code == 422
                eventually(
                    lambda: client.get("/v1/reviews/queue", headers=auth).json(),
                    lambda q: any(
                        r["payload"]["canonical_name"] == "合成演示：新提交的材料" for r in q["items"]
                    ),
                )
                assert business.read_bytes() == marker
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    assert not list(runtime.glob("cyber-memoir-demo-*"))
