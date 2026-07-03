from __future__ import annotations

from array import array
from math import sin, pi
from pathlib import Path
import wave

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from drill_writer.core.models import DrillProject
from drill_writer.core.timing import count_to_audio_ms


class WaveformWidget(QWidget):
    position_selected = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(92)
        self.samples: list[float] = []
        self.duration_ms = 0
        self.position_ms = 0
        self.project: DrillProject | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_project(self, project: DrillProject) -> None:
        self.project = project
        self.update()

    def load_audio(self, path: Path | None) -> None:
        self.samples = []
        self.duration_ms = 0
        if path and path.exists():
            if path.suffix.lower() == ".wav":
                self.load_wav(path)
            if not self.samples:
                self.load_with_pydub(path)
        self.update()

    def load_wav(self, path: Path) -> None:
        try:
            with wave.open(str(path), "rb") as audio:
                frame_rate = max(1, audio.getframerate())
                frame_count = audio.getnframes()
                channels = max(1, audio.getnchannels())
                sample_width = audio.getsampwidth()
                self.duration_ms = int(frame_count / frame_rate * 1000)
                raw = audio.readframes(frame_count)
                if sample_width == 2:
                    samples = array("h")
                    samples.frombytes(raw)
                    mono = samples[::channels]
                    self.samples = downsample(mono, 900)
                elif sample_width == 1:
                    mono = array("h", ((value - 128) * 256 for value in raw[::channels]))
                    self.samples = downsample(mono, 900)
        except Exception:
            self.samples = []

    def load_with_pydub(self, path: Path) -> None:
        try:
            from pydub import AudioSegment

            audio = AudioSegment.from_file(path).set_channels(1)
            self.duration_ms = len(audio)
            raw = audio.get_array_of_samples()
            self.samples = downsample(raw, 900)
        except Exception:
            self.samples = []

    def set_duration_ms(self, duration_ms: int) -> None:
        self.duration_ms = max(self.duration_ms, duration_ms)
        if self.duration_ms > 0 and not self.samples:
            self.samples = fallback_waveform_samples(900)
        self.update()

    def set_position_ms(self, position_ms: int) -> None:
        self.position_ms = max(0, position_ms)
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(8, 6, -8, -6)
        painter.fillRect(self.rect(), QColor("#111318"))
        painter.setPen(QPen(QColor("#303744"), 1))
        painter.setBrush(QColor("#171b23"))
        painter.drawRoundedRect(rect, 5, 5)

        center_y = rect.center().y()
        if self.samples:
            bar_width = max(1, rect.width() / max(1, len(self.samples)))
            painter.setPen(QPen(QColor("#66d9ef"), 1))
            for index, sample in enumerate(self.samples):
                x = rect.left() + index * bar_width
                height = sample * rect.height() * 0.42
                painter.drawLine(int(x), int(center_y - height), int(x), int(center_y + height))
        else:
            painter.setPen(QPen(QColor("#647084"), 1))
            painter.drawLine(rect.left(), center_y, rect.right(), center_y)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Load audio to show waveform")

        if self.project and self.duration_ms > 0:
            painter.setPen(QPen(QColor("#f7d154"), 1, Qt.PenStyle.DashLine))
            for event in self.project.timing_events:
                if event.event_type != "anchor":
                    continue
                x = rect.left() + (event.milliseconds / self.duration_ms) * rect.width()
                painter.drawLine(int(x), rect.top(), int(x), rect.bottom())
            painter.setPen(QPen(QColor("#b057ff"), 1, Qt.PenStyle.DotLine))
            for marker in self.project.markers:
                marker_ms = count_to_audio_ms(self.project, marker.count)
                x = rect.left() + (marker_ms / self.duration_ms) * rect.width()
                painter.drawLine(int(x), rect.top(), int(x), rect.bottom())

        if self.duration_ms > 0:
            x = rect.left() + min(1.0, self.position_ms / self.duration_ms) * rect.width()
            painter.setPen(QPen(QColor("#ff4f6d"), 2))
            painter.drawLine(int(x), rect.top(), int(x), rect.bottom())

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.seek_from_mouse(event.position().x())

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.seek_from_mouse(event.position().x())

    def seek_from_mouse(self, x: float) -> None:
        if self.duration_ms <= 0:
            return
        rect = self.rect().adjusted(8, 6, -8, -6)
        progress = max(0.0, min(1.0, (x - rect.left()) / max(1, rect.width())))
        self.position_selected.emit(int(progress * self.duration_ms))


def downsample(samples: array, target_count: int) -> list[float]:
    if not samples:
        return []
    max_sample = max(1, max(abs(sample) for sample in samples))
    stride = max(1, len(samples) // target_count)
    result: list[float] = []
    for index in range(0, len(samples), stride):
        chunk = samples[index : index + stride]
        if not chunk:
            continue
        result.append(max(abs(sample) for sample in chunk) / max_sample)
    return result[:target_count]


def fallback_waveform_samples(target_count: int) -> list[float]:
    return [
        0.18 + 0.08 * abs(sin(index / target_count * pi * 18))
        for index in range(target_count)
    ]
