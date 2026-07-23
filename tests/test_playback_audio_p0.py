from __future__ import annotations

import math
import struct
import tempfile
import time
import unittest
import wave
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from drill_writer.core.audio_recovery import (
    AudioRecoveryPolicy,
    WINDOWS_DEFAULT_DEVICE_ID,
    choose_audio_device_id,
    is_recoverable_audio_device_error,
    recommended_audio_resume_delay_ms,
)
from drill_writer.core.playback import FrameScheduler, PlaybackFrameCache, PlaybackQuality
from drill_writer.core.project_io import save_project
from drill_writer.core.timing import count_to_audio_ms
from drill_writer.core.waveform import (
    WaveformData,
    decode_audio_waveform,
    waveform_from_timed_envelopes,
)
from drill_writer.ui.main_window import MainWindow
from drill_writer.ui.waveform import WaveformWidget
from reliability_fixtures import playback_project


def write_dynamic_wav(
    path: Path,
    *,
    sample_rate: int,
    duration_seconds: float,
    sample_width: int = 2,
    channels: int = 1,
) -> None:
    frame_count = max(1, int(sample_rate * duration_seconds))
    maximum = {1: 127, 2: 32767, 3: 8388607, 4: 2147483647}[sample_width]
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(sample_width)
        output.setframerate(sample_rate)
        chunk = bytearray()
        for frame in range(frame_count):
            progress = frame / max(1, frame_count - 1)
            amplitude = 0.04
            if 0.43 <= progress <= 0.58:
                amplitude = 0.78
            if 0.76 <= progress <= 0.78:
                amplitude = 0.98
            value = int(math.sin(frame / max(1, sample_rate) * math.tau * 220.0) * maximum * amplitude)
            if sample_width == 1:
                encoded = bytes((max(0, min(255, value + 128)),))
            elif sample_width == 2:
                encoded = struct.pack("<h", value)
            elif sample_width == 3:
                encoded = int(value).to_bytes(3, "little", signed=True)
            else:
                encoded = struct.pack("<i", value)
            chunk.extend(encoded * channels)
            if len(chunk) >= 65536:
                output.writeframesraw(chunk)
                chunk.clear()
        if chunk:
            output.writeframesraw(chunk)


class FrameSchedulerTests(unittest.TestCase):
    def test_scheduler_reports_deadlines_audio_anomalies_and_display_rate(self) -> None:
        scheduler = FrameScheduler(target_fps=60, adaptive=False)
        scheduler.reset(0.0)
        now = 0.0
        for _index in range(90):
            now += 16.67
            if scheduler.should_render(now):
                scheduler.record_render(5.0, now + 5.0)
        now += 70.0
        if scheduler.should_render(now):
            scheduler.record_render(6.0, now + 6.0)
        scheduler.record_audio_clock(1000)
        scheduler.record_audio_clock(820)
        scheduler.record_audio_clock(1900)
        snapshot = scheduler.snapshot()
        self.assertGreaterEqual(snapshot.missed_deadlines, 3)
        self.assertGreater(snapshot.displayed_fps, 50)
        self.assertEqual(snapshot.audio_clock_regressions, 1)
        self.assertEqual(snapshot.audio_clock_jumps, 1)

    def test_scheduler_degrades_and_recovers_without_changing_clock(self) -> None:
        scheduler = FrameScheduler(target_fps=60, adaptive=True)
        scheduler.reset(0.0)
        now = 0.0
        while scheduler.rendered_frames < 60:
            now += 16.67
            if scheduler.should_render(now):
                scheduler.record_render(30.0, now + 30.0)
        self.assertEqual(scheduler.quality, PlaybackQuality.PERFORMANCE)
        self.assertGreater(scheduler.snapshot().adaptive_skips, 0)

        for _index in range(1800):
            now += 16.67
            if scheduler.should_render(now):
                scheduler.record_render(3.0, now + 3.0)
            if scheduler.quality == PlaybackQuality.FULL:
                break
        self.assertEqual(scheduler.quality, PlaybackQuality.FULL)

    def test_frame_cache_quantizes_repeated_frames_and_evicts(self) -> None:
        cache: PlaybackFrameCache[str] = PlaybackFrameCache(max_frames=16)
        key = cache.key(2, 17.125, PlaybackQuality.BALANCED)
        cache.put(key, "frame")
        self.assertEqual(cache.get(cache.key(2, 17.1251, PlaybackQuality.BALANCED)), "frame")
        for index in range(30):
            cache.put((0, index), str(index))
        self.assertEqual(len(cache), 16)
        self.assertGreater(cache.hits, 0)


