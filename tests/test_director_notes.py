from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSize
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QApplication

from drill_writer.core.models import DrillSet
from drill_writer.core.print_layout import PrintLayoutElement, default_print_layout
from drill_writer.core.project_io import create_project_folder, load_project, save_project
from drill_writer.export.exporters import PrintTemplateOptions, export_drill_sheet_pdf, export_staff_packet_pdf
from drill_writer.ui.main_window import MainWindow


class DirectorNotesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def pdf_page_digest(self, path: Path, page: int) -> str:
        document = QPdfDocument()
        try:
            self.assertEqual(document.load(str(path)), QPdfDocument.Error.None_)
            self.assertGreater(document.pageCount(), page)
            image = document.render(page, QSize(900, 700))
            data = QByteArray()
            buffer = QBuffer(data)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            image.save(buffer, "PNG")
            buffer.close()
            return hashlib.sha256(bytes(data)).hexdigest()
        finally:
            document.close()

    def test_set_notes_round_trip_with_legacy_alias(self) -> None:
        drill_set = DrillSet("Impact", 33, 48, director_notes="Guard frames the brass release.")
        restored = DrillSet.from_json(drill_set.to_json())
        self.assertEqual(restored.director_notes, "Guard frames the brass release.")

        legacy = drill_set.to_json()
        legacy["directors_notes"] = legacy.pop("director_notes")
        self.assertEqual(
            DrillSet.from_json(legacy).director_notes,
            "Guard frames the brass release.",
        )

    def test_set_editor_notes_are_undoable_and_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Director Notes", None, 152, 8, "4/4", 8)
            window = MainWindow(project_dir)
            try:
                note = "Woodwinds spiral inward; guard releases on count 7."
                window.begin_set_director_notes_edit()
                window.set_director_notes.setPlainText(note)
                window.finish_set_director_notes_edit()
                self.assertEqual(window.current_set().director_notes, note)

                window.undo_stack.undo()
                self.assertEqual(window.current_set().director_notes, "")
                window.undo_stack.redo()
                self.assertEqual(window.current_set().director_notes, note)

                save_project(project_dir, window.project, backup=False)
                self.assertEqual(load_project(project_dir).sets[0].director_notes, note)
            finally:
                window.close()

    def test_notes_render_on_drill_sheet_and_staff_set_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project_dir = create_project_folder(root, "Notes Export", None, 144, 8, "4/4", 12)
            project = load_project(project_dir)
            blank_drill = root / "blank_drill.pdf"
            blank_staff = root / "blank_staff.pdf"
            export_drill_sheet_pdf(blank_drill, project, project_dir)
            export_staff_packet_pdf(blank_staff, project, project_dir)

            project.sets[0].director_notes = (
                "Full ensemble rotates clockwise while the guard creates a low-to-high color gradient."
            )
            noted_drill = root / "noted_drill.pdf"
            noted_staff = root / "noted_staff.pdf"
            export_drill_sheet_pdf(noted_drill, project, project_dir)
            export_staff_packet_pdf(noted_staff, project, project_dir)

            self.assertNotEqual(
                self.pdf_page_digest(blank_drill, 0),
                self.pdf_page_digest(noted_drill, 0),
            )
            self.assertNotEqual(
                self.pdf_page_digest(blank_staff, 1),
                self.pdf_page_digest(noted_staff, 1),
            )

    def test_custom_layout_can_place_director_notes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project_dir = create_project_folder(root, "Custom Notes", None, 160, 8, "4/4", 4)
            project = load_project(project_dir)
            project.sets[0].director_notes = "Company front resolves into the final picture."
            layout = default_print_layout("drill_sheet")
            layout.elements.append(
                PrintLayoutElement(
                    element_type="text",
                    x=0.08,
                    y=0.15,
                    width=0.84,
                    height=0.06,
                    text="{director_notes}",
                    font_size=10,
                    background="#fffaf0",
                    border_color="#d8a928",
                    border_width=1,
                    padding=8,
                )
            )
            output = root / "custom_notes.pdf"
            export_drill_sheet_pdf(
                output,
                project,
                project_dir,
                options=PrintTemplateOptions(layout=layout.to_json()),
            )
            self.assertGreater(output.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
