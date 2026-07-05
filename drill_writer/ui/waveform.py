from __future__ import annotations

from array import array
from math import ceil, pi, sin, sqrt
from pathlib import Path
import wave

from PySide6.QtCore import QEventLoop, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtMultimedia import QAudioBuffer, QAudioDecoder, QAudioFormat
from PySide6.QtWidgets import QWidget

from drill_writer.core.models import DrillProject
from drill_writer.core.timing import count_to_audio_ms


class WaveformWidget(QWidget):
    position_selected = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(92)
        self.samples: list[float] = []
        self.rms_samples: list[float] = []
        self.duration_ms = 0
        self.position_ms = 0
        self.load_error = ""
        self.project: DrillProject | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_project(self, project: DrillProject) -> None:
        self.project = project
        self.update()

    def load_audio(self, path: Path | None, _ffmpeg_path: str | None = None) -> None:
        self.samples = []
        self.rms_samples = []
        self.duration_ms = 0
        self.load_error = ""
        if path and path.exists():
            if path.suffix.lower() == ".wav":
                self.load_wav(path)
            if not self.samples:
                self.load_with_qt_decoder(path)
            if not self.samples:
                self.load_with_pydub(path)
            if not self.samples and not self.load_error:
                self.load_error = "Could not decode waveform"
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
                    self.samples, self.rms_samples = analyze_waveform(mono, 2200)
                elif sample_width == 1:
                    mono = array("h", ((value - 128) * 256 for value in raw[::channels]))
                    self.samples, self.rms_samples = analyze_waveform(mono, 2200)
        except Exception:
            self.samples = []
            self.rms_samples = []

    def load_with_qt_decoder(self, path: Path) -> None:
        decoder = QAudioDecoder()
        desired_format = QAudioFormat()
        desired_format.setChannelCount(1)
        desired_format.setSampleRate(44100)
        desired_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        decoder.setAudioFormat(desired_format)

        decoded_samples: array = array("h")
        decoded_sample_rate = 44100
        loop = QEventLoop()
        timed_out = False

        def read_buffer() -> None:
            nonlocal decoded_sample_rate
            buffer = decoder.read()
            buffer_format = buffer.format()
            decoded_sample_rate = max(1, buffer_format.sampleRate() or decoded_sample_rate)
            decoded_samples.extend(audio_buffer_to_mono_samples(buffer))

        def timeout() -> None:
            nonlocal timed_out
            timed_out = True
            decoder.stop()
            loop.quit()

        timeout_timer = QTimer()
        timeout_timer.setSingleShot(True)
        timeout_timer.timeout.connect(timeout)
        decoder.bufferReady.connect(read_buffer)
        decoder.finished.connect(loop.quit)
        decoder.finished.connect(timeout_timer.stop)
        decoder.setSource(QUrl.fromLocalFile(str(path)))
        decoder.start()
        timeout_timer.start(12000)
        loop.exec()
        timeout_timer.stop()

        if decoded_samples:
            self.samples, self.rms_samples = analyze_waveform(decoded_samples, 2200)
            if self.duration_ms <= 0:
                self.duration_ms = int(len(decoded_samples) / decoded_sample_rate * 1000)
            self.load_error = ""
        elif timed_out:
            self.load_error = "Waveform decode timed out"
        elif decoder.errorString():
            self.load_error = f"Waveform decode failed: {decoder.errorString()}"

    def load_with_pydub(self, path: Path) -> None:
        try:
            from pydub import AudioSegment

            audio = AudioSegment.from_file(path).set_channels(1)
            self.duration_ms = len(audio)
            raw = audio.get_array_of_samples()
            self.samples, self.rms_samples = analyze_waveform(raw, 2200)
            self.load_error = ""
        except Exception:
            self.samples = []
            self.rms_samples = []
            self.load_error = "Waveform decode failed. Try reloading audio or converting the file to WAV."

    def set_duration_ms(self, duration_ms: int) -> None:
        self.duration_ms = max(self.duration_ms, duration_ms)
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
            painter.setPen(QPen(QColor("#2c4e6a"), 1))
            for index, sample in enumerate(self.samples):
                x = rect.left() + index * bar_width
                height = sample * rect.height() * 0.42
                painter.drawLine(int(x), int(center_y - height), int(x), int(center_y + height))
            painter.setPen(QPen(QColor("#7ee7ff"), 2))
            for index, sample in enumerate(self.rms_samples or self.samples):
                x = rect.left() + index * bar_width
                height = sample * rect.height() * 0.42
                painter.drawLine(int(x), int(center_y - height), int(x), int(center_y + height))
        else:
            painter.setPen(QPen(QColor("#647084"), 1))
            painter.drawLine(rect.left(), center_y, rect.right(), center_y)
            message = "Load audio to show waveform"
            if self.load_error:
                message = "Waveform unavailable - reload audio or use WAV/MP3 supported by Windows"
            elif self.duration_ms > 0:
                message = "Analyzing waveform..."
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, message)

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

    def detect_hit_moments(self, min_gap_ms: int = 260, max_hits: int = 96) -> list[int]:
        if self.duration_ms <= 0 or not self.samples:
            return []
        envelope = [
            peak * 0.68 + rms * 0.32
            for peak, rms in zip(self.samples, self.rms_samples or self.samples)
        ]
        if len(envelope) < 8:
            return []
        bin_ms = self.duration_ms / len(envelope)
        lookbehind_bins = max(3, int(450 / max(1, bin_ms)))
        candidates: list[tuple[float, int]] = []
        for index in range(2, len(envelope) - 2):
            current = envelope[index]
            if current < 0.22:
                continue
            if current < envelope[index - 1] or current < envelope[index + 1]:
                continue
            start = max(0, index - lookbehind_bins)
            local = envelope[start:index]
            local_average = sum(local) / max(1, len(local))
            score = current / max(0.04, local_average)
            if score >= 1.34:
                candidates.append((score * current, index))

        candidates.sort(reverse=True)
        selected: list[int] = []
        min_gap_bins = max(1, int(min_gap_ms / max(1, bin_ms)))
        for _score, index in candidates:
            if any(abs(index - selected_index) < min_gap_bins for selected_index in selected):
                continue
            selected.append(index)
            if len(selected) >= max_hits:
                break
        selected.sort()
        return [int(index * bin_ms) for index in selected]


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


