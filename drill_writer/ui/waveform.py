from __future__ import annotations

from array import array
from math import ceil, pi, sin, sqrt
from pathlib import Path

from PySide6.QtCore import QEventLoop, QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtMultimedia import QAudioBuffer, QAudioDecoder, QAudioFormat
from PySide6.QtWidgets import QWidget

from drill_writer.core.models import DrillProject
from drill_writer.core.timing import count_to_audio_ms
from drill_writer.core.waveform import (
    WaveformData,
    WaveformDecodeError,
    decode_audio_waveform,
    waveform_from_timed_envelopes,
)
from drill_writer.ui.theme import DEFAULT_THEME_TOKENS


class WaveformDecodeThread(QThread):
    decoded = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, generation: int, path: Path, target_count: int = 2200, parent=None) -> None:
        super().__init__(parent)
        self.generation = generation
        self.path = Path(path)
        self.target_count = max(32, int(target_count))

    def run(self) -> None:  # type: ignore[override]
        try:
            data = decode_audio_waveform(
                self.path,
                self.target_count,
                compressed_decoder=lambda path, target: decode_compressed_with_qt(
                    path,
                    target,
                    self.isInterruptionRequested,
                ),
                cancelled=self.isInterruptionRequested,
            )
            if not self.isInterruptionRequested():
                self.decoded.emit(self.generation, data)
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(self.generation, str(exc))


