"""Run the isolated backend and Next development UI; Ctrl+C stops both."""

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from demo_fixtures import DEMO_QUERY, DEMO_SUBMISSION_URL, DEMO_TOKEN

ROOT = Path(__file__).resolve().parents[1]


def unused_port(port):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def wait_ready(url, process, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited with {process.returncode}: {url}")
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            pass
        time.sleep(0.3)
    raise RuntimeError(f"server did not become ready: {url}")


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == "posix":
        os.killpg(process.pid, signal.SIGTERM)
    else:
        process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web-port", type=int, default=3102)
    parser.add_argument("--api-port", type=int, default=8102)
    args = parser.parse_args()
    if args.web_port == args.api_port or not all(1 <= p <= 65535 for p in (args.web_port, args.api_port)):
        parser.error("use two different ports between 1 and 65535")
    try:
        unused_port(args.web_port)
        unused_port(args.api_port)
    except OSError as exc:
        parser.error(f"port unavailable; no existing service was stopped: {exc}")
    web = ROOT / "apps/web"
    next_bin = web / "node_modules/next/dist/bin/next"
    if not next_bin.is_file():
        parser.error("install web dependencies first: cd apps/web && npm ci")

    processes = []
    next_env = web / "next-env.d.ts"
    original = next_env.read_bytes()
    api_url = f"http://127.0.0.1:{args.api_port}"
    web_url = f"http://127.0.0.1:{args.web_port}"

    def stop_on_signal(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop_on_signal)
    try:
        backend = subprocess.Popen(
            [sys.executable, str(ROOT / "ops/demo_server.py"), "--port", str(args.api_port)],
            cwd=ROOT / "apps/backend",
            start_new_session=os.name == "posix",
        )
        processes.append(backend)
        wait_ready(f"{api_url}/health/ready", backend)
        frontend = subprocess.Popen(
            ["node", str(next_bin), "dev", "--hostname", "127.0.0.1", "--port", str(args.web_port)],
            cwd=web,
            env={
                **os.environ,
                "API_INTERNAL_URL": api_url,
                "NEXT_DIST_DIR": ".next-demo",
                "CYBER_MEMOIR_DEMO": "1",
                "NEXT_TELEMETRY_DISABLED": "1",
            },
            start_new_session=os.name == "posix",
        )
        processes.append(frontend)
        wait_ready(web_url, frontend)
        print(
            f"\n本地演示已就绪：{web_url}\n"
            f"合成数据 · 临时数据库 · 不读取业务 .env · 不调用平台或模型\n"
            f"检索示例：{DEMO_QUERY}\n审核：{web_url}/review\n演示令牌：{DEMO_TOKEN}\n"
            f"合成提交链接：{DEMO_SUBMISSION_URL}\nCtrl+C 停止，演示数据随即清理。\n",
            flush=True,
        )
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        raise RuntimeError("a demo server exited; stopping the other server")
    except KeyboardInterrupt:
        return 0
    except (OSError, RuntimeError) as exc:
        print(f"demo: {exc}", file=sys.stderr)
        return 1
    finally:
        for process in reversed(processes):
            stop_process(process)
        # Restore only the import lines Next generated, not concurrent user edits.
        current = next_env.read_text()
        before = original.decode()
        if current != before:
            normalized = current
            for line in current.splitlines(keepends=True):
                if line.startswith('import "./.next-demo/'):
                    suffix = line.split("/dev/types/", 1)[-1]
                    replacement = next(
                        (x for x in before.splitlines(keepends=True) if x.endswith(suffix)), line
                    )
                    normalized = normalized.replace(line, replacement)
            if normalized == before:
                next_env.write_bytes(original)


if __name__ == "__main__":
    raise SystemExit(main())
