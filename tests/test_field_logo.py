from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QRectF, QSettings, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from drill_writer.core.models import SurfaceDefinition
from drill_writer.resources import field_logo_path
from drill_writer.ui.field_logo import (
    DEFAULT_FIELD_LOGO_SCALE,
    FIELD_LOGO_SETTING,
    active_field_logo_path,
    custom_field_logo_path,
    field_logo_enabled,
    field_logo_dimensions_yards,
    field_logo_opacity,
    field_logo_pixmap,
    field_logo_user_opacity,
    field_logo_user_scale,
    install_custom_field_logo,
    set_field_logo_appearance,
)
from drill_writer.ui.field_view import FieldView
from drill_writer.ui.preferences import PreferencesDialog
from drill_writer.ui.surface_preview import draw_surface_preview


FIELD_PALETTES = {
    "white": {
        "fill": "#f9fbf7",
        "line": "#66717a",
        "micro": "#e3e9e8",
        "hash": "#1f2529",
        "endzone": "#edf3ef",
    },
    "inverted": {
        "fill": "#050607",
        "line": "#ffffff",
        "micro": "#303640",
        "hash": "#ffffff",
        "endzone": "#101216",
    },
    "grass": {
        "fill": "#2f7d3b",
        "line": "#ffffff",
        "micro": "#5aa766",
        "hash": "#ffffff",
        "endzone": "#276b33",
    },
}


def render_surface(mode: str, show_logo: bool) -> QImage:
    image = QImage(480, 220, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#22252b"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    draw_surface_preview(
        painter,
        QRectF(8, 8, 464, 204),
        SurfaceDefinition(),
        FIELD_PALETTES[mode],
        mode,
        show_logo,
    )
    painter.end()
    return image


def image_digest(image: QImage) -> str:
    bits = image.constBits()
    return hashlib.sha256(bytes(bits)).hexdigest()


