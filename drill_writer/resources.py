from __future__ import annotations

import sys
from pathlib import Path


def resource_path(relative_path: str) -> Path:
    if getattr(sys, "frozen", False):
        base_path = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "drill_writer"
    else:
        base_path = Path(__file__).resolve().parent
    return base_path / relative_path


def app_icon_path() -> Path:
    return resource_path("assets/app_icon.png")


def app_icon_ico_path() -> Path:
    return resource_path("assets/app_icon.ico")
