# -*- coding: utf-8 -*-
import importlib
import logging
import os
import pkgutil
from pathlib import Path

# إضافة مكتبة static-ffmpeg لتثبيت وربط FFmpeg تلقائياً
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

HELPERS_DIR = Path(__file__).resolve().parent / "helpers"

def load_helper_modules():
    """Load helper modules that expose setup(app)."""
    modules = []
    for info in pkgutil.iter_modules([str(HELPERS_DIR)]):
        name = info.name
        if name.startswith("_") or name == "bot22":
            continue
        modules.append(name)
    return modules

def main():
    bot22 = importlib.import_module("helpers.bot22")

    # Prefer the original bot22 main() because the full source owns
    # its factory/worker lifecycle.
    # botvv is registered by bot22 when supported; otherwise we attach it
    # to an exposed application object.
    if hasattr(bot22, "main") and callable(bot22.main):
        bot22.main()
        return

    raise RuntimeError("helpers/bot22.py لا يحتوي على main().")

if __name__ == "__main__":
    main()
