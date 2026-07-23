from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from drill_writer.ui.prop_designer import (
    DESIGN_DOCUMENT_VERSION,
    PropDesignerCanvas,
    PropDesignerDialog,
    PropFieldPreview,
)


def add_rectangle(canvas: PropDesignerCanvas, rect: QRectF):
    canvas.set_tool("rectangle")
    item = canvas.create_item_for_tool(rect)
    assert item is not None
    canvas.scene.addItem(item)
    canvas.scene.clearSelection()
    item.setSelected(True)
    canvas.commit_history()
    return item


class PropDesignerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_artboard_geometry_uses_real_yards(self) -> None:
        canvas = PropDesignerCanvas()
        canvas.set_physical_size(16.0, 8.0, rescale_items=False)
        item = add_rectangle(
            canvas,
            QRectF(
                canvas.canvas_rect.width() * 0.25,
                canvas.canvas_rect.height() * 0.25,
                canvas.canvas_rect.width() * 0.5,
                canvas.canvas_rect.height() * 0.5,
            ),
        )
        yard_rect = canvas.scene_rect_to_yards(canvas.item_scene_rect(item))
        self.assertAlmostEqual(yard_rect.x(), 4.0, places=2)
        self.assertAlmostEqual(yard_rect.y(), 2.0, places=2)
        self.assertAlmostEqual(yard_rect.width(), 8.0, places=2)
        self.assertAlmostEqual(yard_rect.height(), 4.0, places=2)
        canvas.set_selected_yard_rect(QRectF(1.0, 1.5, 6.0, 3.0))
        updated = canvas.scene_rect_to_yards(canvas.item_scene_rect(item))
        self.assertAlmostEqual(updated.x(), 1.0, places=2)
        self.assertAlmostEqual(updated.y(), 1.5, places=2)
        self.assertAlmostEqual(updated.width(), 6.0, places=2)
        self.assertAlmostEqual(updated.height(), 3.0, places=2)
        canvas.close()

    def test_history_duplicate_undo_and_redo_are_deterministic(self) -> None:
        canvas = PropDesignerCanvas()
        add_rectangle(canvas, QRectF(80, 80, 240, 120))
        canvas.duplicate_selected()
        self.assertEqual(len(canvas.design_items()), 2)
        canvas.undo()
        self.assertEqual(len(canvas.design_items()), 1)
        canvas.redo()
        self.assertEqual(len(canvas.design_items()), 2)
        first_state = canvas.serialize_items()
        canvas.undo()
        canvas.redo()
        self.assertEqual(canvas.serialize_items(), first_state)
        canvas.close()

    def test_image_layers_survive_document_serialization(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "art.png"
            image = QImage(160, 90, QImage.Format.Format_ARGB32)
            image.fill(QColor("#2f6fed"))
            self.assertTrue(image.save(str(source)))
            canvas = PropDesignerCanvas()
            self.assertTrue(canvas.add_image(source))
            payload = canvas.serialize_items()
            restored = PropDesignerCanvas()
            restored.restore_items(payload)
            self.assertEqual(len(restored.design_items()), 1)
            self.assertEqual(restored.serialize_items(), payload)
            canvas.close()
            restored.close()

    def test_save_outputs_high_resolution_png_and_editable_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = Path(temp)
            dialog = PropDesignerDialog(project_dir)
            add_rectangle(dialog.canvas, QRectF(60, 60, 600, 260))
            dialog.name_input.setText("Production Prop")
            dialog.width_yards.setValue(12.0)
            dialog.height_yards.setValue(5.0)
            dialog.field_x.setValue(-10.0)
            dialog.field_y.setValue(-24.0)
            dialog.apply_design_size()
            dialog.save_design()
            self.assertIsNotNone(dialog.created_design)
            design = dialog.created_design
            assert design is not None
            image_path = project_dir / design.image_file
            document_path = project_dir / design.design_file
            self.assertTrue(image_path.is_file())
            self.assertTrue(document_path.is_file())
            rendered = QImage(str(image_path))
            self.assertGreaterEqual(max(rendered.width(), rendered.height()), 1024)
            self.assertAlmostEqual(rendered.width() / rendered.height(), 12.0 / 5.0, places=2)
            payload = json.loads(document_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], DESIGN_DOCUMENT_VERSION)
            self.assertEqual(payload["width_yards"], 12.0)
            self.assertEqual(payload["height_yards"], 5.0)
            self.assertEqual(payload["field_x"], -10.0)
            self.assertEqual(payload["field_y"], -24.0)
            self.assertEqual(len(payload["items"]), 1)
            dialog.close()

    def test_field_preview_supports_detail_ranges_and_all_modes(self) -> None:
        preview = PropFieldPreview()
        image = QImage(240, 100, QImage.Format.Format_ARGB32)
        image.fill(QColor("#f7c94a"))
        preview.resize(520, 320)
        for mode in ("white", "inverted", "grass"):
            for view_width in (120.0, 60.0, 30.0, 20.0):
                preview.set_preview(image, 12.0, 5.0, 5.0, -20.0, mode, view_width)
                rendered = QImage(preview.size(), QImage.Format.Format_ARGB32)
                rendered.fill(QColor("#101419"))
                preview.render(rendered)
                self.assertFalse(rendered.isNull())
                self.assertEqual(preview.view_width_yards, view_width)
        preview.close()


if __name__ == "__main__":
    unittest.main()
