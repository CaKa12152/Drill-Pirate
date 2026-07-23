from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGraphicsTextItem

from drill_writer.core.models import Dot, DrillProject, ProjectMetadata
from drill_writer.ui.field_view import FieldView


class FieldTextThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.field = FieldView()
        project = DrillProject(
            ProjectMetadata("Theme Test", 160, 8, "4/4"),
            dots=[Dot("trumpet1", "T1", 0.0, 0.0)],
        )
        self.field.set_project(project)

    def tearDown(self) -> None:
        self.field.close()

    def test_marcher_labels_follow_each_field_mode(self) -> None:
        expected_light = {"white": False, "inverted": True, "grass": True}
        for mode, should_be_light in expected_light.items():
            with self.subTest(mode=mode):
                self.field.set_field_mode(mode)
                color = self.field.dot_items["trumpet1"].label.defaultTextColor()
                self.assertEqual(color.lightness() >= 200, should_be_light)

    def test_inverted_field_marking_text_is_light(self) -> None:
        self.field.set_field_mode("inverted")
        marking_labels = [
            item
            for item in self.field.scene.items()
            if isinstance(item, QGraphicsTextItem)
            and item.parentItem() is None
            and item.zValue() == -6
        ]
        self.assertGreater(len(marking_labels), 10)
        self.assertTrue(all(item.defaultTextColor().lightness() >= 200 for item in marking_labels))


if __name__ == "__main__":
    unittest.main()
