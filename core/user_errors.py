from __future__ import annotations

import errno
from pathlib import Path

from drill_writer.core.project_io import ProjectLoadError, ProjectSaveError


def actionable_error_message(
    action: str,
    error: BaseException,
    *,
    location: Path | str | None = None,
) -> str:
    detail = str(error).strip() or error.__class__.__name__
    lowered = detail.lower()
    suggestions: list[str] = []

    error_number = getattr(error, "errno", None)
    windows_error = getattr(error, "winerror", None)
    if error_number == errno.ENOSPC or windows_error == 112 or "no space" in lowered or "disk full" in lowered:
        suggestions.extend(
            [
                "Free disk space on the project and export drives.",
                "Try the operation again; the previous project files were preserved.",
            ]
        )
    elif isinstance(error, PermissionError) or error_number in {errno.EACCES, errno.EPERM} or "permission" in lowered:
        suggestions.extend(
            [
                "Choose a folder you can write to and close any program using the file.",
                "Check Windows Security or controlled-folder-access settings if Documents is protected.",
            ]
        )
    elif isinstance(error, ProjectLoadError) or "corrupt" in lowered or "invalid json" in lowered:
        suggestions.extend(
            [
                "Use Restore Previous Save or open the recovery card on the Home screen.",
                "Export a bug report bundle before replacing project files.",
            ]
        )
    elif isinstance(error, ProjectSaveError):
        suggestions.extend(
            [
                "Check free disk space and write permission for the project folder.",
                "Use Restore Previous Save if the project does not reopen normally.",
            ]
        )
    elif "ffmpeg" in lowered or "encoder" in lowered:
        suggestions.extend(
            [
                "Open File > Export > Set ffmpeg.exe and choose the executable inside the FFmpeg bin folder.",
                "Use the Auto encoder option or install a full FFmpeg build if an encoder is unavailable.",
            ]
        )
    elif isinstance(error, FileNotFoundError) or "not found" in lowered:
        suggestions.append("Confirm the source file still exists, then choose it again.")
    else:
        suggestions.append("Try the operation again after saving and reopening the project.")

    suggestions.append("If the problem continues, use Help > Export Bug Report Bundle and include the affected project.")
    lines = [f"Drill Pirate could not {action}.", "", f"What happened: {detail}"]
    if location:
        lines.extend(["", f"Location: {location}"])
    lines.extend(["", "What you can do:"])
    lines.extend(f"• {suggestion}" for suggestion in dict.fromkeys(suggestions))
    return "\n".join(lines)
