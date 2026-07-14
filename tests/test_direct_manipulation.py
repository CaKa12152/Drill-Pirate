from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from drill_writer.core.models import Dot
from drill_writer.ui.field_view import DotItem, EditorTool, FieldView


class DirectManipulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.view = FieldView()

    def tearDown(self) -> None:
        self.view.close()

    def test_hold_key_requests_temporary_tool_and_release(self) -> None:
        requests: list[tuple[EditorTool, bool, bool]] = []
        self.view.temporary_tool_requested.connect(
            lambda tool, active, dirty: requests.append((tool, active, dirty))
        )

        self.view.keyPressEvent(
            QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_R, Qt.KeyboardModifier.NoModifier)
        )
        self.assertEqual(requests[-1], (EditorTool.ROTATE, True, False))

        self.view.set_tool(EditorTool.ROTATE)
        self.view.keyReleaseEvent(
            QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_R, Qt.KeyboardModifier.NoModifier)
        )
        self.assertEqual(requests[-1], (EditorTool.ROTATE, False, False))

    def test_enter_and_escape_use_consistent_tool_actions(self) -> None:
        actions: list[str] = []
        self.view.apply_requested.connect(lambda: actions.append("apply"))
        self.view.cancel_requested.connect(lambda: actions.append("cancel"))
        self.view.set_tool(EditorTool.LINE)

        self.view.keyPressEvent(
            QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Enter, Qt.KeyboardModifier.NoModifier)
        )
        self.view.keyPressEvent(
            QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        )

        self.assertEqual(actions, ["apply", "cancel"])

    def test_shift_constrains_transform_rotation_and_scale(self) -> None:
        self.view._gizmo_drag_start_positions = {
            "a": (-1.0, -1.0),
            "b": (1.0, 1.0),
        }
        self.view._transform_pivot = (0.0, 0.0)
        self.view._gizmo_drag_handle_start = (1.0, 1.0)
        shift = int(Qt.KeyboardModifier.ShiftModifier.value)

        scale = self.view.transform_parameters_for_gizmo("scale_ne", (3.0, 2.0), shift)
        rotation = self.view.transform_parameters_for_gizmo("rotate", (0.0, 2.0), shift)

        self.assertEqual(scale.scale_x, scale.scale_y)
        self.assertAlmostEqual(rotation.rotation_degrees % 15.0, 0.0)

    def test_transform_handles_are_opt_in_and_require_multiple_marchers(self) -> None:
        for index, x in enumerate((-2.0, 2.0), start=1):
            dot = Dot(f"dot{index}", f"D{index}", x, 0.0)
            item = DotItem(dot, self.view.scale_factor, "dot")
            item.setPos(self.view.field_to_scene(x, 0.0))
            self.view.scene.addItem(item)
            self.view.dot_items[dot.id] = item

        first, second = self.view.dot_items.values()
        first.setSelected(True)
        self.view.set_transform_gizmo_enabled(True)
        self.assertEqual(self.view.transform_gizmo_items, [])

        second.setSelected(True)
        self.view.update_transform_gizmo()
        handle_kinds = {
            getattr(item, "kind", "")
            for item in self.view.transform_gizmo_items
        }
        self.assertTrue(self.view.transform_gizmo_items)
        self.assertFalse({"stretch_x", "stretch_y", "skew_x", "skew_y"} & handle_kinds)
        self.assertTrue(
            {"move", "rotate", "pivot", "scale_nw", "scale_ne", "scale_sw", "scale_se"}
            <= handle_kinds
        )


if __name__ == "__main__":
    unittest.main()
