from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


@dataclass(slots=True)
class CreatedPropDesign:
    name: str
    image_file: str
    width: float
    height: float
    layer: str


class PropDesignerCanvas(QGraphicsView):
    def __init__(self) -> None:
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.canvas_rect = QRectF(0, 0, 720, 384)
        self.scene.setSceneRect(self.canvas_rect.adjusted(-60, -60, 60, 60))
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setBackgroundBrush(QColor("#101419"))
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.tool = "select"
        self.fill_color = QColor("#f7d154")
        self.stroke_color = QColor("#111318")
        self.stroke_width = 4.0
        self.no_fill = False
        self.start_point: QPointF | None = None
        self.preview_item: QGraphicsItem | None = None

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        self.setDragMode(
            QGraphicsView.DragMode.RubberBandDrag
            if tool == "select"
            else QGraphicsView.DragMode.NoDrag
        )

    def set_style(self, fill: QColor, stroke: QColor, stroke_width: float, no_fill: bool) -> None:
        self.fill_color = QColor(fill)
        self.stroke_color = QColor(stroke)
        self.stroke_width = max(0.25, float(stroke_width))
        self.no_fill = bool(no_fill)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # type: ignore[override]
        painter.fillRect(rect, QColor("#0f1319"))
        painter.fillRect(self.canvas_rect, QColor("#ffffff"))
        checker = 24
        painter.setPen(Qt.PenStyle.NoPen)
        for row in range(int(self.canvas_rect.height() // checker) + 1):
            for column in range(int(self.canvas_rect.width() // checker) + 1):
                if (row + column) % 2:
                    painter.setBrush(QColor("#eef1f4"))
                    painter.drawRect(
                        QRectF(
                            self.canvas_rect.left() + column * checker,
                            self.canvas_rect.top() + row * checker,
                            checker,
                            checker,
                        )
                    )
        grid_pen = QPen(QColor("#cbd3dc"), 0.8, Qt.PenStyle.DotLine)
        painter.setPen(grid_pen)
        for x in range(0, int(self.canvas_rect.width()) + 1, 45):
            painter.drawLine(
                int(self.canvas_rect.left() + x),
                int(self.canvas_rect.top()),
                int(self.canvas_rect.left() + x),
                int(self.canvas_rect.bottom()),
            )
        for y in range(0, int(self.canvas_rect.height()) + 1, 45):
            painter.drawLine(
                int(self.canvas_rect.left()),
                int(self.canvas_rect.top() + y),
                int(self.canvas_rect.right()),
                int(self.canvas_rect.top() + y),
            )
        painter.setPen(QPen(QColor("#2f3744"), 2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.canvas_rect)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if self.tool == "select" or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self.start_point = self.mapToScene(event.position().toPoint())
        self.preview_item = self.create_item_for_tool(QRectF(self.start_point, self.start_point))
        if self.preview_item:
            self.scene.addItem(self.preview_item)
            self.preview_item.setSelected(True)
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self.start_point is None or self.preview_item is None:
            super().mouseMoveEvent(event)
            return
        current = self.mapToScene(event.position().toPoint())
        self.set_item_scene_rect(self.preview_item, QRectF(self.start_point, current).normalized())
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if self.start_point is None or self.preview_item is None:
            super().mouseReleaseEvent(event)
            return
        rect = self.preview_item.sceneBoundingRect()
        if rect.width() < 4 and rect.height() < 4:
            self.scene.removeItem(self.preview_item)
        self.start_point = None
        self.preview_item = None
        event.accept()

    def create_item_for_tool(self, rect: QRectF) -> QGraphicsItem | None:
        if self.tool == "rectangle":
            item = QGraphicsRectItem(rect)
        elif self.tool == "ellipse":
            item = QGraphicsEllipseItem(rect)
        elif self.tool == "line":
            item = QGraphicsLineItem(rect.left(), rect.top(), rect.right(), rect.bottom())
        else:
            return None
        self.prepare_item(item)
        self.apply_style_to_item(item)
        return item

    def prepare_item(self, item: QGraphicsItem) -> None:
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        item.setZValue(2)

    def apply_style_to_selected(self) -> None:
        for item in self.scene.selectedItems():
            self.apply_style_to_item(item)
            item.update()

    def apply_style_to_item(self, item: QGraphicsItem) -> None:
        pen = QPen(self.stroke_color, self.stroke_width)
        brush = Qt.BrushStyle.NoBrush if self.no_fill else self.fill_color
        if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
            item.setPen(pen)
            item.setBrush(brush)
        elif isinstance(item, QGraphicsLineItem):
            item.setPen(pen)
        elif isinstance(item, QGraphicsTextItem):
            item.setDefaultTextColor(self.fill_color)

    def selected_item(self) -> QGraphicsItem | None:
        selected = self.scene.selectedItems()
        return selected[0] if selected else None

    def delete_selected(self) -> None:
        for item in list(self.scene.selectedItems()):
            self.scene.removeItem(item)

    def duplicate_selected(self) -> None:
        for item in list(self.scene.selectedItems()):
            clone = self.clone_item(item)
            if clone:
                clone.moveBy(22, 22)
                self.scene.addItem(clone)
                item.setSelected(False)
                clone.setSelected(True)

    def clone_item(self, item: QGraphicsItem) -> QGraphicsItem | None:
        if isinstance(item, QGraphicsRectItem):
            clone = QGraphicsRectItem(item.sceneBoundingRect())
            clone.setPen(item.pen())
            clone.setBrush(item.brush())
        elif isinstance(item, QGraphicsEllipseItem):
            clone = QGraphicsEllipseItem(item.sceneBoundingRect())
            clone.setPen(item.pen())
            clone.setBrush(item.brush())
        elif isinstance(item, QGraphicsLineItem):
            line = item.line()
            clone = QGraphicsLineItem(line)
            clone.setPos(item.pos())
            clone.setPen(item.pen())
        elif isinstance(item, QGraphicsTextItem):
            clone = QGraphicsTextItem(item.toPlainText())
            clone.setFont(item.font())
            clone.setDefaultTextColor(item.defaultTextColor())
            clone.setTextWidth(item.textWidth())
            clone.setPos(item.scenePos())
        else:
            return None
        self.prepare_item(clone)
        clone.setRotation(item.rotation())
        return clone

    def add_text(self, text: str, font_size: int) -> None:
        item = QGraphicsTextItem(text)
        item.setFont(QFont("Segoe UI", font_size, QFont.Weight.Bold))
        item.setDefaultTextColor(self.fill_color)
        item.setTextWidth(240)
        item.setPos(self.canvas_rect.center() - QPointF(120, 24))
        self.prepare_item(item)
        self.scene.addItem(item)
        item.setSelected(True)

    def add_image(self, image_path: Path) -> None:
        pixmap = image_path
        _ = pixmap

    def bring_selected_forward(self) -> None:
        for item in self.scene.selectedItems():
            item.setZValue(item.zValue() + 1)

    def send_selected_backward(self) -> None:
        for item in self.scene.selectedItems():
            item.setZValue(item.zValue() - 1)

    def set_selected_rect(self, rect: QRectF, anchor: str = "center") -> None:
        item = self.selected_item()
        if item is None:
            return
        old_rect = item.sceneBoundingRect()
        anchored_rect = self.anchored_rect(old_rect, rect.width(), rect.height(), anchor)
        anchored_rect.moveTo(rect.x(), rect.y())
        if anchor != "manual":
            anchored_rect = self.anchored_rect(old_rect, rect.width(), rect.height(), anchor)
        self.set_item_scene_rect(item, anchored_rect.normalized())

    def anchored_rect(self, old_rect: QRectF, width: float, height: float, anchor: str) -> QRectF:
        width = max(1.0, width)
        height = max(1.0, height)
        if anchor == "top_left":
            top_left = old_rect.topLeft()
            return QRectF(top_left, top_left + QPointF(width, height))
        if anchor == "top_right":
            top_right = old_rect.topRight()
            return QRectF(top_right.x() - width, top_right.y(), width, height)
        if anchor == "bottom_left":
            bottom_left = old_rect.bottomLeft()
            return QRectF(bottom_left.x(), bottom_left.y() - height, width, height)
        if anchor == "bottom_right":
            bottom_right = old_rect.bottomRight()
            return QRectF(bottom_right.x() - width, bottom_right.y() - height, width, height)
        center = old_rect.center()
        return QRectF(center.x() - width / 2, center.y() - height / 2, width, height)

    def set_item_scene_rect(self, item: QGraphicsItem, rect: QRectF) -> None:
        if isinstance(item, QGraphicsRectItem):
            item.setPos(0, 0)
            item.setRect(rect)
        elif isinstance(item, QGraphicsEllipseItem):
            item.setPos(0, 0)
            item.setRect(rect)
        elif isinstance(item, QGraphicsLineItem):
            item.setPos(0, 0)
            item.setLine(rect.left(), rect.top(), rect.right(), rect.bottom())
        elif isinstance(item, QGraphicsTextItem):
            item.setPos(rect.topLeft())
            item.setTextWidth(max(10, rect.width()))

    def set_selected_manual_rect(self, x: float, y: float, width: float, height: float) -> None:
        item = self.selected_item()
        if item is None:
            return
        self.set_item_scene_rect(item, QRectF(x, y, max(1.0, width), max(1.0, height)))

    def render_image(self) -> QImage:
        image = QImage(
            int(self.canvas_rect.width()),
            int(self.canvas_rect.height()),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.fill(Qt.GlobalColor.transparent)
        selected = self.scene.selectedItems()
        for item in selected:
            item.setSelected(False)
        painter = QPainter(image)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        try:
            self.scene.render(
                painter,
                QRectF(0, 0, image.width(), image.height()),
                self.canvas_rect,
                Qt.AspectRatioMode.KeepAspectRatio,
            )
        finally:
            painter.end()
            for item in selected:
                item.setSelected(True)
        return image

    def clear_design(self) -> None:
        for item in list(self.scene.items()):
            self.scene.removeItem(item)


class PropScalePreview(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.width_yards = 8.0
        self.height_yards = 4.0
        self.setMinimumHeight(150)

    def set_prop_size(self, width_yards: float, height_yards: float) -> None:
        self.width_yards = max(0.1, float(width_yards))
        self.height_yards = max(0.1, float(height_yards))
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        field_ratio = 120 / 53.333
        field_width = rect.width()
        field_height = field_width / field_ratio
        if field_height > rect.height():
            field_height = rect.height()
            field_width = field_height * field_ratio
        field = QRectF(
            rect.center().x() - field_width / 2,
            rect.center().y() - field_height / 2,
            field_width,
            field_height,
        )
        painter.setPen(QPen(QColor("#6b747c"), 1))
        painter.setBrush(QColor("#f9fbf7"))
        painter.drawRoundedRect(field, 5, 5)
        painter.setPen(QPen(QColor("#cbd3dc"), 0.6))
        for index in range(13):
            x = field.left() + field.width() * index / 12
            painter.drawLine(int(x), int(field.top()), int(x), int(field.bottom()))
        prop_width = min(field.width(), self.width_yards / 120 * field.width())
        prop_height = min(field.height(), self.height_yards / 53.333 * field.height())
        prop = QRectF(
            field.center().x() - prop_width / 2,
            field.bottom() - field.height() * 0.1 - prop_height / 2,
            max(4, prop_width),
            max(4, prop_height),
        )
        painter.setPen(QPen(QColor("#111318"), 1.5))
        painter.setBrush(QColor(247, 209, 84, 190))
        painter.drawRoundedRect(prop, 3, 3)
        painter.setPen(QColor("#d8deea"))
        painter.drawText(
            rect.adjusted(0, rect.height() - 18, 0, 0),
            Qt.AlignmentFlag.AlignCenter,
            f"{self.width_yards:g} x {self.height_yards:g} yd on field",
        )


class PropDesignerDialog(QDialog):
    def __init__(self, project_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project_dir = project_dir
        self.created_design: CreatedPropDesign | None = None
        self.setWindowTitle("Prop Designer")
        self.setModal(True)
        self.setMinimumSize(860, 560)
        self.resize(1040, 680)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self.canvas = PropDesignerCanvas()
        self.canvas.setMinimumSize(480, 320)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.canvas.scene.selectionChanged.connect(self.sync_selected_controls)
        layout.addWidget(self.canvas, 1)

        side_shell = QWidget()
        side_shell.setMinimumWidth(280)
        side_shell.setMaximumWidth(360)
        side_shell_layout = QVBoxLayout(side_shell)
        side_shell_layout.setContentsMargins(0, 0, 0, 0)
        side_shell_layout.setSpacing(8)
        control_container = QWidget()
        side = QVBoxLayout(control_container)
        side.setContentsMargins(4, 4, 4, 4)
        side.setSpacing(8)
        control_scroll = QScrollArea()
        control_scroll.setWidgetResizable(True)
        control_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        control_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        control_scroll.setWidget(control_container)
        side_shell_layout.addWidget(control_scroll, 1)
        layout.addWidget(side_shell)

        self.name_input = QLineEdit("Designed Prop")
        self.layer_input = QLineEdit("Props")
        self.width_yards = QDoubleSpinBox()
        self.width_yards.setRange(0.25, 80)
        self.width_yards.setDecimals(2)
        self.width_yards.setValue(8.0)
        self.height_yards = QDoubleSpinBox()
        self.height_yards.setRange(0.25, 40)
        self.height_yards.setDecimals(2)
        self.height_yards.setValue(4.0)
        self.scale_preview = PropScalePreview()
        for widget in (self.width_yards, self.height_yards):
            widget.valueChanged.connect(self.update_scale_preview)
        project_group = QGroupBox("Field Size")
        project_form = QFormLayout(project_group)
        project_form.addRow("Name", self.name_input)
        project_form.addRow("Layer", self.layer_input)
        project_form.addRow("Width", self.width_yards)
        project_form.addRow("Height", self.height_yards)
        project_form.addRow(self.scale_preview)
        side.addWidget(project_group)

        tools_group = QGroupBox("Art Tools")
        tools_grid = QGridLayout(tools_group)
        tools = (
            ("Select", "select"),
            ("Square/Rect", "rectangle"),
            ("Circle/Oval", "ellipse"),
            ("Line", "line"),
        )
        for index, (label, tool) in enumerate(tools):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, value=tool: self.canvas.set_tool(value))
            tools_grid.addWidget(button, index // 2, index % 2)
        text_button = QPushButton("Text")
        text_button.clicked.connect(self.add_text)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self.canvas.delete_selected)
        duplicate_button = QPushButton("Duplicate")
        duplicate_button.clicked.connect(self.canvas.duplicate_selected)
        front_button = QPushButton("Bring Front")
        front_button.clicked.connect(self.canvas.bring_selected_forward)
        back_button = QPushButton("Send Back")
        back_button.clicked.connect(self.canvas.send_selected_backward)
        tools_grid.addWidget(text_button, 2, 0)
        tools_grid.addWidget(delete_button, 2, 1)
        tools_grid.addWidget(duplicate_button, 3, 0)
        tools_grid.addWidget(front_button, 3, 1)
        tools_grid.addWidget(back_button, 4, 0, 1, 2)
        side.addWidget(tools_group)

        style_group = QGroupBox("Color / Stroke")
        style_form = QFormLayout(style_group)
        self.fill_button = QPushButton("Fill Color")
        self.fill_button.clicked.connect(self.choose_fill)
        self.stroke_button = QPushButton("Stroke Color")
        self.stroke_button.clicked.connect(self.choose_stroke)
        self.no_fill = QCheckBox("No fill")
        self.stroke_width = QDoubleSpinBox()
        self.stroke_width.setRange(0.25, 40)
        self.stroke_width.setDecimals(2)
        self.stroke_width.setValue(4.0)
        for widget in (self.no_fill, self.stroke_width):
            changed = widget.toggled if isinstance(widget, QCheckBox) else widget.valueChanged
            changed.connect(self.apply_style)
        style_form.addRow(self.fill_button)
        style_form.addRow(self.stroke_button)
        style_form.addRow("Stroke Width", self.stroke_width)
        style_form.addRow("", self.no_fill)
        side.addWidget(style_group)

        inspect_group = QGroupBox("Selected Shape")
        inspect_form = QFormLayout(inspect_group)
        self.shape_x = self.position_spin()
        self.shape_y = self.position_spin()
        self.shape_w = self.size_spin()
        self.shape_h = self.size_spin()
        self.anchor_combo = QComboBox()
        self.anchor_combo.addItem("Center", "center")
        self.anchor_combo.addItem("Top Left", "top_left")
        self.anchor_combo.addItem("Top Right", "top_right")
        self.anchor_combo.addItem("Bottom Left", "bottom_left")
        self.anchor_combo.addItem("Bottom Right", "bottom_right")
        apply_rect = QPushButton("Apply Shape Size")
        apply_rect.clicked.connect(self.apply_shape_rect)
        inspect_form.addRow("X", self.shape_x)
        inspect_form.addRow("Y", self.shape_y)
        inspect_form.addRow("Width", self.shape_w)
        inspect_form.addRow("Height", self.shape_h)
        inspect_form.addRow("Scale Anchor", self.anchor_combo)
        inspect_form.addRow(apply_rect)
        side.addWidget(inspect_group)

        hint = QLabel(
            "Drag on the canvas with Rectangle, Circle/Oval, or Line selected. "
            "Use the shape inspector for exact scaling and anchor-based resizing."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #aeb7c8;")
        side.addWidget(hint)

        bottom = QHBoxLayout()
        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(self.confirm_clear)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        save_button = QPushButton("Save Prop")
        save_button.clicked.connect(self.save_design)
        bottom.addWidget(clear_button)
        bottom.addStretch(1)
        bottom.addWidget(cancel_button)
        bottom.addWidget(save_button)
        side_shell_layout.addLayout(bottom)
        self.update_scale_preview()

    def position_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-2000, 2000)
        spin.setDecimals(2)
        return spin

    def size_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(1, 3000)
        spin.setDecimals(2)
        return spin

    def sync_selected_controls(self) -> None:
        item = self.canvas.selected_item()
        enabled = item is not None
        for widget in (self.shape_x, self.shape_y, self.shape_w, self.shape_h, self.anchor_combo):
            widget.setEnabled(enabled)
        if not item:
            return
        rect = item.sceneBoundingRect()
        for spin, value in (
            (self.shape_x, rect.x()),
            (self.shape_y, rect.y()),
            (self.shape_w, rect.width()),
            (self.shape_h, rect.height()),
        ):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

    def update_scale_preview(self) -> None:
        self.scale_preview.set_prop_size(self.width_yards.value(), self.height_yards.value())

    def apply_style(self) -> None:
        self.canvas.set_style(
            QColor(self.fill_button.property("selected_color") or "#f7d154"),
            QColor(self.stroke_button.property("selected_color") or "#111318"),
            self.stroke_width.value(),
            self.no_fill.isChecked(),
        )
        self.canvas.apply_style_to_selected()

    def choose_fill(self) -> None:
        color = QColorDialog.getColor(QColor(self.fill_button.property("selected_color") or "#f7d154"), self)
        if not color.isValid():
            return
        self.fill_button.setProperty("selected_color", color.name())
        self.fill_button.setStyleSheet(f"background: {color.name()};")
        self.apply_style()

    def choose_stroke(self) -> None:
        color = QColorDialog.getColor(QColor(self.stroke_button.property("selected_color") or "#111318"), self)
        if not color.isValid():
            return
        self.stroke_button.setProperty("selected_color", color.name())
        self.stroke_button.setStyleSheet(f"background: {color.name()};")
        self.apply_style()

    def add_text(self) -> None:
        text, accepted = QInputDialog.getText(self, "Add Text", "Text:")
        if not accepted or not text.strip():
            return
        size, size_ok = QInputDialog.getInt(self, "Text Size", "Font size:", 48, 8, 220, 1)
        if not size_ok:
            return
        self.canvas.add_text(text.strip(), size)

    def apply_shape_rect(self) -> None:
        item = self.canvas.selected_item()
        if item is None:
            return
        old = item.sceneBoundingRect()
        width_changed = abs(self.shape_w.value() - old.width()) > 0.01
        height_changed = abs(self.shape_h.value() - old.height()) > 0.01
        if width_changed or height_changed:
            self.canvas.set_selected_rect(
                QRectF(self.shape_x.value(), self.shape_y.value(), self.shape_w.value(), self.shape_h.value()),
                str(self.anchor_combo.currentData() or "center"),
            )
        else:
            self.canvas.set_selected_manual_rect(
                self.shape_x.value(),
                self.shape_y.value(),
                self.shape_w.value(),
                self.shape_h.value(),
            )
        self.sync_selected_controls()

    def confirm_clear(self) -> None:
        if QMessageBox.question(self, "Clear Design", "Remove all shapes from this prop design?") == QMessageBox.StandardButton.Yes:
            self.canvas.clear_design()

    def save_design(self) -> None:
        if not self.canvas.scene.items(self.canvas.canvas_rect):
            QMessageBox.information(self, "Prop Designer", "Add at least one shape before saving.")
            return
        name = self.name_input.text().strip() or "Designed Prop"
        props_dir = self.project_dir / "props"
        props_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(char for char in name if char.isalnum() or char in (" ", "-", "_")).strip().replace(" ", "_")
        path = props_dir / f"{safe_name or 'prop'}_{int(time.time())}.png"
        image = self.canvas.render_image()
        if not image.save(str(path)):
            QMessageBox.warning(self, "Prop Designer", "Could not save the prop image.")
            return
        self.created_design = CreatedPropDesign(
            name=name,
            image_file=str(path.relative_to(self.project_dir)),
            width=self.width_yards.value(),
            height=self.height_yards.value(),
            layer=self.layer_input.text().strip() or "Props",
        )
        self.accept()
