from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
import csv
from queue import Empty, Queue
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QMarginsF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen

from drill_writer.core.analysis import detect_path_warnings
from drill_writer.core.animation import interpolate_project, interpolate_props
from drill_writer.core.coordinates import format_drill_coordinate
from drill_writer.core.models import DrillProject
from drill_writer.core.project_io import BACKUP_DIR_NAME, save_project
from drill_writer.ui.field_view import FieldView


ProgressCallback = Callable[[str, int, int], None]
CancelCallback = Callable[[], bool]


class ExportCancelled(RuntimeError):
    pass


INK = QColor("#17202a")
MUTED = QColor("#596575")
BLUE = QColor("#2458d3")
BLUE_DARK = QColor("#183f9a")
GOLD = QColor("#d8a928")
LINE = QColor("#d8dee8")
SOFT = QColor("#f5f7fb")
TABLE_HEADER = QColor("#edf2fb")
EXPORT_FONT_FAMILY = "Arial"
EXPORT_FONT_INITIALIZED = False


def ensure_export_font() -> str:
    global EXPORT_FONT_FAMILY, EXPORT_FONT_INITIALIZED
    if EXPORT_FONT_INITIALIZED:
        return EXPORT_FONT_FAMILY
    for font_path in (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
    ):
        if not font_path.exists():
            continue
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        if families:
            EXPORT_FONT_FAMILY = families[0]
            break
    EXPORT_FONT_INITIALIZED = True
    return EXPORT_FONT_FAMILY


def export_project_zip(project_dir: Path, output_path: Path, project: DrillProject) -> None:
    save_project(project_dir, project, backup_reason="project_zip")
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in project_dir.rglob("*"):
            if BACKUP_DIR_NAME in path.relative_to(project_dir).parts:
                continue
            if path.is_file():
                archive.write(path, path.relative_to(project_dir))


def clean_text(value: object) -> str:
    return (
        str(value)
        .replace("â€”", "-")
        .replace("â€“", "-")
        .replace("—", "-")
        .replace("–", "-")
        .replace("Â·", "-")
        .replace("·", "-")
    )


def set_font(painter: QPainter, size: int, bold: bool = False) -> None:
    painter.setFont(QFont(ensure_export_font(), size, QFont.Weight.Bold if bold else QFont.Weight.Normal))


def draw_header(
    painter: QPainter,
    page_rect: QRectF,
    title: str,
    subtitle: str = "",
    eyebrow: str = "Drill Pirate",
) -> QRectF:
    painter.fillRect(page_rect, QColor("#ffffff"))
    accent_rect = QRectF(page_rect.left(), page_rect.top(), 8, 78)
    painter.fillRect(accent_rect, BLUE)

    painter.setPen(GOLD)
    set_font(painter, 9, True)
    painter.drawText(
        page_rect.adjusted(24, 0, 0, -page_rect.height() + 20),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        clean_text(eyebrow).upper(),
    )

    painter.setPen(INK)
    set_font(painter, 20, True)
    painter.drawText(
        page_rect.adjusted(24, 24, 0, -page_rect.height() + 58),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        clean_text(title),
    )

    if subtitle:
        painter.setPen(MUTED)
        set_font(painter, 9)
        painter.drawText(
            page_rect.adjusted(24, 58, 0, -page_rect.height() + 82),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            clean_text(subtitle),
        )
    return page_rect.adjusted(24, 92, -24, -32)


def draw_footer(painter: QPainter, page_rect: QRectF, text: str) -> None:
    painter.setPen(MUTED)
    set_font(painter, 8)
    painter.drawText(
        page_rect.adjusted(24, page_rect.height() - 24, -24, 0),
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        clean_text(text),
    )


def draw_chip(painter: QPainter, rect: QRectF, label: str, value: str) -> None:
    painter.setPen(QPen(QColor("#d0d8e4"), 1))
    painter.setBrush(SOFT)
    painter.drawRoundedRect(rect, 7, 7)
    painter.setPen(MUTED)
    set_font(painter, 7, True)
    painter.drawText(rect.adjusted(10, 5, -10, -rect.height() / 2), Qt.AlignmentFlag.AlignLeft, clean_text(label).upper())
    painter.setPen(INK)
    set_font(painter, 12, True)
    painter.drawText(rect.adjusted(10, rect.height() / 2 - 3, -10, -4), Qt.AlignmentFlag.AlignLeft, clean_text(value))


