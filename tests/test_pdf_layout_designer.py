from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QApplication

from drill_writer.core.print_layout import (
    PRINT_LAYOUT_SCHEMA_VERSION,
    PrintLayout,
    PrintLayoutElement,
    default_print_layout,
    expand_layout_text,
)
from drill_writer.core.project_io import create_project_folder, load_project
from drill_writer.export.exporters import (
    PrintTemplateOptions,
    export_coordinate_summary_pdf,
    export_dot_book_pdf,
    export_drill_sheet_pdf,
    export_staff_packet_pdf,
)
from drill_writer.ui.pdf_layout_designer import PdfLayoutDesignerDialog


class PrintLayoutModelTests(unittest.TestCase):
    def test_layout_round_trip_normalizes_geometry_and_style(self) -> None:
        layout = PrintLayout(
            name="Commercial Packet",
            profile="staff_packet",
            page_size="A3",
            orientation="portrait",
            background="#f4f1ea",
            elements=[
                PrintLayoutElement(
                    element_type="text",
                    x=0.9,
                    y=-2,
                    width=0.4,
                    height=0,
                    text="{show_title}",
                    opacity=3,
                    rotation_degrees=18,
                )
            ],
        )
        restored = PrintLayout.from_json(layout.to_json(), "staff_packet")
        self.assertEqual(restored.schema_version, PRINT_LAYOUT_SCHEMA_VERSION)
        self.assertEqual(restored.page_size, "A3")
        self.assertEqual(restored.orientation, "portrait")
        self.assertLessEqual(restored.elements[0].x + restored.elements[0].width, 1.0)
        self.assertGreaterEqual(restored.elements[0].y, 0.0)
        self.assertGreaterEqual(restored.elements[0].height, 0.01)
        self.assertEqual(restored.elements[0].opacity, 1.0)
        self.assertEqual(restored.elements[0].rotation_degrees, 18)

    def test_dynamic_text_tokens_expand_without_touching_unknown_tokens(self) -> None:
        text = expand_layout_text(
            "{show_title} / {set_name} / {custom}",
            {"show_title": "Pirate Show", "set_name": "Set 8"},
        )
        self.assertEqual(text, "Pirate Show / Set 8 / {custom}")


class PrintLayoutUiAndExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_designer_moves_resizes_adds_and_changes_orientation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dialog = PdfLayoutDesignerDialog("drill_sheet", Path(temp))
            try:
                initial_count = len(dialog.layout_model.elements)
                dialog.add_element("text")
                item = dialog.selected_item()
                self.assertIsNotNone(item)
                item.setPos(dialog.page_rect.left() + 120, dialog.page_rect.top() + 80)
                item.setRect(0, 0, 260, 90)
                dialog.item_geometry_changed(item)
                dialog.rotation_spin.setValue(27)
                dialog.orientation_combo.setCurrentIndex(dialog.orientation_combo.findData("portrait"))
                payload = dialog.layout_json()
                self.assertEqual(payload["orientation"], "portrait")
                self.assertEqual(len(payload["elements"]), initial_count + 1)
                added = payload["elements"][-1]
                self.assertGreater(added["x"], 0)
                self.assertGreater(added["width"], 0.2)
                self.assertEqual(added["rotation_degrees"], 27)
            finally:
                dialog.close()

    def test_all_pdf_profiles_render_custom_portrait_layout_with_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project_dir = create_project_folder(root, "Custom PDF", None, 160, 8, "4/4", 2)
            project = load_project(project_dir)
            asset_dir = project_dir / "print_assets"
            asset_dir.mkdir(parents=True, exist_ok=True)
            image = QImage(80, 40, QImage.Format.Format_ARGB32)
            image.fill(QColor("#d8a928"))
            self.assertTrue(image.save(str(asset_dir / "logo.png")))

            exporters = {
                "drill_sheet": lambda path, options: export_drill_sheet_pdf(
                    path,
                    project,
                    project_dir,
                    options=options,
                ),
                "dot_book": lambda path, options: export_dot_book_pdf(
                    path,
                    project,
                    options=options,
                    project_dir=project_dir,
                ),
                "staff_packet": lambda path, options: export_staff_packet_pdf(
                    path,
                    project,
                    project_dir,
                    options=options,
                ),
                "coordinate_summary": lambda path, options: export_coordinate_summary_pdf(
                    path,
                    project,
                    options=options,
                    project_dir=project_dir,
                ),
            }
            for profile, exporter in exporters.items():
                layout = default_print_layout(profile)
                layout.orientation = "portrait"
                layout.elements.append(
                    PrintLayoutElement(
                        element_type="image",
                        x=0.76,
                        y=0.02,
                        width=0.2,
                        height=0.09,
                        image_path="print_assets/logo.png",
                        fit_mode="contain",
                    )
                )
                output = root / f"{profile}.pdf"
                exporter(output, PrintTemplateOptions(layout=layout.to_json()))
                self.assertGreater(output.stat().st_size, 1000, profile)
                document = QPdfDocument()
                try:
                    self.assertEqual(document.load(str(output)), QPdfDocument.Error.None_, profile)
                    self.assertGreater(document.pageCount(), 0, profile)
                    page_size = document.pagePointSize(0)
                    self.assertGreater(page_size.height(), page_size.width(), profile)
                finally:
                    document.close()
                    del document
                    QApplication.processEvents()


if __name__ == "__main__":
    unittest.main()
