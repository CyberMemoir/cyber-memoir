"""Archive capture is read-only and does not certify unstable or corrupt inputs."""

import hashlib
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def capture(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "evals"))
    return importlib.import_module("capture_archive")


@pytest.mark.parametrize("api", ["https://127.0.0.1:8100", "http://example.org", "http://token@localhost"])
def test_capture_rejects_nonlocal_or_credential_url(capture, tmp_path, api):
    with pytest.raises(ValueError, match="loopback"):
        capture.capture(api, "unused", "unused", tmp_path / "new")
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize("change", ["project", "service", "stopped"])
def test_capture_refuses_unrelated_source_container(capture, monkeypatch, tmp_path, change):
    labels = {"com.docker.compose.project": "synthetic", "com.docker.compose.service": "postgres"}
    info = {"State": {"Running": change != "stopped"}, "Config": {"Labels": labels}}
    if change in ["project", "service"]:
        labels[f"com.docker.compose.{change}"] = "unrelated"
    monkeypatch.setattr(capture.subprocess, "check_output", lambda *args: json.dumps([info]).encode())
    with pytest.raises(ValueError, match="requested running"):
        capture.capture("http://127.0.0.1:8100", "synthetic-pg", "synthetic", tmp_path / "new")
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize("change", ["none", "artifact", "snapshot"])
def test_readonly_capture_verifies_bytes_and_final_snapshot(capture, monkeypatch, tmp_path, change):
    body = b"synthetic evidence, not cultural facts"
    sha = hashlib.sha256(body).hexdigest()
    snapshot = {"records": [], "evidence": [{"id": "synthetic-id", "artifact_hash": sha}]}
    info = {
        "State": {"Running": True},
        "Config": {
            "Labels": {
                "com.docker.compose.project": "synthetic",
                "com.docker.compose.service": "postgres",
            }
        },
        "Image": "synthetic-image",
    }
    calls = []
    monkeypatch.setattr(capture.subprocess, "check_output", lambda *args: json.dumps([info]).encode())

    def dump(command, stdout, check):
        calls.append(command)
        stdout.write(b"synthetic database")

    monkeypatch.setattr(capture.subprocess, "run", dump)
    snapshots = iter(
        [snapshot, {"records": ["changed"], "evidence": []} if change == "snapshot" else snapshot]
    )
    monkeypatch.setattr(capture, "collect_public_snapshot", lambda client: next(snapshots))

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, path):
            assert path == "/v1/evidence/synthetic-id/artifact"
            return capture.httpx.Response(
                200,
                content=b"corrupt" if change == "artifact" else body,
                request=capture.httpx.Request("GET", "http://127.0.0.1" + path),
            )

    monkeypatch.setattr(capture.httpx, "Client", lambda **kwargs: Client())
    out = tmp_path / "new"
    if change == "none":
        result = capture.capture("http://127.0.0.1:8100", "synthetic-pg", "synthetic", out)
        assert result["source_public_sha256"] == capture.digest(snapshot)
        assert (out.stat().st_mode & 0o777) == 0o700
        assert ((out / "postgres.dump").stat().st_mode & 0o777) == 0o600
        assert (out / "objects" / "sha256" / sha[:2] / sha).read_bytes() == body
    else:
        with pytest.raises(ValueError):
            capture.capture("http://127.0.0.1:8100", "synthetic-pg", "synthetic", out)
        assert not (out / "manifest.json").exists()
    assert len(calls) == 1
    assert calls[0][:4] == ["docker", "exec", "synthetic-pg", "pg_dump"]
    assert "--no-owner" in calls[0] and "--no-acl" in calls[0]