def draw_chips(
    painter: QPainter,
    left: float,
    top: float,
    width: float,
    chips: list[tuple[str, str]],
) -> float:
    if not chips:
        return top
    gap = 10
    chip_width = (width - gap * (len(chips) - 1)) / len(chips)
    for index, (label, value) in enumerate(chips):
        rect = QRectF(left + index * (chip_width + gap), top, chip_width, 48)
        draw_chip(painter, rect, label, value)
    return top + 60


def draw_field_panel(
    painter: QPainter,
    field_view: FieldView,
    panel_rect: QRectF,
    scene_source: QRectF,
    caption: str = "",
) -> None:
    field_rect = panel_rect.adjusted(10, 10, -10, -28 if caption else -10)
    field_aspect = 120 / 53.333
    target_width = field_rect.width()
    target_height = target_width / field_aspect
    if target_height > field_rect.height():
        target_height = field_rect.height()
        target_width = target_height * field_aspect
    render_rect = QRectF(
        field_rect.left() + (field_rect.width() - target_width) / 2,
        field_rect.top(),
        target_width,
        target_height,
    )
    visible_panel = QRectF(
        render_rect.left() - 10,
        render_rect.top() - 10,
        render_rect.width() + 20,
        render_rect.height() + (38 if caption else 20),
    ).intersected(panel_rect)
    painter.setPen(QPen(LINE, 1.2))
    painter.setBrush(QColor("#fbfcff"))
    painter.drawRoundedRect(visible_panel, 10, 10)
    field_view.scene.render(painter, render_rect, scene_source, Qt.AspectRatioMode.KeepAspectRatio)
    if caption:
        painter.setPen(MUTED)
        set_font(painter, 8)
        painter.drawText(
            QRectF(visible_panel.left() + 14, visible_panel.bottom() - 22, visible_panel.width() - 28, 18),
            Qt.AlignmentFlag.AlignCenter,
            clean_text(caption),
        )


def draw_clean_table(
    painter: QPainter,
    rect: QRectF,
    headers: list[str],
    rows: list[list[str]],
    column_widths: list[float],
    row_height: float = 28,
) -> float:
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(TABLE_HEADER)
    painter.drawRoundedRect(QRectF(rect.left(), rect.top(), rect.width(), row_height), 7, 7)
    x = rect.left()
    set_font(painter, 8, True)
    painter.setPen(INK)
    for header, width in zip(headers, column_widths):
        painter.drawText(
            QRectF(x + 8, rect.top(), width - 12, row_height),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            clean_text(header).upper(),
        )
        x += width

    y = rect.top() + row_height
    set_font(painter, 9)
    for row_index, row in enumerate(rows):
        if y + row_height > rect.bottom():
            break
        if row_index % 2 == 0:
            painter.fillRect(QRectF(rect.left(), y, rect.width(), row_height), QColor("#fbfcff"))
        painter.setPen(QPen(LINE, 0.8))
        painter.drawLine(rect.left(), y + row_height, rect.right(), y + row_height)
        x = rect.left()
        painter.setPen(INK)
        for value, width in zip(row, column_widths):
            text = painter.fontMetrics().elidedText(clean_text(value), Qt.TextElideMode.ElideRight, int(width - 12))
            painter.drawText(
                QRectF(x + 8, y, width - 12, row_height),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                text,
            )
            x += width
        y += row_height
    return y


def movement_style_export_label(style: object) -> str:
    if not style:
        return "Normal"
    value = getattr(style, "value", style)
    labels = {
        "normal": "Normal",
        "half_time": "Half Time",
        "double_time": "Double Time",
        "jazz_run": "Jazz Run",
        "halt": "Halt",
        "visual": "Visual",
    }
    return labels.get(str(value), str(value).replace("_", " ").title())


