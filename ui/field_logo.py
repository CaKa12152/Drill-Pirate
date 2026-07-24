from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRectF, QSettings, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap

from drill_writer.core.diagnostics import app_data_dir
from drill_writer.core.models import SurfaceDefinition
from drill_writer.core.specialized_design import normalized_surface
from drill_writer.resources import field_logo_path
from drill_writer.ui.theme import normalize_field_mode


FIELD_LOGO_SETTING = "appearance/show_field_logo"
FIELD_LOGO_CUSTOM_PATH_SETTING = "appearance/field_logo_custom_path"
FIELD_LOGO_OPACITY_SETTING = "appearance/field_logo_opacity"
FIELD_LOGO_SCALE_SETTING = "appearance/field_logo_scale"
DEFAULT_FIELD_LOGO_OPACITY = 1.0
DEFAULT_FIELD_LOGO_SCALE = 1.0


def field_logo_enabled(settings: QSettings | None = None) -> bool:
    source = settings or QSettings("OpenAI", "DrillWriter")
    return source.value(FIELD_LOGO_SETTING, True, type=bool)


def custom_field_logo_path(settings: QSettings | None = None) -> Path | None:
    source = settings or QSettings("OpenAI", "DrillWriter")
    value = str(source.value(FIELD_LOGO_CUSTOM_PATH_SETTING, "") or "").strip()
    if not value:
        return None
    candidate = Path(value).expanduser()
    return candidate if candidate.is_file() else None


def active_field_logo_path(settings: QSettings | None = None) -> Path:
    return custom_field_logo_path(settings) or field_logo_path()


def field_logo_user_opacity(settings: QSettings | None = None) -> float:
    source = settings or QSettings("OpenAI", "DrillWriter")
    try:
        value = float(source.value(FIELD_LOGO_OPACITY_SETTING, DEFAULT_FIELD_LOGO_OPACITY))
    except (TypeError, ValueError):
        value = DEFAULT_FIELD_LOGO_OPACITY
    return max(0.05, min(1.0, value))


def field_logo_user_scale(settings: QSettings | None = None) -> float:
    source = settings or QSettings("OpenAI", "DrillWriter")
    try:
        value = float(source.value(FIELD_LOGO_SCALE_SETTING, DEFAULT_FIELD_LOGO_SCALE))
    except (TypeError, ValueError):
        value = DEFAULT_FIELD_LOGO_SCALE
    return max(0.25, min(2.5, value))


def custom_field_logo_storage_path() -> Path:
    directory = app_data_dir() / "assets"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "custom_field_logo.png"


def install_custom_field_logo(
    source_path: str | Path,
    settings: QSettings | None = None,
    *,
    destination: Path | None = None,
) -> Path:
    source = Path(source_path).expanduser()
    image = QImage(str(source))
    if image.isNull():
        raise ValueError("The selected file is not a supported or readable image.")
    target = destination or custom_field_logo_storage_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.stem}.tmp{target.suffix}")
    if not image.save(str(temporary), "PNG"):
        raise OSError(f"Could not save the field logo to {target}.")
    temporary.replace(target)
    preferences = settings or QSettings("OpenAI", "DrillWriter")
    preferences.setValue(FIELD_LOGO_CUSTOM_PATH_SETTING, str(target))
    preferences.sync()
    clear_field_logo_cache()
    return target


def clear_custom_field_logo(settings: QSettings | None = None, *, delete_file: bool = True) -> None:
    preferences = settings or QSettings("OpenAI", "DrillWriter")
    existing = custom_field_logo_path(preferences)
    preferences.remove(FIELD_LOGO_CUSTOM_PATH_SETTING)
    preferences.sync()
    if delete_file and existing is not None and existing == custom_field_logo_storage_path():
        existing.unlink(missing_ok=True)
    clear_field_logo_cache()


def set_field_logo_appearance(
    opacity: float,
    scale: float,
    settings: QSettings | None = None,
) -> None:
    preferences = settings or QSettings("OpenAI", "DrillWriter")
    preferences.setValue(FIELD_LOGO_OPACITY_SETTING, max(0.05, min(1.0, float(opacity))))
    preferences.setValue(FIELD_LOGO_SCALE_SETTING, max(0.25, min(2.5, float(scale))))
    preferences.sync()


@lru_cache(maxsize=12)
def _themed_field_logo_pixmap(field_mode: str, source_path: str, modified_ns: int) -> QPixmap:
    mode = normalize_field_mode(field_mode)
    source = QImage(source_path).convertToFormat(QImage.Format.Format_RGBA8888)
    if source.isNull():
        return QPixmap()
    if mode == "grass":
        return QPixmap.fromImage(source)

    pixels = bytearray(source.constBits())
    stride = source.bytesPerLine()
    inverted = mode == "inverted"
    for y_position in range(source.height()):
        row_start = y_position * stride
        for x_position in range(source.width()):
            offset = row_start + x_position * 4
            red, green, blue, alpha = pixels[offset : offset + 4]
            if alpha == 0:
                continue
            monochrome = (54 * red + 183 * green + 19 * blue) // 256
            if inverted:
                monochrome = 255 - monochrome
            pixels[offset] = monochrome
            pixels[offset + 1] = monochrome
            pixels[offset + 2] = monochrome

    themed = QImage(
        pixels,
        source.width(),
        source.height(),
        stride,
        QImage.Format.Format_RGBA8888,
    ).copy()
    return QPixmap.fromImage(themed)


def clear_field_logo_cache() -> None:
    _themed_field_logo_pixmap.cache_clear()


def field_logo_pixmap(field_mode: str = "grass", settings: QSettings | None = None) -> QPixmap:
    source = active_field_logo_path(settings)
    try:
        modified_ns = source.stat().st_mtime_ns
    except OSError:
        modified_ns = 0
    return _themed_field_logo_pixmap(normalize_field_mode(field_mode), str(source), modified_ns)


def field_logo_opacity(field_mode: str, settings: QSettings | None = None) -> float:
    normalize_field_mode(field_mode)
    return field_logo_user_opacity(settings)


def field_logo_dimensions_yards(
    surface: SurfaceDefinition,
    pixmap: QPixmap | None = None,
    settings: QSettings | None = None,
) -> tuple[float, float]:
    normalized = normalized_surface(surface)
    image = pixmap or field_logo_pixmap("grass")
    if image.isNull():
        return (0.0, 0.0)
    user_scale = field_logo_user_scale(settings)
    maximum_width = min(22.0, normalized.width_yards * 0.20) * user_scale
    maximum_height = min(18.0, normalized.height_yards * 0.42) * user_scale
    scale = min(maximum_width / image.width(), maximum_height / image.height())
    return image.width() * scale, image.height() * scale


def draw_field_logo(
    painter: QPainter,
    rect: QRectF,
    surface: SurfaceDefinition,
    field_mode: str,
    *,
    visible: bool | None = None,
) -> None:
    if visible is None:
        visible = field_logo_enabled()
    normalized = normalized_surface(surface)
    if not visible or normalized.surface_type == "parade":
        return
    pixmap = field_logo_pixmap(field_mode)
    if pixmap.isNull():
        return
    width_yards, height_yards = field_logo_dimensions_yards(normalized, pixmap)
    target_width = width_yards / normalized.width_yards * rect.width()
    target_height = height_yards / normalized.height_yards * rect.height()
    target = QRectF(
        rect.center().x() - target_width / 2,
        rect.center().y() - target_height / 2,
        target_width,
        target_height,
    )
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.setOpacity(field_logo_opacity(field_mode))
    painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
    painter.restore()
