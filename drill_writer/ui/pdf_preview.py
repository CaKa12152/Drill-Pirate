from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QDialog


class PdfPreviewDialog(QDialog):
    def __init__(self, preview_path: Path, default_save_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.preview_path = preview_path
        self.default_save_path = default_save_path
        self.saved_path: Path | None = None
        self.setWindowTitle("Export Preview")
        self.setMinimumSize(980, 720)
        self.resize(1120, 780)

        layout = QVBoxLayout(self)
        header = QLabel("Preview the PDF pages before saving.")
        header.setStyleSheet("font-size: 16px; font-weight: 650;")
        layout.addWidget(header)

        self.document = QPdfDocument(self)
        self.document.load(str(preview_path))
        self.view = QPdfView(self)
        self.view.setDocument(self.document)
        self.view.setZoomMode(QPdfView.ZoomMode.FitInView)
        layout.addWidget(self.view, 1)

        buttons = QHBoxLayout()
        save_button = QPushButton("Save As...")
        close_button = QPushButton("Close")
        save_button.clicked.connect(self.save_as)
        close_button.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(save_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def save_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF",
            str(self.default_save_path),
            "PDF (*.pdf)",
        )
        if not path:
            return
        target = Path(path)
        try:
            shutil.copyfile(self.preview_path, target)
        except Exception as exc:
            QMessageBox.warning(self, "Save Failed", str(exc))
            return
        self.saved_path = target
        self.accept()