class PreferenceReceiver(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.logo_visible: bool | None = None
        self.logo_appearance: tuple[str, bool, float, float] | None = None

    def apply_field_logo_visible(self, visible: bool) -> None:
        self.logo_visible = bool(visible)

    def apply_field_logo_appearance(
        self,
        source_path: str,
        use_default: bool,
        opacity: float,
        scale: float,
    ) -> None:
        self.logo_appearance = (source_path, use_default, opacity, scale)


class FieldLogoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_logo_asset_has_real_transparency(self) -> None:
        image = QImage(str(field_logo_path()))
        self.assertFalse(image.isNull())
        self.assertTrue(image.hasAlphaChannel())
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        self.assertGreater(image.pixelColor(image.width() // 2, image.height() // 3).alpha(), 0)

    def test_logo_renders_and_can_be_removed_in_every_field_mode(self) -> None:
        for mode in ("white", "inverted", "grass"):
            with self.subTest(mode=mode):
                shown = render_surface(mode, True)
                hidden = render_surface(mode, False)
                self.assertNotEqual(image_digest(shown), image_digest(hidden))
                self.assertGreater(field_logo_opacity(mode), 0.0)

    def test_logo_colors_are_theme_aware(self) -> None:
        grass = field_logo_pixmap("grass").toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        white = field_logo_pixmap("white").toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        inverted = field_logo_pixmap("inverted").toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        self.assertNotEqual(image_digest(grass), image_digest(white))
        self.assertNotEqual(image_digest(white), image_digest(inverted))

        colored_pixels = 0
        checked_pixels = 0
        grayscale_values: set[int] = set()
        for y_position in range(0, grass.height(), 9):
            for x_position in range(0, grass.width(), 9):
                grass_color = grass.pixelColor(x_position, y_position)
                if grass_color.alpha() < 200:
                    continue
                if max(grass_color.red(), grass_color.green(), grass_color.blue()) - min(
                    grass_color.red(), grass_color.green(), grass_color.blue()
                ) >= 35:
                    colored_pixels += 1
                white_color = white.pixelColor(x_position, y_position)
                inverted_color = inverted.pixelColor(x_position, y_position)
                self.assertEqual(white_color.red(), white_color.green())
                self.assertEqual(white_color.green(), white_color.blue())
                grayscale_values.add(white_color.red())
                self.assertEqual(inverted_color.red(), 255 - white_color.red())
                self.assertEqual(inverted_color.green(), 255 - white_color.green())
                self.assertEqual(inverted_color.blue(), 255 - white_color.blue())
                self.assertEqual(inverted_color.alpha(), white_color.alpha())
                checked_pixels += 1
        self.assertGreater(colored_pixels, 0)
        self.assertGreater(checked_pixels, 100)
        self.assertGreater(len(grayscale_values), 12)
        self.assertTrue(any(0 < value < 255 for value in grayscale_values))

    def test_main_field_updates_logo_visibility_without_rebuilding_dots(self) -> None:
        field = FieldView()
        for mode in ("white", "inverted", "grass"):
            field.set_field_mode(mode)
            self.assertIsNotNone(field.field_logo_item)
            self.assertAlmostEqual(field.field_logo_item.opacity(), field_logo_opacity(mode), places=3)
            field.set_field_logo_visible(False)
            self.assertFalse(field.field_logo_item.isVisible())
            field.set_field_logo_visible(True)
            self.assertTrue(field.field_logo_item.isVisible())
        field.deleteLater()

    def test_visibility_setting_defaults_on_and_persists_off(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            settings = QSettings(str(Path(temp) / "settings.ini"), QSettings.Format.IniFormat)
            self.assertTrue(field_logo_enabled(settings))
            settings.setValue(FIELD_LOGO_SETTING, False)
            settings.sync()
            self.assertFalse(field_logo_enabled(settings))

    def test_custom_logo_is_copied_and_appearance_values_are_persistent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            settings = QSettings(str(directory / "settings.ini"), QSettings.Format.IniFormat)
            source = directory / "school.png"
            target = directory / "stored.png"
            image = QImage(120, 60, QImage.Format.Format_ARGB32)
            image.fill(QColor("#2f6fed"))
            self.assertTrue(image.save(str(source)))
            installed = install_custom_field_logo(source, settings, destination=target)
            self.assertEqual(installed, target)
            self.assertEqual(custom_field_logo_path(settings), target)
            self.assertEqual(active_field_logo_path(settings), target)
            set_field_logo_appearance(0.42, 1.75, settings)
            self.assertAlmostEqual(field_logo_user_opacity(settings), 0.42)
            self.assertAlmostEqual(field_logo_user_scale(settings), 1.75)
            default_dimensions = field_logo_dimensions_yards(
                SurfaceDefinition(),
                field_logo_pixmap("grass", settings),
                QSettings(str(directory / "defaults.ini"), QSettings.Format.IniFormat),
            )
            custom_dimensions = field_logo_dimensions_yards(
                SurfaceDefinition(),
                field_logo_pixmap("grass", settings),
                settings,
            )
            self.assertAlmostEqual(
                custom_dimensions[0] / default_dimensions[0],
                1.75 / DEFAULT_FIELD_LOGO_SCALE,
                places=2,
            )

    def test_preferences_applies_center_field_logo_toggle(self) -> None:
        receiver = PreferenceReceiver()
        dialog = PreferencesDialog("dark", parent=receiver, current_show_field_logo=True)
        dialog.field_logo_checkbox.setChecked(False)
        dialog.field_logo_opacity_slider.setValue(46)
        dialog.field_logo_size_slider.setValue(165)
        dialog.apply_clicked()
        self.assertFalse(receiver.logo_visible)
        self.assertEqual(receiver.logo_appearance, ("", True, 0.46, 1.65))
        dialog.deleteLater()
        receiver.deleteLater()


if __name__ == "__main__":
    unittest.main()
