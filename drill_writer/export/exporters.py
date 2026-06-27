from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QMarginsF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter

from drill_writer.core.animation import interpolate_project
from drill_writer.core.models import DrillProject
from drill_writer.core.project_io import save_project
from drill_writer.ui.field_view import FieldView


ProgressCallback = Callable[[str, int, int], None]
CancelCallback = Callable[[], bool]


class ExportCancelled(RuntimeError):
    pass


def export_project_zip(project_dir: Path, output_path: Path, project: DrillProject) -> None:
    save_project(project_dir, project)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in project_dir.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(project_dir))


def export_drill_sheet_pdf(
    output_path: Path,
    project: DrillProject,
    progress_callback: ProgressCallback | None = None,
) -> None:
    writer = QPdfWriter(str(output_path))
    writer.setResolution(150)
    writer.setPageLayout(
        QPageLayout(
            QPageSize(QPageSize.PageSizeId.Letter),
            QPageLayout.Orientation.Landscape,
            QMarginsF(0.35, 0.35, 0.35, 0.35),
            QPageLayout.Unit.Inch,
        )
    )

    sheet_field = FieldView()
    sheet_field.set_project(project)
    sheet_field.update_labels(True)
    scene_source = QRectF(
        -60 * sheet_field.scale_factor,
        -26.6665 * sheet_field.scale_factor,
        120 * sheet_field.scale_factor,
        53.333 * sheet_field.scale_factor,
    )

    painter = QPainter(writer)
    try:
        total = max(1, len(project.sets))
        for index, drill_set in enumerate(project.sets):
            if index:
                writer.newPage()
            if progress_callback:
                progress_callback("Rendering drill sheet PDF", index + 1, total)

            sheet_field.set_positions(drill_set.dot_positions)
            page_rect = QRectF(writer.pageLayout().paintRectPixels(writer.resolution()))
            painter.fillRect(page_rect, QColor("#ffffff"))

            title_font = QFont("Arial", 20, QFont.Weight.Bold)
            detail_font = QFont("Arial", 10)
            painter.setPen(QColor("#111318"))
            painter.setFont(title_font)
            painter.drawText(
                page_rect.adjusted(0, 0, 0, -page_rect.height() + 42),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{project.metadata.show_title} — {drill_set.name}",
            )

            tempo = project.active_tempo(index)
            count_text = (
                f"Counts: {drill_set.start_count}–{drill_set.end_count}  "
                f"({drill_set.duration_counts} total)"
            )
            details = (
                f"{count_text}     Tempo: {tempo:g} BPM     "
                f"Transition: {drill_set.transition.value}"
            )
            painter.setFont(detail_font)
            painter.drawText(
                page_rect.adjusted(0, 48, 0, -page_rect.height() + 78),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                details,
            )

            available = page_rect.adjusted(0, 104, 0, 0)
            field_aspect = 120 / 53.333
            field_width = available.width()
            field_height = field_width / field_aspect
            if field_height > available.height():
                field_height = available.height()
                field_width = field_height * field_aspect
            field_rect = QRectF(
                available.left() + (available.width() - field_width) / 2,
                available.top() + (available.height() - field_height) / 2,
                field_width,
                field_height,
            )
            sheet_field.scene.render(
                painter,
                field_rect,
                scene_source,
                Qt.AspectRatioMode.KeepAspectRatio,
            )
    finally:
        painter.end()


def export_mp4(
    field_view: FieldView,
    project_dir: Path,
    output_path: Path,
    project: DrillProject,
    ffmpeg_path: str | None = None,
    fps: int = 30,
    size: QSize = QSize(1920, 1080),
    progress_callback: ProgressCallback | None = None,
    cancel_callback: CancelCallback | None = None,
) -> None:
    ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg was not found on PATH.")

    def report(stage: str, current: int, total: int) -> None:
        if progress_callback:
            progress_callback(stage, current, total)

    def check_cancelled(process: subprocess.Popen | None = None) -> None:
        if cancel_callback and cancel_callback():
            if process and process.poll() is None:
                process.terminate()
            raise ExportCancelled("MP4 export cancelled.")

    audio_path = project_dir / project.metadata.audio_file if project.metadata.audio_file else None
    frame_counts = [
        max(1, int(drill_set.duration_counts * (60 / project.active_tempo(set_index)) * fps))
        for set_index, drill_set in enumerate(project.sets)
    ]
    total_frames = sum(frame_counts)
    progress_total = total_frames + 1

    with tempfile.TemporaryDirectory(prefix="drill_writer_frames_") as temp_dir:
        frames_dir = Path(temp_dir)
        frame_index = 0
        for set_index, drill_set in enumerate(project.sets):
            frame_count = frame_counts[set_index]
            for local_frame in range(frame_count):
                check_cancelled()
                progress = local_frame / max(1, frame_count - 1)
                count = drill_set.start_count + progress * (drill_set.end_count - drill_set.start_count)
                field_view.set_positions(interpolate_project(project, set_index, count))
                image = QImage(size, QImage.Format.Format_ARGB32)
                image.fill(0xFF16181D)
                painter = QPainter(image)
                field_view.scene.render(painter)
                painter.end()
                image.save(str(frames_dir / f"frame_{frame_index:06d}.png"))
                frame_index += 1
                report("Rendering MP4 frames", frame_index, progress_total)

        command = [
            ffmpeg,
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frames_dir / "frame_%06d.png"),
        ]
        if audio_path and audio_path.exists():
            command += ["-i", str(audio_path), "-shortest"]
        command += ["-pix_fmt", "yuv420p", str(output_path)]
        report("Encoding MP4 with ffmpeg", total_frames, progress_total)
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        while process.poll() is None:
            check_cancelled(process)
            report("Encoding MP4 with ffmpeg", total_frames, progress_total)
            time.sleep(0.1)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace") or stdout.decode("utf-8", errors="replace")
            raise RuntimeError(message.strip() or "ffmpeg failed.")
        report("MP4 export complete", progress_total, progress_total)
