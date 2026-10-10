"""Read-only database/public-artifact capture; never stop, migrate or publish in the source stack."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import httpx
from checkpoint import collect_public_snapshot, digest


def capture(api, postgres_container, project, out):
    parsed = urlparse(api)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.username
        or parsed.password
    ):
        raise ValueError("capture only accepts the explicitly configured loopback public API")
    info = json.loads(subprocess.check_output(["docker", "inspect", postgres_container]))[0]
    if (
        not info["State"]["Running"]
        or info["Config"]["Labels"].get("com.docker.compose.project") != project
        or info["Config"]["Labels"].get("com.docker.compose.service") != "postgres"
    ):
        raise ValueError("source container is not the requested running project's PostgreSQL service")
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    with httpx.Client(base_url=api, timeout=60, trust_env=False) as client:
        before = collect_public_snapshot(client)
        with (out / "postgres.dump").open("xb") as stream:
            os.chmod(stream.name, 0o600)
            subprocess.run(
                [
                    "docker",
                    "exec",
                    postgres_container,
                    "pg_dump",
                    "-U",
                    "memoir",
                    "-d",
                    "memoir",
                    "-Fc",
                    "--no-owner",
                    "--no-acl",
                ],
                stdout=stream,
                check=True,
            )
        artifacts = {}
        for record in before["evidence"]:
            sha = record["artifact_hash"]
            if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
                raise ValueError("public evidence lacks a content-addressed artifact hash")
            if sha in artifacts:
                continue
            response = client.get(f"/v1/evidence/{record['id']}/artifact")
            response.raise_for_status()
            body = response.content
            if hashlib.sha256(body).hexdigest() != sha:
                raise ValueError("public artifact bytes differ from the saved evidence hash")
            target = out / "objects" / "sha256" / sha[:2] / sha
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            artifacts[sha] = {"bytes": len(body), "evidence_id": record["id"]}
        if digest(before) != digest(collect_public_snapshot(client)):
            raise ValueError("source public records changed during capture; no valid manifest written")
    result = {
        "source_api": api,
        "source_public_sha256": digest(before),
        "dump_sha256": hashlib.sha256((out / "postgres.dump").read_bytes()).hexdigest(),
        "records": len(before["records"]),
        "evidence": len(before["evidence"]),
        "artifacts": artifacts,
        "source_postgres_image": info["Image"],
    }
    (out / "public.json").write_text(
        json.dumps(before, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    (out / "manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True)
    parser.add_argument("--postgres-container", required=True)
    parser.add_argument("--source-project", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = capture(args.api, args.postgres_container, args.source_project, args.out.resolve())
    print(
        json.dumps(
            {key: result[key] for key in ["source_public_sha256", "dump_sha256", "records", "evidence"]}
        )
    )


if __name__ == "__main__":
    main()
