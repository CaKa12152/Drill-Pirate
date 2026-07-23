from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QDoubleSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from drill_writer.core.print_layout import (
    PAGE_ORIENTATIONS,
    PAGE_SIZES,
    PrintLayout,
    PrintLayoutElement,
    default_print_layout,
    expand_layout_text,
)


PAGE_DIMENSIONS = {
    "Letter": (8.5, 11.0),
    "Legal": (8.5, 14.0),
    "A4": (8.27, 11.69),
    "A3": (11.69, 16.54),
}

ELEMENT_LABELS = {
    "text": "Text",
    "image": "Image",
    "field": "Field View",
    "table": "Data Table",
    "rectangle": "Rectangle",
    "line": "Line",
}


class LayoutElementItem(QGraphicsRectItem):
    resize_margin = 14.0

    def __init__(self, dialog: "PdfLayoutDesignerDialog", element: PrintLayoutElement) -> None:
        super().__init__()
        self.dialog = dialog
        self.element = element
        self.resizing = False
        self.resize_start = QPointF()
        self.resize_rect = QRectF()
        self._syncing = False
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.sync_from_element()

    def sync_from_element(self) -> None:
        page = self.dialog.page_rect
        self._syncing = True
        self.setPos(page.left() + self.element.x * page.width(), page.top() + self.element.y * page.height())
        self.setRect(0, 0, self.element.width * page.width(), self.element.height * page.height())
        self.setTransformOriginPoint(self.rect().center())
        self.setRotation(self.element.rotation_degrees)
        self.setZValue(self.element.z_index + 10)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not self.element.locked)
        self._syncing = False
        self.update()

    def itemChange(self, change, value):  # type: ignore[override]
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and not self._syncing:
            position = QPointF(value)
            page = self.dialog.page_rect
            rect = self.rect()
            position.setX(max(page.left(), min(position.x(), page.right() - rect.width())))
            position.setY(max(page.top(), min(position.y(), page.bottom() - rect.height())))
            return position
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and not self._syncing:
            self.dialog.item_geometry_changed(self)
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if not self.element.locked:
            handle = QRectF(
                self.rect().right() - self.resize_margin,
                self.rect().bottom() - self.resize_margin,
                self.resize_margin,
                self.resize_margin,
            )
            if handle.contains(event.pos()):
                self.resizing = True
                self.resize_start = event.scenePos()
                self.resize_rect = QRectF(self.rect())
                self.setSelected(True)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self.resizing:
            delta = event.scenePos() - self.resize_start
            page = self.dialog.page_rect
            width = max(24.0, min(self.resize_rect.width() + delta.x(), page.right() - self.pos().x()))
            height = max(18.0, min(self.resize_rect.height() + delta.y(), page.bottom() - self.pos().y()))
            self.setRect(0, 0, width, height)
            self.setTransformOriginPoint(self.rect().center())
            self.dialog.item_geometry_changed(self)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if self.resizing:
            self.resizing = False
            self.dialog.item_geometry_changed(self)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        painter.save()
        painter.setOpacity(self.element.opacity)
        background = QColor(self.element.background)
        if background.alpha() > 0:
            painter.setBrush(background)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        border = QColor(self.element.border_color)
        if border.alpha() > 0 and self.element.border_width > 0:
            painter.setPen(QPen(border, max(1.0, self.element.border_width)))
        else:
            painter.setPen(QPen(QColor("#8d9aac"), 1, Qt.PenStyle.DashLine))
        painter.drawRoundedRect(self.rect(), self.element.corner_radius, self.element.corner_radius)

        content = self.rect().adjusted(6, 4, -6, -4)
        if self.element.element_type == "image":
            image_path = self.dialog.resolve_image_path(self.element.image_path)
            pixmap = QPixmap(str(image_path)) if image_path and image_path.exists() else QPixmap()
            if not pixmap.isNull():
                painter.drawPixmap(content.toRect(), pixmap)
            else:
                painter.setPen(QColor("#596575"))
                painter.drawText(content, Qt.AlignmentFlag.AlignCenter, "IMAGE\nDouble-click Browse in Properties")
        elif self.element.element_type in {"field", "table"}:
            painter.setPen(QColor("#2458d3"))
            painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            painter.drawText(content, Qt.AlignmentFlag.AlignCenter, ELEMENT_LABELS[self.element.element_type].upper())
        elif self.element.element_type == "line":
            painter.setPen(QPen(QColor(self.element.color), max(1.0, self.element.border_width or 2.0)))
            painter.drawLine(content.left(), content.center().y(), content.right(), content.center().y())
        elif self.element.element_type == "rectangle":
            pass
        else:
            painter.setPen(QColor(self.element.color))
            painter.setFont(
                QFont(
                    self.element.font_family,
                    max(7, int(self.element.font_size * 0.7)),
                    QFont.Weight.Bold if self.element.bold else QFont.Weight.Normal,
                    self.element.italic,
                )
            )
            alignment = {
                "left": Qt.AlignmentFlag.AlignLeft,
                "center": Qt.AlignmentFlag.AlignHCenter,
                "right": Qt.AlignmentFlag.AlignRight,
            }[self.element.alignment]
            preview_text = expand_layout_text(self.element.text, self.dialog.preview_context)
            painter.drawText(content, alignment | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap, preview_text)

        if self.isSelected():
            painter.setOpacity(1.0)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#b057ff"), 2))
            painter.drawRect(self.rect())
            painter.fillRect(
                QRectF(
                    self.rect().right() - self.resize_margin,
                    self.rect().bottom() - self.resize_margin,
                    self.resize_margin,
                    self.resize_margin,
                ),
                QColor("#b057ff"),
            )
        painter.restore()