class AudioDeviceRecoveryTests(unittest.TestCase):
    def test_disconnect_default_change_and_reconnect_selection(self) -> None:
        selected = choose_audio_device_id("headphones", {"speakers", "headphones"}, "speakers")
        self.assertEqual(selected.physical_id, "headphones")
        self.assertFalse(selected.used_fallback)

        disconnected = choose_audio_device_id("headphones", {"speakers"}, "speakers")
        self.assertEqual(disconnected.physical_id, "speakers")
        self.assertTrue(disconnected.used_fallback)

        changed_default = choose_audio_device_id(
            WINDOWS_DEFAULT_DEVICE_ID,
            {"speakers", "bluetooth"},
            "bluetooth",
        )
        self.assertEqual(changed_default.physical_id, "bluetooth")

        reconnected = choose_audio_device_id("headphones", {"speakers", "headphones"}, "speakers")
        self.assertEqual(reconnected.physical_id, "headphones")

    def test_invalidation_backoff_and_bluetooth_latency(self) -> None:
        self.assertTrue(is_recoverable_audio_device_error("AUDCLNT_E_DEVICE_INVALIDATED"))
        self.assertTrue(is_recoverable_audio_device_error("Audio device was disconnected"))
        self.assertFalse(is_recoverable_audio_device_error("Unsupported media format"))
        self.assertGreater(
            recommended_audio_resume_delay_ms("Bluetooth Headset"),
            recommended_audio_resume_delay_ms("Built-in Speakers"),
        )
        policy = AudioRecoveryPolicy()
        first_delay = policy.schedule("device invalidated")
        self.assertEqual(first_delay, 0)
        self.assertIsNone(policy.schedule("duplicate signal"))
        policy.completed(False)
        self.assertEqual(policy.schedule("retry"), 120)
        policy.completed(True)
        self.assertEqual(policy.attempts, 0)


class WaveformReliabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_long_waveform_preserves_real_dynamics(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "long_program.wav"
            write_dynamic_wav(path, sample_rate=8000, duration_seconds=75.0)
            data = decode_audio_waveform(path, target_count=900)
            self.assertGreaterEqual(data.duration_ms, 74900)
            self.assertLessEqual(len(data.peaks), 900)
            self.assertGreater(max(data.peaks) - min(data.peaks), 0.7)
            self.assertGreater(max(data.rms) - min(data.rms), 0.5)

    def test_unusual_sample_rates_bit_depths_and_channels(self) -> None:
        combinations = (
            (8000, 1, 1),
            (11025, 2, 2),
            (44100, 3, 2),
            (96000, 4, 1),
        )
        with tempfile.TemporaryDirectory() as temp:
            for sample_rate, sample_width, channels in combinations:
                with self.subTest(rate=sample_rate, width=sample_width, channels=channels):
                    path = Path(temp) / f"audio_{sample_rate}_{sample_width}_{channels}.wav"
                    write_dynamic_wav(
                        path,
                        sample_rate=sample_rate,
                        duration_seconds=0.35,
                        sample_width=sample_width,
                        channels=channels,
                    )
                    data = decode_audio_waveform(path, target_count=96)
                    self.assertEqual(data.sample_rate, sample_rate)
                    self.assertIn(f"{sample_width * 8}-bit", data.source_format)
                    self.assertIn(f"{channels} channel", data.source_format)
                    self.assertTrue(data.peaks)

    def test_compressed_vbr_decoder_uses_timestamps_not_byte_rate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "variable_bitrate.mp3"
            path.write_bytes(b"simulated compressed fixture")
            calls: list[tuple[Path, int]] = []

            def fake_decoder(source: Path, target_count: int) -> WaveformData:
                calls.append((source, target_count))
                points = [
                    (0.0, 100.0, 60.0),
                    (83.0, 120.0, 70.0),
                    (515.0, 8000.0, 4200.0),
                    (900.0, 250.0, 130.0),
                    (1875.0, 15000.0, 9000.0),
                    (3995.0, 180.0, 90.0),
                ]
                return waveform_from_timed_envelopes(
                    points,
                    4000,
                    target_count,
                    sample_rate=48000,
                    source_format="MP3 VBR",
                )

            data = decode_audio_waveform(path, 160, compressed_decoder=fake_decoder)
            self.assertEqual(calls, [(path, 160)])
            self.assertEqual(data.duration_ms, 4000)
            self.assertEqual(data.sample_rate, 48000)
            self.assertEqual(data.source_format, "MP3 VBR")
            self.assertGreater(max(data.peaks) - min(data.peaks), 0.7)

    def test_widget_decodes_long_wav_without_blocking_the_ui(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "background.wav"
            write_dynamic_wav(path, sample_rate=8000, duration_seconds=30.0)
            widget = WaveformWidget()
            completed: list[tuple[bool, str]] = []
            loop = QEventLoop()
            widget.load_finished.connect(lambda success, message: (completed.append((success, message)), loop.quit()))
            started = time.perf_counter()
            widget.load_audio(path)
            returned_in = time.perf_counter() - started
            self.assertLess(returned_in, 0.25)
            if not completed:
                QTimer.singleShot(6000, loop.quit)
                loop.exec()
            self.assertTrue(completed)
            self.assertTrue(completed[0][0], completed[0][1])
            self.assertGreater(max(widget.samples) - min(widget.samples), 0.7)
            widget.cancel_loading()
            widget.deleteLater()


class SustainedPlaybackStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_pause_seek_loop_tempo_map_and_boundaries_under_ui_load(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = Path(temp) / "sustained_playback"
            project = playback_project(300)
            save_project(project_dir, project, backup=False)
            window = MainWindow(project_dir)
            window.playback_scheduler.quality = PlaybackQuality.PERFORMANCE
            for _pass in range(2):
                for set_index, drill_set in enumerate(window.project.sets):
                    window.set_index = set_index
                    for frame in range(35):
                        progress = frame / 34.0
                        count = drill_set.start_count + progress * (drill_set.end_count - drill_set.start_count)
                        window.set_count(
                            count,
                            seek_audio=False,
                            update_waveform=False,
                            refresh_paths=False,
                            playback_optimized=True,
                        )
            self.assertGreater(window.playback_frame_cache.hits, 0)
            self.assertEqual(len(window.field.dot_items), 300)

            seek_count = 24.5
            window.seek_audio_position(int(count_to_audio_ms(window.project, seek_count)))
            self.assertAlmostEqual(window.current_count, seek_count, delta=0.08)

            window.set_index = 0
            _start, end = window.project.sets[0].start_count, window.project.sets[1].start_count
            window.current_count = float(end) + 0.1
            window.loop_current_set.setChecked(True)
            window.playback_clock.start()
            window.playback_scheduler.reset(time.perf_counter() * 1000.0 - 20.0)
            window.tick_playback()
            self.assertEqual(window.set_index, 0)
            self.assertLess(window.current_count, float(end))

            window.play()
            self.assertTrue(window.play_timer.isActive())
            window.pause()
            self.assertFalse(window.play_timer.isActive())
            self.assertEqual(window.field.playback_quality, "full")
            window.close()
            window.deleteLater()


if __name__ == "__main__":
    unittest.main()