def field_scene_source(field_view: FieldView) -> QRectF:
    return QRectF(
        -60 * field_view.scale_factor,
        -26.6665 * field_view.scale_factor,
        120 * field_view.scale_factor,
        53.333 * field_view.scale_factor,
    )


def draw_raster_pdf_page(
    writer: QPdfWriter,
    pdf_painter: QPainter,
    draw_callback: Callable[[QPainter, QRectF], None],
) -> None:
    page_pixels = writer.pageLayout().paintRectPixels(writer.resolution())
    image = QImage(
        max(1, int(page_pixels.width())),
        max(1, int(page_pixels.height())),
        QImage.Format.Format_ARGB32,
    )
    image.fill(QColor("#ffffff"))
    image_painter = QPainter(image)
    image_painter.setRenderHints(
        QPainter.RenderHint.Antialiasing
        | QPainter.RenderHint.TextAntialiasing
        | QPainter.RenderHint.SmoothPixmapTransform
    )
    try:
        draw_callback(image_painter, QRectF(0, 0, image.width(), image.height()))
    finally:
        image_painter.end()
    pdf_painter.drawImage(QRectF(0, 0, image.width(), image.height()), image)


def export_drill_sheet_pdf(
    output_path: Path,
    project: DrillProject,
    project_dir: Path | None = None,
    progress_callback: ProgressCallback | None = None,
) -> None:
    ensure_export_font()
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
    sheet_field.set_project(project, project_dir)
    sheet_field.update_labels(False)
    scene_source = field_scene_source(sheet_field)

    pdf_painter = QPainter(writer)
    try:
        total = max(1, len(project.sets))
        for index, drill_set in enumerate(project.sets):
            if index:
                writer.newPage()
            if progress_callback:
                progress_callback("Creating drill sheet PDF", index + 1, total)

            sheet_field.set_positions(drill_set.dot_positions)
            sheet_field.set_prop_states(drill_set.prop_positions)

            def draw_page(painter: QPainter, page_rect: QRectF) -> None:
                content_rect = draw_header(
                    painter,
                    page_rect,
                    f"{project.metadata.show_title} - {drill_set.name}",
                    "Set chart for rehearsal and coordinate reference",
                )
                chips_bottom = draw_chips(
                    painter,
                    content_rect.left(),
                    content_rect.top(),
                    content_rect.width(),
                    [
                        ("Counts", f"{drill_set.start_count}-{drill_set.end_count}"),
                        ("Length", f"{drill_set.duration_counts} counts"),
                        ("Tempo", f"{project.active_tempo(index):g} BPM"),
                        ("Performers", str(len(project.dots))),
                    ],
                )
                field_panel = QRectF(
                    content_rect.left(),
                    chips_bottom,
                    content_rect.width(),
                    content_rect.bottom() - chips_bottom - 4,
                )
                draw_field_panel(
                    painter,
                    sheet_field,
                    field_panel,
                    scene_source,
                    "Field overview",
                )
                draw_footer(painter, page_rect, f"Set {index + 1} of {total}")

            draw_raster_pdf_page(writer, pdf_painter, draw_page)
    finally:
        pdf_painter.end()

