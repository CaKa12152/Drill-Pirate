from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass
from enum import IntEnum
from math import floor
from statistics import fmean
from typing import Generic, TypeVar


class PlaybackQuality(IntEnum):
    FULL = 0
    BALANCED = 1
    PERFORMANCE = 2

    @property
    def label(self) -> str:
        return {
            PlaybackQuality.FULL: "Full",
            PlaybackQuality.BALANCED: "Balanced",
            PlaybackQuality.PERFORMANCE: "Performance",
        }[self]

    @property
    def render_fps(self) -> float:
        return {
            PlaybackQuality.FULL: 60.0,
            PlaybackQuality.BALANCED: 45.0,
            PlaybackQuality.PERFORMANCE: 30.0,
        }[self]

    @property
    def auxiliary_stride(self) -> int:
        return {
            PlaybackQuality.FULL: 1,
            PlaybackQuality.BALANCED: 3,
            PlaybackQuality.PERFORMANCE: 6,
        }[self]


class AudioClockInterpolator:
    def __init__(self, hard_resync_ms: float = 240.0) -> None:
        self.hard_resync_ms = max(40.0, float(hard_resync_ms))
        self.reset(0, 0.0)

    def reset(self, media_ms: int, monotonic_ms: float, rate: float = 1.0) -> None:
        position = max(0.0, float(media_ms))
        self.anchor_media_ms = position
        self.anchor_monotonic_ms = float(monotonic_ms)
        self.last_reported_ms = position
        self.last_output_ms = position
        self.rate = max(0.05, float(rate))
        self.initialized = True

    def sample(
        self,
        reported_ms: int,
        monotonic_ms: float,
        rate: float = 1.0,
        *,
        seeking: bool = False,
    ) -> int:
        now = float(monotonic_ms)
        playback_rate = max(0.05, float(rate))
        reported = max(0.0, float(reported_ms))
        if not self.initialized or seeking:
            self.reset(int(reported), now, playback_rate)
            return int(round(reported))

        predicted = self.anchor_media_ms + max(0.0, now - self.anchor_monotonic_ms) * self.rate
        if abs(playback_rate - self.rate) > 0.0001:
            self.anchor_media_ms = predicted
            self.anchor_monotonic_ms = now
            self.rate = playback_rate
            predicted = self.anchor_media_ms

        previous_reported = self.last_reported_ms
        if reported + 80.0 >= previous_reported:
            self.last_reported_ms = max(previous_reported, reported)
            if abs(reported - previous_reported) > 0.5:
                drift = reported - predicted
                if abs(drift) >= self.hard_resync_ms:
                    self.anchor_media_ms = reported
                    self.anchor_monotonic_ms = now
                    predicted = reported
                else:
                    correction = max(-24.0, min(24.0, drift * 0.22))
                    self.anchor_media_ms += correction
                    predicted += correction

        output = max(self.last_output_ms, predicted)
        self.last_output_ms = output
        return int(round(output))


@dataclass(frozen=True, slots=True)
class PlaybackDiagnosticsSnapshot:
    quality: PlaybackQuality
    callbacks: int
    rendered_frames: int
    dropped_frames: int
    missed_deadlines: int
    adaptive_skips: int
    average_render_ms: float
    p95_render_ms: float
    maximum_render_ms: float
    displayed_fps: float
    audio_clock_regressions: int
    audio_clock_jumps: int


