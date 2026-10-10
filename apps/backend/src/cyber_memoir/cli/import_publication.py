"""python -m cyber_memoir.cli.import_publication validate|dry-run|import DIRECTORY"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

from cyber_memoir.domain.publications import PublicationPackage


def read_package(directory: Path) -> PublicationPackage:
    entries_path, manifest_path = directory / "entries.jsonl", directory / "manifest.json"
    if entries_path.stat().st_size > 8_000_000 or manifest_path.stat().st_size > 100_000:
        raise ValueError("数据包超过大小限制")
    package = PublicationPackage.model_validate(
        {
            "manifest": json.loads(manifest_path.read_text(encoding="utf-8")),
            # Read bytes: universal newline conversion would invalidate a Windows file hash.
            "entries_jsonl": entries_path.read_bytes().decode("utf-8"),
        }
    )
    package.entries()
    return package


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="校验或导入已采集的跨平台材料；只生成待审稿。")
    parser.add_argument("command", choices=("validate", "dry-run", "import"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--api", default="http://127.0.0.1:8100")
    parser.add_argument("--plan-hash", help="确认预演结果；状态变化时拒绝导入")
    args = parser.parse_args(argv)
    try:
        package = read_package(args.directory)
        rows = package.entries()
        if args.command == "validate":
            result = {
                "valid": True,
                "groups": len(rows),
                "new_groups": package.manifest.new_groups,
                "existing_groups": package.manifest.existing_groups,
                "meme_source_associations": package.manifest.meme_source_associations,
                "entries_sha256": package.manifest.entries_sha256,
                "note": "仅完成文件校验；追加目标、审核状态与重复导入需在线预演。",
            }
        else:
            token = os.environ.get("REVIEWER_TOKEN", "")
            if not token:
                raise ValueError("在线操作需要环境变量 REVIEWER_TOKEN")
            api = urlparse(args.api)
            if api.username or api.password or api.query or api.fragment or not api.hostname:
                raise ValueError("API 地址不能包含凭据、查询参数或片段")
            if api.scheme != "https" and not (
                api.scheme == "http" and api.hostname in {"localhost", "127.0.0.1", "::1"}
            ):
                raise ValueError("远程 API 必须使用 HTTPS")
            path = "/v1/reviews/imports/validate" if args.command == "dry-run" else "/v1/reviews/imports"
            with httpx.Client(
                base_url=args.api, timeout=120, trust_env=False, follow_redirects=False
            ) as client:
                response = client.post(
                    path,
                    json=package.model_dump(mode="json"),
                    headers={"Authorization": f"Bearer {token}"},
                    params={"expected_plan_hash": args.plan_hash}
                    if args.plan_hash and args.command == "import"
                    else None,
                )
                response.raise_for_status()
                result = response.json()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("can_import", True) else 2
    except httpx.HTTPStatusError as exc:
        # Do not print the request headers, token, or untrusted redirect URLs.
        print(f"API 拒绝请求 ({exc.response.status_code})：{exc.response.text}", file=sys.stderr)
    except (ValueError, OSError, httpx.RequestError) as exc:
        print(f"导入未完成：{exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