def export_dot_book_pdf(
    output_path: Path,
    project: DrillProject,
    progress_callback: ProgressCallback | None = None,
) -> None:
    ensure_export_font()
    writer = QPdfWriter(str(output_path))
    writer.setResolution(150)
    writer.setPageLayout(
        QPageLayout(
            QPageSize(QPageSize.PageSizeId.Letter),
            QPageLayout.Orientation.Portrait,
            QMarginsF(0.45, 0.45, 0.45, 0.45),
            QPageLayout.Unit.Inch,
        )
    )
    pdf_painter = QPainter(writer)
    try:
        total = max(1, len(project.dots))
        for dot_index, dot in enumerate(project.dots):
            if dot_index:
                writer.newPage()
            if progress_callback:
                progress_callback("Creating dot book PDF", dot_index + 1, total)

            rows: list[list[str]] = []
            for set_index, drill_set in enumerate(project.sets):
                x, y = drill_set.dot_positions.get(dot.id, (dot.x, dot.y))
                yard_text, hash_text = format_drill_coordinate(x, y)
                rows.append(
                    [
                        drill_set.name,
                        f"{drill_set.start_count}-{drill_set.end_count}",
                        yard_text,
                        hash_text,
                        movement_style_export_label(drill_set.movement_styles.get(dot.id)),
                        f"{project.active_tempo(set_index):g} BPM",
                    ]
                )

            def draw_page(painter: QPainter, page_rect: QRectF) -> None:
                content_rect = draw_header(
                    painter,
                    page_rect,
                    f"{dot.name} - Dot Book",
                    project.metadata.show_title,
                )
                chip_values = [
                    ("Drill #", dot.id),
                    ("Section", dot.section or "Unassigned"),
                    ("Instrument", dot.instrument or "-"),
                ]
                chips_bottom = draw_chips(
                    painter,
                    content_rect.left(),
                    content_rect.top(),
                    content_rect.width(),
                    chip_values,
                )
                table_rect = QRectF(
                    content_rect.left(),
                    chips_bottom + 6,
                    content_rect.width(),
                    content_rect.bottom() - chips_bottom - 18,
                )
                headers = ["Set", "Counts", "Yard Line", "Hash / Side", "Move", "Tempo"]
                table_width = table_rect.width()
                widths = [
                    table_width * 0.16,
                    table_width * 0.10,
                    table_width * 0.25,
                    table_width * 0.25,
                    table_width * 0.12,
                    table_width * 0.12,
                ]
                draw_clean_table(painter, table_rect, headers, rows, widths, row_height=30)
                draw_footer(painter, page_rect, f"Performer {dot_index + 1} of {total}")

            draw_raster_pdf_page(writer, pdf_painter, draw_page)
    finally:
        pdf_painter.end()

def export_staff_packet_pdf(
    output_path: Path,
    project: DrillProject,
    project_dir: Path | None = None,
    progress_callback: ProgressCallback | None = None,
) -> None:
    ensure_export_font()
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
    pdf_painter = QPainter(writer)
    try:
        overview_rows = [
            [
                drill_set.name,
                f"{drill_set.start_count}-{drill_set.end_count}",
                f"{drill_set.duration_counts}",
                f"{project.active_tempo(index):g} BPM",
            ]
            for index, drill_set in enumerate(project.sets)
        ]

        def draw_overview_page(painter: QPainter, page_rect: QRectF) -> None:
            content_rect = draw_header(painter, page_rect, project.metadata.show_title, "Staff rehearsal packet")
            draw_chips(
                painter,
                content_rect.left(),
                content_rect.top(),
                content_rect.width(),
                [
                    ("Sets", str(len(project.sets))),
                    ("Performers", str(len(project.dots))),
                    ("Base Tempo", f"{project.metadata.initial_tempo:g} BPM"),
                    ("Time Signature", project.metadata.time_signature),
                ],
            )
            painter.setPen(INK)
            set_font(painter, 18, True)
            painter.drawText(
                QRectF(content_rect.left(), content_rect.top() + 92, content_rect.width(), 34),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "Set Overview",
            )
            overview_rect = QRectF(
                content_rect.left(),
                content_rect.top() + 136,
                content_rect.width(),
                content_rect.height() - 150,
            )
            overview_width = overview_rect.width()
            draw_clean_table(
                painter,
                overview_rect,
                ["Set", "Counts", "Length", "Tempo"],
                overview_rows,
                [
                    overview_width * 0.46,
                    overview_width * 0.18,
                    overview_width * 0.14,
                    overview_width * 0.22,
                ],
                row_height=30,
            )
            draw_footer(painter, page_rect, "Overview")

        draw_raster_pdf_page(writer, pdf_painter, draw_overview_page)

        warnings = []
        for set_index in range(len(project.sets)):
            warnings.extend(detect_path_warnings(project, set_index, warning_limit=60))
        if warnings:
            writer.newPage()
            rows = [
                [
                    warning.set_name,
                    f"{warning.count:.1f}",
                    clean_text(warning.message),
                ]
                for warning in warnings[:38]
            ]

            def draw_warnings_page(painter: QPainter, page_rect: QRectF) -> None:
                content_rect = draw_header(
                    painter,
                    page_rect,
                    project.metadata.show_title,
                    "Spacing notes for staff review",
                )
                warning_rect = QRectF(
                    content_rect.left(),
                    content_rect.top(),
                    content_rect.width(),
                    content_rect.height() - 8,
                )
                warning_width = warning_rect.width()
                draw_clean_table(
                    painter,
                    warning_rect,
                    ["Set", "Count", "Note"],
                    rows,
                    [warning_width * 0.18, warning_width * 0.10, warning_width * 0.72],
                    row_height=28,
                )
                draw_footer(painter, page_rect, "Spacing review")

            draw_raster_pdf_page(writer, pdf_painter, draw_warnings_page)

        sheet_field = FieldView()
        sheet_field.set_project(project, project_dir)
        sheet_field.update_labels(False)
        scene_source = field_scene_source(sheet_field)
        total = max(1, len(project.sets))
        for index, drill_set in enumerate(project.sets):
            if progress_callback:
                progress_callback("Creating staff packet", index + 1, total)
            writer.newPage()
            sheet_field.set_positions(drill_set.dot_positions)
            sheet_field.set_prop_states(drill_set.prop_positions)

            def draw_set_page(painter: QPainter, page_rect: QRectF) -> None:
                content_rect = draw_header(
                    painter,
                    page_rect,
                    f"{drill_set.name}",
                    f"{project.metadata.show_title} - counts {drill_set.start_count}-{drill_set.end_count} - {project.active_tempo(index):g} BPM",
                )
                field_panel = QRectF(
                    content_rect.left(),
                    content_rect.top(),
                    content_rect.width(),
                    content_rect.height() - 4,
                )
                draw_field_panel(painter, sheet_field, field_panel, scene_source)
                draw_footer(painter, page_rect, f"Set {index + 1} of {total}")

            draw_raster_pdf_page(writer, pdf_painter, draw_set_page)
    finally:
        pdf_painter.end()

