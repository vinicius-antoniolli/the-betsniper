from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from config import settings


CHROMIUM_EXECUTABLE_ENV = "PLAYWRIGHT_CHROMIUM_EXECUTABLE"
CHROMIUM_EXECUTABLE_FALLBACK_ENV = "CHROMIUM_EXECUTABLE_PATH"
SYSTEM_CHROMIUM_CANDIDATES = (
    "chromium",
    "chromium-browser",
    "google-chrome-stable",
    "google-chrome",
    "msedge",
)
SYSTEM_CHROMIUM_PATHS = (
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/google-chrome",
    "/snap/bin/chromium",
)
DEFAULT_CHROMIUM_ARGS = (
    "--disable-quic",
    "--disable-features=UseDnsHttpsSvcb,UseHttpsSvcbAlpn,EncryptedClientHello",
    "--disable-dev-shm-usage",
    "--no-sandbox",
)


def _resolve_executable(value: str | None) -> str | None:
    if not value:
        return None
    expanded = Path(value).expanduser()
    if expanded.exists():
        return str(expanded)
    return shutil.which(value)


def chromium_executable_path() -> str | None:
    configured = (
        settings.playwright_chromium_executable
        or os.environ.get(CHROMIUM_EXECUTABLE_ENV)
        or os.environ.get(CHROMIUM_EXECUTABLE_FALLBACK_ENV)
    )
    resolved = _resolve_executable(configured)
    if resolved:
        return resolved

    for path in SYSTEM_CHROMIUM_PATHS:
        resolved = _resolve_executable(path)
        if resolved:
            return resolved
    for name in SYSTEM_CHROMIUM_CANDIDATES:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


def chromium_launch_options(headless: bool, args: list[str] | None = None) -> dict[str, Any]:
    launch_args = list(DEFAULT_CHROMIUM_ARGS)
    for arg in args or []:
        if arg not in launch_args:
            launch_args.append(arg)

    options: dict[str, Any] = {
        "headless": headless,
        "args": launch_args,
    }
    executable_path = chromium_executable_path()
    if executable_path:
        options["executable_path"] = executable_path
    return options
