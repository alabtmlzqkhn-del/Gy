# -*- coding: utf-8 -*-
"""Central JSON data storage for the bot.

Persistent storage is data.json.  No SQL/Redis is used by this module.
All modules should use this module instead of creating their own storage file.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data.json"
BACKUP_FILE = BASE_DIR / "data.json.bak"
_LOCK = threading.RLock()


def _empty() -> dict[str, Any]:
    return {
        "version": 1,
        "users": {},
        "groups": {},
        "ranks": {},
        "locks": {},
        "tags": {},
        "restrictions": {},
        "settings": {},
        "replies": {},
        "games": {},
        "books": {},
        "bot_settings": {},
        "cache": {},
    }


def load_data() -> dict[str, Any]:
    """Read the complete JSON store. Creates it when missing/corrupt."""
    with _LOCK:
        if not DATA_FILE.exists():
            data = _empty()
            _write_unlocked(data)
            return data
        try:
            with DATA_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("data.json must contain an object")
            return data
        except Exception:
            # Keep the damaged file for recovery, then start clean.
            try:
                broken = DATA_FILE.with_suffix(".json.broken")
                os.replace(DATA_FILE, broken)
            except Exception:
                pass
            data = _empty()
            _write_unlocked(data)
            return data


def _write_unlocked(data: dict[str, Any]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    if DATA_FILE.exists():
        try:
            shutil.copy2(DATA_FILE, BACKUP_FILE)
        except Exception:
            pass
    os.replace(tmp, DATA_FILE)


def save_data(data: dict[str, Any]) -> None:
    """Atomically save the complete data dictionary."""
    if not isinstance(data, dict):
        raise TypeError("data must be a dict")
    with _LOCK:
        _write_unlocked(data)


def get_data() -> dict[str, Any]:
    return load_data()


def get(key: str, default: Any = None) -> Any:
    with _LOCK:
        return load_data().get(key, default)


def set_value(key: str, value: Any) -> None:
    with _LOCK:
        data = load_data()
        data[key] = value
        save_data(data)


def update(values: dict[str, Any]) -> None:
    with _LOCK:
        data = load_data()
        data.update(values)
        save_data(data)


def delete(key: str) -> None:
    with _LOCK:
        data = load_data()
        data.pop(key, None)
        save_data(data)


def get_group(chat_id: int) -> dict[str, Any]:
    with _LOCK:
        data = load_data()
        groups = data.setdefault("groups", {})
        return groups.setdefault(str(chat_id), {})


def save_group(chat_id: int, group_data: dict[str, Any]) -> None:
    with _LOCK:
        data = load_data()
        data.setdefault("groups", {})[str(chat_id)] = group_data
        save_data(data)


# Loaded once for modules that want a shared in-memory snapshot.  For writes,
# use save_data/load_data so the JSON file is updated immediately.
DATA = load_data()
