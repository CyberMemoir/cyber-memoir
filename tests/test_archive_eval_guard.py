"""Evaluation endpoints must belong to the labeled run, not another local service."""

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "ops"))
    return importlib.import_module("archive_eval_server")


@pytest.mark.parametrize("change", ["label", "port", "interface", "stopped"])
def test_owned_endpoint_refuses_wrong_identity(module, monkeypatch, change):
    info = {
        "Config": {"Labels": {"cyber-memoir-evaluation": "synthetic-run"}},
        "State": {"Running": True},
        "NetworkSettings": {"Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55433"}]}},
        "Image": "synthetic-image",
    }
    if change == "label":
        info["Config"]["Labels"]["cyber-memoir-evaluation"] = "someone-else"
    elif change == "port":
        info["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"] = "55432"
    elif change == "interface":
        info["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostIp"] = "0.0.0.0"
    else:
        info["State"]["Running"] = False
    monkeypatch.setattr(module.subprocess, "check_output", lambda *args: json.dumps([info]).encode())
    with pytest.raises(ValueError):
        module.owned_container("synthetic-container", "synthetic-run", 5432, 55433)


def test_owned_endpoint_keeps_pinned_image_identity(module, monkeypatch):
    info = {
        "Config": {"Labels": {"cyber-memoir-evaluation": "synthetic-run"}},
        "State": {"Running": True},
        "NetworkSettings": {"Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55433"}]}},
        "Image": "synthetic-image",
    }
    monkeypatch.setattr(module.subprocess, "check_output", lambda *args: json.dumps([info]).encode())
    assert module.owned_container("synthetic-container", "synthetic-run", 5432, 55433) == "synthetic-image"


@pytest.mark.parametrize("mode,index", [("off", False), ("hybrid", True)])
def test_paired_profiling_rejects_disabled_or_index_only_before_access(module, monkeypatch, mode, index):
    monkeypatch.setattr(
        "sys.argv",
        [
            "archive_eval_server",
            "--snapshot",
            "synthetic",
            "--run-id",
            "synthetic",
            "--database-url",
            "synthetic",
            "--search-url",
            "synthetic",
            "--pg-container",
            "synthetic",
            "--search-container",
            "synthetic",
            "--mode",
            mode,
            "--compare-cpu-rerank",
            *(["--index-only"] if index else []),
        ],
    )
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