class FrameScheduler:
    def __init__(
        self,
        *,
        target_fps: float = 60.0,
        adaptive: bool = True,
        sample_window: int = 180,
    ) -> None:
        self.target_fps = max(1.0, float(target_fps))
        self.target_interval_ms = 1000.0 / self.target_fps
        self.adaptive = bool(adaptive)
        self.sample_window = max(30, int(sample_window))
        self.quality = PlaybackQuality.FULL
        self.callbacks = 0
        self.rendered_frames = 0
        self.missed_deadlines = 0
        self.adaptive_skips = 0
        self.audio_clock_regressions = 0
        self.audio_clock_jumps = 0
        self._last_callback_ms: float | None = None
        self._last_render_ms: float | None = None
        self._last_audio_ms: int | None = None
        self._render_durations: deque[float] = deque(maxlen=self.sample_window)
        self._render_timestamps: deque[float] = deque(maxlen=self.sample_window)
        self._missed_history: deque[int] = deque(maxlen=self.sample_window)
        self._stable_windows = 0
        self._quality_changed = False

    def reset(self, now_ms: float | None = None) -> None:
        adaptive = self.adaptive
        target_fps = self.target_fps
        sample_window = self.sample_window
        self.__init__(target_fps=target_fps, adaptive=adaptive, sample_window=sample_window)
        self._last_callback_ms = now_ms

    def set_adaptive(self, enabled: bool) -> None:
        self.adaptive = bool(enabled)
        if not self.adaptive and self.quality != PlaybackQuality.FULL:
            self.quality = PlaybackQuality.FULL
            self._quality_changed = True

    def record_audio_clock(self, audio_ms: int, *, seeking: bool = False) -> None:
        current = int(audio_ms)
        previous = self._last_audio_ms
        self._last_audio_ms = current
        if previous is None or seeking:
            return
        if current + 40 < previous:
            self.audio_clock_regressions += 1
        elif current - previous > 750:
            self.audio_clock_jumps += 1

    def should_render(self, callback_ms: float) -> bool:
        now = float(callback_ms)
        self.callbacks += 1
        if self._last_callback_ms is not None:
            gap = max(0.0, now - self._last_callback_ms)
            callback_interval_ms = 1000.0 / self.quality.render_fps
            missed = max(
                0,
                floor((gap + callback_interval_ms * 0.45) / callback_interval_ms) - 1,
            )
            self.missed_deadlines += missed
            self._missed_history.append(missed)
        else:
            self._missed_history.append(0)
        self._last_callback_ms = now

        desired_interval = 1000.0 / self.quality.render_fps
        if self._last_render_ms is not None and now - self._last_render_ms < desired_interval * 0.5:
            self.adaptive_skips += 1
            return False
        self._last_render_ms = now
        return True

    def record_render(self, duration_ms: float, completed_ms: float) -> None:
        duration = max(0.0, float(duration_ms))
        self.rendered_frames += 1
        self._render_durations.append(duration)
        self._render_timestamps.append(float(completed_ms))
        if self.rendered_frames % 30 == 0:
            self._update_quality()

    def consume_quality_change(self) -> PlaybackQuality | None:
        if not self._quality_changed:
            return None
        self._quality_changed = False
        return self.quality

    def snapshot(self) -> PlaybackDiagnosticsSnapshot:
        durations = list(self._render_durations)
        average = fmean(durations) if durations else 0.0
        ordered = sorted(durations)
        p95_index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95))) if ordered else 0
        p95 = ordered[p95_index] if ordered else 0.0
        maximum = max(ordered, default=0.0)
        displayed_fps = 0.0
        if len(self._render_timestamps) >= 2:
            span_seconds = (self._render_timestamps[-1] - self._render_timestamps[0]) / 1000.0
            if span_seconds > 0.0001:
                displayed_fps = (len(self._render_timestamps) - 1) / span_seconds
        return PlaybackDiagnosticsSnapshot(
            quality=self.quality,
            callbacks=self.callbacks,
            rendered_frames=self.rendered_frames,
            dropped_frames=self.missed_deadlines + self.adaptive_skips,
            missed_deadlines=self.missed_deadlines,
            adaptive_skips=self.adaptive_skips,
            average_render_ms=average,
            p95_render_ms=p95,
            maximum_render_ms=maximum,
            displayed_fps=displayed_fps,
            audio_clock_regressions=self.audio_clock_regressions,
            audio_clock_jumps=self.audio_clock_jumps,
        )

    def _update_quality(self) -> None:
        if not self.adaptive or len(self._render_durations) < 30:
            return
        snapshot = self.snapshot()
        budget = 1000.0 / self.quality.render_fps
        drop_ratio = min(1.0, sum(self._missed_history) / max(1, len(self._missed_history)))
        overloaded = snapshot.average_render_ms > budget * 0.82 or snapshot.p95_render_ms > budget * 1.15
        if overloaded and self.quality < PlaybackQuality.PERFORMANCE:
            self.quality = PlaybackQuality(self.quality + 1)
            self._stable_windows = 0
            self._quality_changed = True
            return
        stable = (
            snapshot.average_render_ms < budget * 0.48
            and snapshot.p95_render_ms < budget * 0.72
            and drop_ratio < 0.04
        )
        self._stable_windows = self._stable_windows + 1 if stable else 0
        if self._stable_windows >= 6 and self.quality > PlaybackQuality.FULL:
            self.quality = PlaybackQuality(self.quality - 1)
            self._stable_windows = 0
            self._quality_changed = True


FrameValue = TypeVar("FrameValue")


class PlaybackFrameCache(Generic[FrameValue]):
    def __init__(self, max_frames: int = 360) -> None:
        self.max_frames = max(16, int(max_frames))
        self._values: OrderedDict[tuple[int, int], FrameValue] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def clear(self) -> None:
        self._values.clear()
        self.hits = 0
        self.misses = 0

    def key(self, set_index: int, count: float, quality: PlaybackQuality) -> tuple[int, int]:
        samples_per_count = {
            PlaybackQuality.FULL: 240,
            PlaybackQuality.BALANCED: 120,
            PlaybackQuality.PERFORMANCE: 60,
        }[quality]
        return int(set_index), int(round(float(count) * samples_per_count))

    def get(self, key: tuple[int, int]) -> FrameValue | None:
        value = self._values.get(key)
        if value is None:
            self.misses += 1
            return None
        self._values.move_to_end(key)
        self.hits += 1
        return value

    def put(self, key: tuple[int, int], value: FrameValue) -> None:
        self._values[key] = value
        self._values.move_to_end(key)
        while len(self._values) > self.max_frames:
            self._values.popitem(last=False)

    def __len__(self) -> int:
        return len(self._values)