def export_coordinate_csv(output_path: Path, project: DrillProject) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "dot_id",
                "name",
                "section",
                "instrument",
                "rank",
                "equipment",
                "layer",
                "set",
                "start_count",
                "end_count",
                "tempo",
                "x",
                "y",
                "yard_line_coordinate",
                "hash_coordinate",
                "movement_style",
                "transition",
            ]
        )
        for dot in project.dots:
            for set_index, drill_set in enumerate(project.sets):
                x, y = drill_set.dot_positions.get(dot.id, (dot.x, dot.y))
                yard_text, hash_text = format_drill_coordinate(x, y)
                writer.writerow(
                    [
                        dot.id,
                        dot.name,
                        dot.section,
                        dot.instrument,
                        dot.rank,
                        dot.equipment,
                        dot.layer,
                        drill_set.name,
                        drill_set.start_count,
                        drill_set.end_count,
                        project.active_tempo(set_index),
                        f"{x:.3f}",
                        f"{y:.3f}",
                        yard_text,
                        hash_text,
                        movement_style_export_label(drill_set.movement_styles.get(dot.id)),
                        drill_set.transition.value,
                    ]
                )


def draw_table_row(
    painter: QPainter,
    left: float,
    top: float,
    height: float,
    widths: list[int],
    values: list[str],
    bold: bool = False,
) -> None:
    painter.setFont(QFont(ensure_export_font(), 9, QFont.Weight.Bold if bold else QFont.Weight.Normal))
    x = left
    for width, value in zip(widths, values):
        rect = QRectF(x, top, width, height)
        painter.setPen(QColor("#c7ccd6"))
        painter.drawRect(rect)
        painter.setPen(QColor("#111318"))
        painter.drawText(rect.adjusted(6, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, value)
        x += width


def read_process_output(stream, output_queue: Queue[str]) -> None:
    try:
        for line in iter(stream.readline, ""):
            output_queue.put(line.strip())
    finally:
        stream.close()


def drain_ffmpeg_progress(
    output_queue: Queue[str],
    output_lines: list[str],
    fps: int,
    total_frames: int,
    render_steps: int,
    encode_steps: int,
    last_progress: int,
) -> int:
    current = last_progress
    while True:
        try:
            line = output_queue.get_nowait()
        except Empty:
            return current
        if not line:
            continue
        output_lines.append(line)
        parsed = ffmpeg_progress_from_line(line, fps, total_frames, render_steps, encode_steps)
        if parsed is not None:
            current = max(current, parsed)


def ffmpeg_progress_from_line(
    line: str,
    fps: int,
    total_frames: int,
    render_steps: int,
    encode_steps: int,
) -> int | None:
    key, separator, value = line.partition("=")
    if not separator:
        return None
    key = key.strip()
    value = value.strip()
    if key == "progress" and value == "end":
        return render_steps + encode_steps
    if key == "frame":
        try:
            encoded_frames = max(0, int(value))
        except ValueError:
            return None
        ratio = min(1.0, encoded_frames / max(1, total_frames))
        return min(render_steps + int(ratio * encode_steps), render_steps + encode_steps - 20)
    if key in {"out_time_ms", "out_time_us"}:
        try:
            encoded_seconds = max(0.0, int(value) / 1_000_000)
        except ValueError:
            return None
        ratio = min(1.0, encoded_seconds * fps / max(1, total_frames))
        return min(render_steps + int(ratio * encode_steps), render_steps + encode_steps - 20)
    if key == "out_time":
        seconds = seconds_from_ffmpeg_timestamp(value)
        if seconds is None:
            return None
        ratio = min(1.0, seconds * fps / max(1, total_frames))
        return min(render_steps + int(ratio * encode_steps), render_steps + encode_steps - 20)
    return None


def seconds_from_ffmpeg_timestamp(value: str) -> float | None:
    try:
        hours, minutes, seconds = value.split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except (ValueError, TypeError):
        return None


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
    progress_total = 1000
    render_steps = 720
    encode_steps = progress_total - render_steps

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
                field_view.set_prop_states(interpolate_props(project, set_index, count))
                image = QImage(size, QImage.Format.Format_ARGB32)
                image.fill(0xFF16181D)
                painter = QPainter(image)
                field_view.scene.render(painter)
                painter.end()
                image.save(str(frames_dir / f"frame_{frame_index:06d}.png"))
                frame_index += 1
                render_progress = int((frame_index / max(1, total_frames)) * render_steps)
                report("Rendering MP4 frames", render_progress, progress_total)

        command = [
            ffmpeg,
            "-y",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostats",
            "-framerate",
            str(fps),
            "-i",
            str(frames_dir / "frame_%06d.png"),
        ]
        if audio_path and audio_path.exists():
            command += ["-i", str(audio_path), "-shortest"]
        command += ["-pix_fmt", "yuv420p", "-movflags", "+faststart", "-progress", "pipe:1", str(output_path)]
        report("Encoding MP4 with ffmpeg", render_steps, progress_total)
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        output_queue: Queue[str] = Queue()
        output_lines: list[str] = []
        reader_thread: threading.Thread | None = None
        if process.stdout is not None:
            reader_thread = threading.Thread(
                target=read_process_output,
                args=(process.stdout, output_queue),
                daemon=True,
            )
            reader_thread.start()

        last_encode_progress = render_steps
        while process.poll() is None:
            check_cancelled(process)
            last_encode_progress = drain_ffmpeg_progress(
                output_queue,
                output_lines,
                fps,
                total_frames,
                render_steps,
                encode_steps,
                last_encode_progress,
            )
            stage = "Finalizing MP4 file" if last_encode_progress >= progress_total - 20 else "Encoding MP4 with ffmpeg"
            report(stage, last_encode_progress, progress_total)
            time.sleep(0.1)
        process.wait()
        if reader_thread:
            reader_thread.join(timeout=1.0)
        last_encode_progress = drain_ffmpeg_progress(
            output_queue,
            output_lines,
            fps,
            total_frames,
            render_steps,
            encode_steps,
            last_encode_progress,
        )
        if process.returncode != 0:
            message = "\n".join(output_lines[-20:])
            raise RuntimeError(message.strip() or "ffmpeg failed.")
        report("MP4 export complete", progress_total, progress_total)
