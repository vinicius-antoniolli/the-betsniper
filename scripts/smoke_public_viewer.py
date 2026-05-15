from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def _get(url: str, timeout: float = 3.0) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
        return int(response.status), body


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test do viewer publico Streamlit.")
    parser.add_argument("--port", type=int, default=8509)
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()

    env = os.environ.copy()
    env["PUBLIC_VIEWER_MODE"] = "true"
    env["BETFAIR_WEB_ENABLED"] = "false"
    env["X_AUTO_PUBLISH_ENABLED"] = "false"
    env.setdefault("APP_DB_URL", "sqlite:///public_data/betsniper_public.db")

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "streamlit_app.py",
        "--server.port",
        str(args.port),
        "--server.headless",
        "true",
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.time() + args.timeout
        health_url = f"http://127.0.0.1:{args.port}/_stcore/health"
        page_url = f"http://127.0.0.1:{args.port}"
        while time.time() < deadline:
            try:
                status, body = _get(health_url, timeout=2.0)
                if status == 200 and body.strip().lower() == "ok":
                    page_status, _ = _get(page_url, timeout=5.0)
                    print(f"HEALTH={body.strip()}")
                    print(f"PAGE_STATUS={page_status}")
                    return
            except (OSError, urllib.error.URLError):
                time.sleep(1)
        output = ""
        if process.stdout:
            output = process.stdout.read()[-4000:]
        raise RuntimeError(f"Streamlit public viewer health timeout.\n{output}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
