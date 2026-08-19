"""設定の保存 / 読み込み (%APPDATA%\\ProcCpuMonitor\\config.json)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "ProcCpuMonitor"

DEFAULT_PROCESSES = ["sldworks.exe", "EdmServerV6.exe", "ENOPLMCSAClient.exe"]

DEFAULTS = {
    "processes": DEFAULT_PROCESSES,
    "interval_ms": 1000,
    "window_seconds": 120,
    "normalize": False,
    "y_mode": "auto",
    "topmost": False,
}


def config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


def config_path() -> Path:
    return config_dir() / "config.json"


def load() -> dict:
    data = dict(DEFAULTS)
    try:
        with open(config_path(), "r", encoding="utf-8") as fp:
            loaded = json.load(fp)
        if isinstance(loaded, dict):
            for key in DEFAULTS:
                if key in loaded:
                    data[key] = loaded[key]
    except (OSError, ValueError):
        pass
    if not isinstance(data.get("processes"), list) or not data["processes"]:
        data["processes"] = list(DEFAULT_PROCESSES)
    data["processes"] = [str(p).strip() for p in data["processes"] if str(p).strip()]
    return data


def save(data: dict) -> None:
    try:
        config_dir().mkdir(parents=True, exist_ok=True)
        with open(config_path(), "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
    except OSError:
        pass