def decode_compressed_with_qt(
    path: Path,
    target_count: int,
    cancelled=lambda: False,
) -> WaveformData:
    decoder = QAudioDecoder()
    desired_format = QAudioFormat()
    desired_format.setChannelCount(1)
    desired_format.setSampleRate(44100)
    desired_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    decoder.setAudioFormat(desired_format)

    envelope_points: list[tuple[float, float, float]] = []
    decoded_sample_rate = 44100
    decoded_duration_ms = 0.0
    running_time_ms = 0.0
    loop = QEventLoop()
    timed_out = False

    def read_buffer() -> None:
        nonlocal decoded_sample_rate, decoded_duration_ms, running_time_ms
        if cancelled():
            decoder.stop()
            loop.quit()
            return
        buffer = decoder.read()
        buffer_format = buffer.format()
        decoded_sample_rate = max(1, buffer_format.sampleRate() or decoded_sample_rate)
        samples = audio_buffer_to_mono_samples(buffer)
        if not samples:
            return
        start_time = float(buffer.startTime()) / 1000.0 if buffer.startTime() >= 0 else running_time_ms
        duration_ms = max(0.001, len(samples) / decoded_sample_rate * 1000.0)
        block_size = max(64, min(2048, len(samples) // 4 or len(samples)))
        for sample_index in range(0, len(samples), block_size):
            block = samples[sample_index : sample_index + block_size]
            if not block:
                continue
            peak = max(max(block), -min(block))
            rms = sqrt(sum(float(value) * float(value) for value in block) / len(block))
            time_ms = start_time + sample_index / decoded_sample_rate * 1000.0
            envelope_points.append((time_ms, float(peak), rms))
        running_time_ms = max(running_time_ms, start_time + duration_ms)
        decoded_duration_ms = max(decoded_duration_ms, running_time_ms)

    def timeout() -> None:
        nonlocal timed_out
        timed_out = True
        decoder.stop()
        loop.quit()

    timeout_timer = QTimer()
    timeout_timer.setSingleShot(True)
    timeout_timer.timeout.connect(timeout)
    cancellation_timer = QTimer()
    cancellation_timer.setInterval(60)
    cancellation_timer.timeout.connect(
        lambda: (decoder.stop(), loop.quit()) if cancelled() else None
    )
    decoder.bufferReady.connect(read_buffer)
    decoder.finished.connect(loop.quit)
    decoder.finished.connect(timeout_timer.stop)
    if hasattr(decoder, "errorChanged"):
        decoder.errorChanged.connect(loop.quit)
    decoder.setSource(QUrl.fromLocalFile(str(path)))
    decoder.start()
    timeout_timer.start(120000)
    cancellation_timer.start()
    loop.exec()
    timeout_timer.stop()
    cancellation_timer.stop()
    decoder.stop()

    if cancelled():
        raise WaveformDecodeError("Waveform decode cancelled.")
    if envelope_points:
        return waveform_from_timed_envelopes(
            envelope_points,
            max(1, int(decoded_duration_ms)),
            target_count,
            sample_rate=decoded_sample_rate,
            source_format=path.suffix.lower().lstrip(".").upper() or "Compressed audio",
        )
    if timed_out:
        raise WaveformDecodeError("Waveform decode timed out after two minutes.")
    error = decoder.errorString()
    raise WaveformDecodeError(
        f"Waveform decode failed: {error or 'the Windows audio decoder returned no samples.'}"
    )


class WaveformWidget(QWidget):
    position_selected = Signal(int)
    load_finished = Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(92)
        self.samples: list[float] = []
        self.rms_samples: list[float] = []
        self.duration_ms = 0
        self.position_ms = 0
        self.load_error = ""
        self.source_format = ""
        self.sample_rate = 0
        self.loading = False
        self._decode_generation = 0
        self._decode_workers: list[WaveformDecodeThread] = []
        self.project: DrillProject | None = None
        self.theme_tokens = dict(DEFAULT_THEME_TOKENS["dark"])
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_theme_tokens(self, tokens: dict[str, str]) -> None:
        self.theme_tokens = dict(tokens)
        self.update()

    def set_project(self, project: DrillProject) -> None:
        self.project = project
        self.update()

    def load_audio(self, path: Path | None, _ffmpeg_path: str | None = None) -> None:
        self._decode_generation += 1
        generation = self._decode_generation
        self.samples = []
        self.rms_samples = []
        self.duration_ms = 0
        self.load_error = ""
        self.source_format = ""
        self.sample_rate = 0
        self.loading = bool(path and path.exists())
        for worker in self._decode_workers:
            if worker.isRunning():
                worker.requestInterruption()
        if not path or not path.exists():
            self.update()
            return
        worker = WaveformDecodeThread(generation, path, parent=self)
        self._decode_workers.append(worker)

        def decoded(completed_generation: int, data: WaveformData) -> None:
            if completed_generation != self._decode_generation:
                return
            self.samples = list(data.peaks)
            self.rms_samples = list(data.rms)
            self.duration_ms = max(0, int(data.duration_ms))
            self.sample_rate = int(data.sample_rate)
            self.source_format = data.source_format
            self.load_error = ""
            self.loading = False
            self.update()
            self.load_finished.emit(True, f"Waveform loaded: {self.source_format}, {self.sample_rate:g} Hz")

        def failed(failed_generation: int, message: str) -> None:
            if failed_generation != self._decode_generation:
                return
            self.samples = []
            self.rms_samples = []
            self.load_error = message or "Could not decode waveform"
            self.loading = False
            self.update()
            self.load_finished.emit(False, self.load_error)

        def finished() -> None:
            if worker in self._decode_workers:
                self._decode_workers.remove(worker)
            worker.deleteLater()

        worker.decoded.connect(decoded)
        worker.failed.connect(failed)
        worker.finished.connect(finished)
        worker.start()
        self.update()

    def load_wav(self, path: Path) -> None:
        try:
            data = decode_audio_waveform(path, 2200)
            self.samples, self.rms_samples = list(data.peaks), list(data.rms)
            self.duration_ms = data.duration_ms
            self.sample_rate = data.sample_rate
            self.source_format = data.source_format
        except Exception as exc:
            self.samples = []
            self.rms_samples = []
            self.load_error = str(exc)

    def load_with_qt_decoder(self, path: Path) -> None:
        try:
            data = decode_compressed_with_qt(path, 2200)
            self.samples, self.rms_samples = list(data.peaks), list(data.rms)
            self.duration_ms = data.duration_ms
            self.sample_rate = data.sample_rate
            self.source_format = data.source_format
            self.load_error = ""
        except Exception as exc:
            self.samples = []
            self.rms_samples = []
            self.load_error = str(exc)

    def load_with_pydub(self, path: Path) -> None:
        self.samples = []
        self.rms_samples = []
        self.load_error = "Waveforms use the built-in Windows/Qt decoder and do not require ffmpeg."

    def cancel_loading(self, wait_ms: int = 3000) -> None:
        self._decode_generation += 1
        for worker in list(self._decode_workers):
            if worker.isRunning():
                worker.requestInterruption()
                worker.wait(max(0, int(wait_ms)))
        self.loading = False

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
        background = QColor(self.theme_tokens.get("background_color", "#111318"))
        surface = QColor(self.theme_tokens.get("surface_color", "#171b23"))
        border = QColor(self.theme_tokens.get("border_color", "#303744"))
        text = QColor(self.theme_tokens.get("muted_text_color", "#647084"))
        accent = QColor(self.theme_tokens.get("accent_color", "#f7d154"))
        selection = QColor(self.theme_tokens.get("selection_color", "#2f6fed"))
        painter.fillRect(self.rect(), background)
        painter.setPen(QPen(border, 1))
        painter.setBrush(surface)
        painter.drawRoundedRect(rect, 5, 5)

        center_y = rect.center().y()
        if self.samples:
            bar_width = max(1, rect.width() / max(1, len(self.samples)))
            painter.setPen(QPen(selection.darker(135), 1))
            for index, sample in enumerate(self.samples):
                x = rect.left() + index * bar_width
                height = sample * rect.height() * 0.42
                painter.drawLine(int(x), int(center_y - height), int(x), int(center_y + height))
            painter.setPen(QPen(selection.lighter(145), 2))
            for index, sample in enumerate(self.rms_samples or self.samples):
                x = rect.left() + index * bar_width
                height = sample * rect.height() * 0.42
                painter.drawLine(int(x), int(center_y - height), int(x), int(center_y + height))
        else:
            painter.setPen(QPen(text, 1))
            painter.drawLine(rect.left(), center_y, rect.right(), center_y)
            message = "Load audio to show waveform"
            if self.load_error:
                message = "Waveform unavailable - reload audio or use an audio format supported by Windows"
            elif self.loading:
                message = "Analyzing waveform..."
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, message)

        if self.project and self.duration_ms > 0:
            painter.setPen(QPen(accent, 1, Qt.PenStyle.DashLine))
            for event in self.project.timing_events:
                if event.event_type != "anchor":
                    continue
                x = rect.left() + (event.milliseconds / self.duration_ms) * rect.width()
                painter.drawLine(int(x), rect.top(), int(x), rect.bottom())
            painter.setPen(QPen(selection.lighter(120), 1, Qt.PenStyle.DotLine))
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