class PdfLayoutDesignerDialog(QDialog):
    def __init__(
        self,
        profile: str,
        project_dir: Path,
        initial_layout: dict | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.profile = profile
        self.project_dir = Path(project_dir)
        self.layout_model = (
            PrintLayout.from_json(initial_layout, profile)
            if initial_layout and initial_layout.get("elements")
            else default_print_layout(profile)
        )
        self.page_rect = QRectF()
        self.page_item: QGraphicsRectItem | None = None
        self.items_by_id: dict[str, LayoutElementItem] = {}
        self._syncing_properties = False
        self.preview_context = {
            "show_title": "Example Show",
            "page_title": "Set 12 — Impact",
            "page_subtitle": "Counts 65–80  •  168 BPM",
            "set_name": "Set 12",
            "counts": "65–80",
            "tempo": "168 BPM",
            "director_notes": "Winds bloom outward while the guard frames the impact with a high release.",
            "performer": "T1",
            "section": "Trumpets",
            "instrument": "Trumpet",
            "page": "1",
            "pages": "24",
            "footer": "Page 1 of 24",
        }

        self.setWindowTitle("PDF Layout Designer")
        self.setMinimumSize(1120, 720)
        self.resize(1480, 900)
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel(f"PDF Layout Designer  •  {profile.replace('_', ' ').title()}")
        title.setStyleSheet("font-size: 18px; font-weight: 750;")
        header.addWidget(title)
        header.addStretch()
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(PAGE_SIZES)
        self.page_size_combo.setCurrentText(self.layout_model.page_size)
        self.orientation_combo = QComboBox()
        for orientation in PAGE_ORIENTATIONS:
            self.orientation_combo.addItem(orientation.title(), orientation)
        self.orientation_combo.setCurrentIndex(max(0, self.orientation_combo.findData(self.layout_model.orientation)))
        self.preview_mode_combo = QComboBox()
        self.preview_mode_combo.addItem("Set / Field Page", "field")
        self.preview_mode_combo.addItem("Overview / Table Page", "table")
        background_button = QPushButton("Page Color…")
        background_button.clicked.connect(self.choose_page_background)
        header.addWidget(QLabel("Page"))
        header.addWidget(self.page_size_combo)
        header.addWidget(self.orientation_combo)
        if profile in {"staff_packet", "section_packet"}:
            header.addWidget(QLabel("Preview"))
            header.addWidget(self.preview_mode_combo)
        header.addWidget(background_button)
        root.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.build_left_panel())
        splitter.addWidget(self.build_canvas())
        splitter.addWidget(self.build_property_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([250, 850, 330])
        root.addWidget(splitter, 1)

        bottom = QHBoxLayout()
        help_label = QLabel("Drag elements to move • drag the purple corner to resize • Ctrl+D duplicates • Delete removes")
        help_label.setObjectName("secondaryText")
        bottom.addWidget(help_label)
        bottom.addStretch()
        cancel_button = QPushButton("Cancel")
        apply_button = QPushButton("Apply Layout")
        apply_button.setDefault(True)
        cancel_button.clicked.connect(self.reject)
        apply_button.clicked.connect(self.accept)
        bottom.addWidget(cancel_button)
        bottom.addWidget(apply_button)
        root.addLayout(bottom)

        self.page_size_combo.currentTextChanged.connect(self.page_settings_changed)
        self.orientation_combo.currentIndexChanged.connect(self.page_settings_changed)
        self.preview_mode_combo.currentIndexChanged.connect(self.rebuild_canvas)
        self.scene.selectionChanged.connect(self.selection_changed)
        self.rebuild_canvas()
        self.refresh_element_list()

    def build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(220)
        panel.setMaximumWidth(290)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 4, 0)

        add_group = QGroupBox("Add Elements")
        add_grid = QGridLayout(add_group)
        for index, (element_type, label) in enumerate(ELEMENT_LABELS.items()):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, value=element_type: self.add_element(value))
            add_grid.addWidget(button, index // 2, index % 2)
        layout.addWidget(add_group)

        layer_group = QGroupBox("Layers")
        layer_layout = QVBoxLayout(layer_group)
        self.element_list = QListWidget()
        self.element_list.currentItemChanged.connect(self.layer_selection_changed)
        layer_layout.addWidget(self.element_list, 1)
        layer_buttons = QGridLayout()
        duplicate_button = QPushButton("Duplicate")
        delete_button = QPushButton("Delete")
        up_button = QPushButton("Bring Forward")
        down_button = QPushButton("Send Back")
        duplicate_button.clicked.connect(self.duplicate_selected)
        delete_button.clicked.connect(self.delete_selected)
        up_button.clicked.connect(lambda: self.change_layer(1))
        down_button.clicked.connect(lambda: self.change_layer(-1))
        for index, button in enumerate((duplicate_button, delete_button, up_button, down_button)):
            layer_buttons.addWidget(button, index // 2, index % 2)
        layer_layout.addLayout(layer_buttons)
        layout.addWidget(layer_group, 1)

        preset_group = QGroupBox("Reusable Presets")
        preset_layout = QVBoxLayout(preset_group)
        self.preset_combo = QComboBox()
        self.refresh_presets()
        preset_layout.addWidget(self.preset_combo)
        preset_buttons = QHBoxLayout()
        load_button = QPushButton("Load")
        save_button = QPushButton("Save As…")
        load_button.clicked.connect(self.load_preset)
        save_button.clicked.connect(self.save_preset)
        preset_buttons.addWidget(load_button)
        preset_buttons.addWidget(save_button)
        preset_layout.addLayout(preset_buttons)
        reset_button = QPushButton("Reset to Drill Pirate Default")
        reset_button.clicked.connect(self.reset_default)
        preset_layout.addWidget(reset_button)
        layout.addWidget(preset_group)
        return panel

    def build_canvas(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.view.setBackgroundBrush(QColor("#252b35"))
        layout.addWidget(self.view)
        return container

    def build_property_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(300)
        scroll.setMaximumWidth(390)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 0, 8, 8)

        self.property_group = QGroupBox("Element Properties")
        form = QFormLayout(self.property_group)
        self.element_name = QLabel("Select an element")
        self.x_spin = self.percent_spin()
        self.y_spin = self.percent_spin()
        self.width_spin = self.percent_spin()
        self.height_spin = self.percent_spin()
        self.rotation_spin = QDoubleSpinBox()
        self.rotation_spin.setRange(-360, 360)
        self.rotation_spin.setDecimals(1)
        self.rotation_spin.setSuffix("°")
        form.addRow("Type", self.element_name)
        form.addRow("X", self.x_spin)
        form.addRow("Y", self.y_spin)
        form.addRow("Width", self.width_spin)
        form.addRow("Height", self.height_spin)
        form.addRow("Rotation", self.rotation_spin)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setMaximumHeight(110)
        self.font_combo = QFontComboBox()
        self.font_size = QDoubleSpinBox()
        self.font_size.setRange(4, 160)
        self.font_size.setDecimals(1)
        self.bold_check = QCheckBox("Bold")
        self.italic_check = QCheckBox("Italic")
        self.alignment_combo = QComboBox()
        self.alignment_combo.addItems(["left", "center", "right"])
        self.text_color_button = QPushButton("Choose…")
        self.background_button = QPushButton("Choose…")
        self.border_button = QPushButton("Choose…")
        self.border_width = QDoubleSpinBox()
        self.border_width.setRange(0, 20)
        self.border_width.setDecimals(1)
        self.opacity_spin = QSpinBox()
        self.opacity_spin.setRange(0, 100)
        self.opacity_spin.setSuffix("%")
        self.corner_radius = QDoubleSpinBox()
        self.corner_radius.setRange(0, 100)
        self.corner_radius.setDecimals(1)
        self.padding_spin = QDoubleSpinBox()
        self.padding_spin.setRange(0, 100)
        self.padding_spin.setDecimals(1)
        self.image_path = QLineEdit()
        self.image_path.setReadOnly(True)
        image_button = QPushButton("Browse Image…")
        image_button.clicked.connect(self.choose_image)
        self.fit_combo = QComboBox()
        self.fit_combo.addItems(["contain", "cover", "stretch"])
        self.visible_check = QCheckBox("Visible")
        self.locked_check = QCheckBox("Lock element")
        form.addRow("Text / Tokens", self.text_edit)
        form.addRow("Font", self.font_combo)
        form.addRow("Font Size", self.font_size)
        form.addRow("Style", self.row_widget(self.bold_check, self.italic_check))
        form.addRow("Alignment", self.alignment_combo)
        form.addRow("Text / Line Color", self.text_color_button)
        form.addRow("Background", self.background_button)
        form.addRow("Border Color", self.border_button)
        form.addRow("Border Width", self.border_width)
        form.addRow("Corner Radius", self.corner_radius)
        form.addRow("Content Padding", self.padding_spin)
        form.addRow("Opacity", self.opacity_spin)
        form.addRow("Image", self.image_path)
        form.addRow("", image_button)
        form.addRow("Image Fit", self.fit_combo)
        form.addRow("Display", self.row_widget(self.visible_check, self.locked_check))
        layout.addWidget(self.property_group)

        token_group = QGroupBox("Dynamic Text Tokens")
        token_layout = QVBoxLayout(token_group)
        token_text = QLabel(
            "{show_title}  {page_title}  {page_subtitle}\n"
            "{set_name}  {counts}  {tempo}\n"
            "{director_notes}\n"
            "{performer}  {section}  {instrument}\n"
            "{page}  {pages}  {footer}"
        )
        token_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        token_text.setWordWrap(True)
        token_layout.addWidget(token_text)
        layout.addWidget(token_group)
        layout.addStretch()
        scroll.setWidget(panel)

        for spin in (self.x_spin, self.y_spin, self.width_spin, self.height_spin, self.rotation_spin):
            spin.valueChanged.connect(self.properties_changed)
        self.text_edit.textChanged.connect(self.properties_changed)
        self.font_combo.currentFontChanged.connect(self.properties_changed)
        self.font_size.valueChanged.connect(self.properties_changed)
        self.bold_check.toggled.connect(self.properties_changed)
        self.italic_check.toggled.connect(self.properties_changed)
        self.alignment_combo.currentTextChanged.connect(self.properties_changed)
        self.border_width.valueChanged.connect(self.properties_changed)
        self.corner_radius.valueChanged.connect(self.properties_changed)
        self.padding_spin.valueChanged.connect(self.properties_changed)
        self.opacity_spin.valueChanged.connect(self.properties_changed)
        self.fit_combo.currentTextChanged.connect(self.properties_changed)
        self.visible_check.toggled.connect(self.properties_changed)
        self.locked_check.toggled.connect(self.properties_changed)
        self.text_color_button.clicked.connect(lambda: self.choose_element_color("color"))
        self.background_button.clicked.connect(lambda: self.choose_element_color("background"))
        self.border_button.clicked.connect(lambda: self.choose_element_color("border_color"))
        self.property_group.setEnabled(False)
        return scroll

    @staticmethod
    def row_widget(*widgets: QWidget) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        for widget in widgets:
            layout.addWidget(widget)
        layout.addStretch()
        return container

    @staticmethod
    def percent_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0, 100)
        spin.setDecimals(2)
        spin.setSuffix("%")
        return spin

    def selected_item(self) -> LayoutElementItem | None:
        selected = [item for item in self.scene.selectedItems() if isinstance(item, LayoutElementItem)]
        return selected[0] if len(selected) == 1 else None

    def page_settings_changed(self) -> None:
        self.layout_model.page_size = self.page_size_combo.currentText()
        self.layout_model.orientation = str(self.orientation_combo.currentData())
        self.rebuild_canvas()

    def page_dimensions(self) -> tuple[float, float]:
        width, height = PAGE_DIMENSIONS.get(self.layout_model.page_size, PAGE_DIMENSIONS["Letter"])
        if self.layout_model.orientation == "landscape":
            return height, width
        return width, height

    def element_preview_visible(self, element: PrintLayoutElement) -> bool:
        if not element.visible:
            return False
        preview_mode = str(self.preview_mode_combo.currentData())
        if self.profile in {"staff_packet", "section_packet"}:
            if preview_mode == "field" and element.element_type == "table":
                return False
            if preview_mode == "table" and element.element_type == "field":
                return False
        return True

    def rebuild_canvas(self) -> None:
        selected_id = self.selected_item().element.element_id if self.selected_item() else ""
        self.scene.clear()
        self.items_by_id.clear()
        width_inches, height_inches = self.page_dimensions()
        scale = 720.0 / max(width_inches, height_inches)
        page_width = width_inches * scale
        page_height = height_inches * scale
        self.page_rect = QRectF(28, 28, page_width, page_height)
        self.scene.setSceneRect(0, 0, page_width + 56, page_height + 56)
        self.page_item = self.scene.addRect(
            self.page_rect,
            QPen(QColor("#9aa6b6"), 1),
            QColor(self.layout_model.background),
        )
        self.page_item.setZValue(-100)
        for element in sorted(self.layout_model.elements, key=lambda item: item.z_index):
            item = LayoutElementItem(self, element)
            item.setVisible(self.element_preview_visible(element))
            self.scene.addItem(item)
            self.items_by_id[element.element_id] = item
            if element.element_id == selected_id:
                item.setSelected(True)
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if hasattr(self, "view"):
            self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def item_geometry_changed(self, item: LayoutElementItem) -> None:
        page = self.page_rect
        item.element.x = (item.pos().x() - page.left()) / page.width()
        item.element.y = (item.pos().y() - page.top()) / page.height()
        item.element.width = item.rect().width() / page.width()
        item.element.height = item.rect().height() / page.height()
        if item.isSelected():
            self.sync_property_panel(item)

    def add_element(self, element_type: str) -> None:
        element = PrintLayoutElement(
            element_type=element_type,
            x=0.12,
            y=0.12,
            width=0.38 if element_type not in {"field", "table"} else 0.76,
            height=0.09 if element_type == "text" else 0.32 if element_type in {"field", "table", "image"} else 0.12,
            text="Double-click properties to edit" if element_type == "text" else "",
            z_index=max((item.z_index for item in self.layout_model.elements), default=-1) + 1,
            background="#eaf0fb" if element_type == "rectangle" else "#00000000",
            border_color="#2458d3" if element_type in {"rectangle", "line"} else "#d8dee8",
            border_width=2 if element_type in {"rectangle", "line"} else 1,
        )
        self.layout_model.elements.append(element)
        self.rebuild_canvas()
        self.refresh_element_list()
        item = self.items_by_id[element.element_id]
        item.setSelected(True)

    def delete_selected(self) -> None:
        item = self.selected_item()
        if item is None:
            return
        self.layout_model.elements = [element for element in self.layout_model.elements if element.element_id != item.element.element_id]
        self.rebuild_canvas()
        self.refresh_element_list()

    def duplicate_selected(self) -> None:
        item = self.selected_item()
        if item is None:
            return
        payload = item.element.to_json()
        payload.pop("id", None)
        payload["x"] = min(0.95, item.element.x + 0.025)
        payload["y"] = min(0.95, item.element.y + 0.025)
        payload["z_index"] = max((element.z_index for element in self.layout_model.elements), default=0) + 1
        duplicate = PrintLayoutElement.from_json(payload)
        self.layout_model.elements.append(duplicate)
        self.rebuild_canvas()
        self.refresh_element_list()
        self.items_by_id[duplicate.element_id].setSelected(True)

    def change_layer(self, delta: int) -> None:
        item = self.selected_item()
        if item is None:
            return
        item.element.z_index += int(delta)
        self.rebuild_canvas()
        self.refresh_element_list()
        self.items_by_id[item.element.element_id].setSelected(True)

    def selection_changed(self) -> None:
        item = self.selected_item()
        self.property_group.setEnabled(item is not None)
        if item is not None:
            self.sync_property_panel(item)
            for index in range(self.element_list.count()):
                list_item = self.element_list.item(index)
                if list_item.data(Qt.ItemDataRole.UserRole) == item.element.element_id:
                    self.element_list.blockSignals(True)
                    self.element_list.setCurrentItem(list_item)
                    self.element_list.blockSignals(False)
                    break

    def sync_property_panel(self, item: LayoutElementItem) -> None:
        element = item.element
        self._syncing_properties = True
        self.element_name.setText(ELEMENT_LABELS.get(element.element_type, element.element_type.title()))
        self.x_spin.setValue(element.x * 100)
        self.y_spin.setValue(element.y * 100)
        self.width_spin.setValue(element.width * 100)
        self.height_spin.setValue(element.height * 100)
        self.rotation_spin.setValue(element.rotation_degrees)
        self.text_edit.setPlainText(element.text)
        self.font_combo.setCurrentFont(QFont(element.font_family))
        self.font_size.setValue(element.font_size)
        self.bold_check.setChecked(element.bold)
        self.italic_check.setChecked(element.italic)
        self.alignment_combo.setCurrentText(element.alignment)
        self.border_width.setValue(element.border_width)
        self.corner_radius.setValue(element.corner_radius)
        self.padding_spin.setValue(element.padding)
        self.opacity_spin.setValue(round(element.opacity * 100))
        self.image_path.setText(element.image_path)
        self.fit_combo.setCurrentText(element.fit_mode)
        self.visible_check.setChecked(element.visible)
        self.locked_check.setChecked(element.locked)
        self.update_color_button(self.text_color_button, element.color)
        self.update_color_button(self.background_button, element.background)
        self.update_color_button(self.border_button, element.border_color)
        is_text = element.element_type == "text"
        is_image = element.element_type == "image"
        for widget in (self.text_edit, self.font_combo, self.font_size, self.bold_check, self.italic_check, self.alignment_combo):
            widget.setEnabled(is_text)
        self.image_path.setEnabled(is_image)
        self.fit_combo.setEnabled(is_image)
        self._syncing_properties = False

    def properties_changed(self, *_args) -> None:
        if self._syncing_properties:
            return
        item = self.selected_item()
        if item is None:
            return
        element = item.element
        element.x = self.x_spin.value() / 100
        element.y = self.y_spin.value() / 100
        element.width = max(0.01, self.width_spin.value() / 100)
        element.height = max(0.01, self.height_spin.value() / 100)
        element.rotation_degrees = self.rotation_spin.value()
        element.text = self.text_edit.toPlainText()
        element.font_family = self.font_combo.currentFont().family()
        element.font_size = self.font_size.value()
        element.bold = self.bold_check.isChecked()
        element.italic = self.italic_check.isChecked()
        element.alignment = self.alignment_combo.currentText()
        element.border_width = self.border_width.value()
        element.corner_radius = self.corner_radius.value()
        element.padding = self.padding_spin.value()
        element.opacity = self.opacity_spin.value() / 100
        element.fit_mode = self.fit_combo.currentText()
        element.visible = self.visible_check.isChecked()
        element.locked = self.locked_check.isChecked()
        element.__post_init__()
        item.sync_from_element()
        item.setVisible(self.element_preview_visible(element))
        self.refresh_element_list()

    def choose_element_color(self, attribute: str) -> None:
        item = self.selected_item()
        if item is None:
            return
        initial = QColor(getattr(item.element, attribute))
        color = QColorDialog.getColor(initial, self, "Choose Color", QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if not color.isValid():
            return
        setattr(item.element, attribute, color.name(QColor.NameFormat.HexArgb))
        item.update()
        self.sync_property_panel(item)

    def choose_page_background(self) -> None:
        color = QColorDialog.getColor(QColor(self.layout_model.background), self, "Choose Page Color")
        if not color.isValid():
            return
        self.layout_model.background = color.name()
        self.rebuild_canvas()

    def choose_image(self) -> None:
        item = self.selected_item()
        if item is None or item.element.element_type != "image":
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Add Image to PDF Layout",
            str(self.project_dir),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.svg)",
        )
        if not path:
            return
        source = Path(path)
        asset_dir = self.project_dir / "print_assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        target = asset_dir / source.name
        suffix = 2
        while target.exists() and target.resolve() != source.resolve():
            target = asset_dir / f"{source.stem}_{suffix}{source.suffix}"
            suffix += 1
        if target.resolve() != source.resolve():
            shutil.copy2(source, target)
        item.element.image_path = target.relative_to(self.project_dir).as_posix()
        self.image_path.setText(item.element.image_path)
        item.update()

    def resolve_image_path(self, image_path: str) -> Path | None:
        if not image_path:
            return None
        path = Path(image_path)
        return path if path.is_absolute() else self.project_dir / path

    @staticmethod
    def update_color_button(button: QPushButton, value: str) -> None:
        color = QColor(value)
        display = color.name(QColor.NameFormat.HexArgb)
        button.setText(display)
        button.setStyleSheet(f"background: {color.name()}; color: {'#111111' if color.lightness() > 150 else '#ffffff'};")

    def refresh_element_list(self) -> None:
        selected_id = self.selected_item().element.element_id if self.selected_item() else ""
        self.element_list.blockSignals(True)
        self.element_list.clear()
        for element in sorted(self.layout_model.elements, key=lambda value: value.z_index, reverse=True):
            label = ELEMENT_LABELS.get(element.element_type, element.element_type.title())
            if element.element_type == "text" and element.text:
                label += f" — {element.text[:24]}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, element.element_id)
            if element.locked:
                item.setText("🔒 " + item.text())
            if not element.visible:
                item.setText("◌ " + item.text())
            self.element_list.addItem(item)
            if element.element_id == selected_id:
                self.element_list.setCurrentItem(item)
        self.element_list.blockSignals(False)

    def layer_selection_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        element_id = str(current.data(Qt.ItemDataRole.UserRole))
        item = self.items_by_id.get(element_id)
        if item is not None:
            self.scene.clearSelection()
            item.setSelected(True)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Delete:
            self.delete_selected()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            self.duplicate_selected()
            event.accept()
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_D:
            self.duplicate_selected()
            event.accept()
            return
        super().keyPressEvent(event)

    def preset_settings(self) -> QSettings:
        return QSettings("OpenAI", "DrillWriter")

    def load_presets(self) -> dict[str, dict]:
        raw = self.preset_settings().value("pdf_layout/presets", "{}")
        try:
            data = json.loads(str(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return {str(name): value for name, value in data.items() if isinstance(value, dict)}

    def refresh_presets(self) -> None:
        current = self.preset_combo.currentText() if hasattr(self, "preset_combo") else ""
        if not hasattr(self, "preset_combo"):
            return
        self.preset_combo.clear()
        for name in sorted(self.load_presets()):
            self.preset_combo.addItem(name)
        if current:
            self.preset_combo.setCurrentText(current)

    def save_preset(self) -> None:
        name, accepted = QInputDialog.getText(self, "Save PDF Layout Preset", "Preset name")
        if not accepted or not name.strip():
            return
        presets = self.load_presets()
        presets[name.strip()] = self.layout_json()
        self.preset_settings().setValue("pdf_layout/presets", json.dumps(presets, sort_keys=True))
        self.refresh_presets()
        self.preset_combo.setCurrentText(name.strip())

    def load_preset(self) -> None:
        name = self.preset_combo.currentText()
        payload = self.load_presets().get(name)
        if not payload:
            return
        self.layout_model = PrintLayout.from_json(payload, self.profile)
        self.page_size_combo.setCurrentText(self.layout_model.page_size)
        self.orientation_combo.setCurrentIndex(max(0, self.orientation_combo.findData(self.layout_model.orientation)))
        self.rebuild_canvas()
        self.refresh_element_list()

    def reset_default(self) -> None:
        self.layout_model = default_print_layout(self.profile)
        self.page_size_combo.setCurrentText(self.layout_model.page_size)
        self.orientation_combo.setCurrentIndex(max(0, self.orientation_combo.findData(self.layout_model.orientation)))
        self.rebuild_canvas()
        self.refresh_element_list()

    def layout_json(self) -> dict:
        self.layout_model.page_size = self.page_size_combo.currentText()
        self.layout_model.orientation = str(self.orientation_combo.currentData())
        return deepcopy(self.layout_model.to_json())