def audio_buffer_to_mono_samples(buffer: QAudioBuffer) -> array:
    buffer_format = buffer.format()
    channel_count = max(1, buffer_format.channelCount())
    sample_format = buffer_format.sampleFormat()
    raw = bytes(memoryview(buffer.constData()))
    samples = array("h")
    if sample_format == QAudioFormat.SampleFormat.Int16:
        decoded = array("h")
        decoded.frombytes(raw)
        samples.extend(decoded[::channel_count])
    elif sample_format == QAudioFormat.SampleFormat.UInt8:
        samples.extend((value - 128) * 256 for value in raw[::channel_count])
    elif sample_format == QAudioFormat.SampleFormat.Int32:
        decoded_32 = array("i")
        decoded_32.frombytes(raw)
        samples.extend(max(-32768, min(32767, value // 65536)) for value in decoded_32[::channel_count])
    elif sample_format == QAudioFormat.SampleFormat.Float:
        decoded_float = array("f")
        decoded_float.frombytes(raw)
        samples.extend(max(-32768, min(32767, int(value * 32767))) for value in decoded_float[::channel_count])
    return samples


def analyze_waveform(samples, target_count: int) -> tuple[list[float], list[float]]:
    if not samples:
        return [], []
    stride = max(1, ceil(len(samples) / target_count))
    peaks: list[float] = []
    rms_values: list[float] = []
    for index in range(0, len(samples), stride):
        chunk = samples[index : index + stride]
        if not chunk:
            continue
        abs_values = [abs(sample) for sample in chunk]
        peaks.append(float(max(abs_values)))
        rms_values.append(sqrt(sum(value * value for value in abs_values) / len(abs_values)))
    if not peaks:
        return [], []
    normalized_peaks = robust_normalize(peaks, low_percentile=0.08, high_percentile=0.995, gamma=1.08)
    normalized_rms = robust_normalize(rms_values, low_percentile=0.12, high_percentile=0.97, gamma=1.35)
    return normalized_peaks[:target_count], normalized_rms[:target_count]


def robust_normalize(
    values: list[float],
    low_percentile: float,
    high_percentile: float,
    gamma: float,
) -> list[float]:
    if not values:
        return []
    sorted_values = sorted(values)
    low_index = min(len(sorted_values) - 1, max(0, int(len(sorted_values) * low_percentile)))
    high_index = min(len(sorted_values) - 1, max(0, int(len(sorted_values) * high_percentile)))
    floor = sorted_values[low_index]
    ceiling = max(floor + 1.0, sorted_values[high_index])
    normalized: list[float] = []
    for value in values:
        ratio = max(0.0, min(1.0, (value - floor) / (ceiling - floor)))
        normalized.append(0.03 + 0.97 * (ratio**gamma))
    return normalized


def fallback_waveform_samples(target_count: int) -> list[float]:
    return [
        0.18 + 0.08 * abs(sin(index / target_count * pi * 18))
        for index in range(target_count)
    ]
