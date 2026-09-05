# -*- coding: utf-8 -*-
"""Automatic plugin loader.

Put a Python plugin in the plugins/ folder. If it exposes setup(app)
or register(app), it is loaded automatically; no edit to bot22.py is needed.
"""
from __future__ import annotations

import importlib
import logging
from pathlib import Path
from types import ModuleType

logger = logging.getLogger(__name__)


def _plugin_files() -> list[Path]:
    folder = Path(__file__).resolve().parent
    return sorted(p for p in folder.glob("*.py") if p.name != "__init__.py" and not p.name.startswith("_"))


def load_plugins(app) -> list[str]:
    loaded: list[str] = []
    package = __package__ or "plugins"
    for path in _plugin_files():
        module_name = f"{package}.{path.stem}"
        try:
            module: ModuleType = importlib.import_module(module_name)
            register = getattr(module, "setup", None) or getattr(module, "register", None)
            if not callable(register):
                logger.info("Plugin skipped (no setup/app or register/app): %s", path.name)
                continue
            register(app)
            loaded.append(path.stem)
            logger.info("PLUGIN LOADED: %s", path.name)
        except Exception:
            logger.exception("PLUGIN FAILED: %s", path.name)
    logger.info("Plugins loaded: %s", ", ".join(loaded) if loaded else "none")
    return loaded
