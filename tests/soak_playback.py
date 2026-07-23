from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from drill_writer.core.animation import interpolate_dot_facings, interpolate_project, interpolate_props
from drill_writer.core.timing import audio_ms_to_count, count_to_audio_ms
from reliability_fixtures import playback_project


@dataclass(slots=True)
class SoakResult:
    performers: int
    frames: int
    elapsed_seconds: float
    average_frame_ms: float
    maximum_frame_ms: float


def exercise_playback_frames(performers: int, frames: int) -> SoakResult:
    project = playback_project(performers)
    samples_per_set = max(2, frames // max(1, len(project.sets)))
    completed = 0
    maximum_frame_seconds = 0.0
    started = time.perf_counter()
    for frame in range(frames):
        set_index = (frame // samples_per_set) % len(project.sets)
        drill_set = project.sets[set_index]
        local_frame = frame % samples_per_set
        progress = local_frame / max(1, samples_per_set - 1)
        count = drill_set.start_count + progress * (drill_set.end_count - drill_set.start_count)
        frame_started = time.perf_counter()
        positions = interpolate_project(project, set_index, count)
        facings = interpolate_dot_facings(project, set_index, count)
        props = interpolate_props(project, set_index, count)
        round_trip_count = audio_ms_to_count(project, count_to_audio_ms(project, count))
        maximum_frame_seconds = max(maximum_frame_seconds, time.perf_counter() - frame_started)
        if len(positions) != performers or len(facings) != performers:
            raise AssertionError(f"Frame {frame} returned an incomplete performer map.")
        if props:
            raise AssertionError("The playback soak fixture unexpectedly returned props.")
        if not all(math.isfinite(value) for point in positions.values() for value in point):
            raise AssertionError(f"Frame {frame} produced a non-finite coordinate.")
        if abs(round_trip_count - count) > 0.03:
            raise AssertionError(
                f"Audio/count round trip drifted by {abs(round_trip_count - count):.4f} counts."
            )
        completed += 1
    elapsed = time.perf_counter() - started
    return SoakResult(
        performers=performers,
        frames=completed,
        elapsed_seconds=elapsed,
        average_frame_ms=(elapsed / max(1, completed)) * 1000.0,
        maximum_frame_ms=maximum_frame_seconds * 1000.0,
    )


def run_timed_soak(performers: int, minutes: float) -> SoakResult:
    deadline = time.monotonic() + max(0.01, minutes) * 60.0
    total_frames = 0
    total_elapsed = 0.0
    maximum_frame_ms = 0.0
    while time.monotonic() < deadline:
        result = exercise_playback_frames(performers, 360)
        total_frames += result.frames
        total_elapsed += result.elapsed_seconds
        maximum_frame_ms = max(maximum_frame_ms, result.maximum_frame_ms)
    return SoakResult(
        performers=performers,
        frames=total_frames,
        elapsed_seconds=total_elapsed,
        average_frame_ms=(total_elapsed / max(1, total_frames)) * 1000.0,
        maximum_frame_ms=maximum_frame_ms,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Long-running Drill Pirate playback reliability soak.")
    parser.add_argument("--minutes", type=float, default=5.0, help="Minutes to run for each performer size.")
    parser.add_argument(
        "--performers",
        type=int,
        nargs="*",
        default=[200, 300, 400, 500],
        help="Performer counts to test.",
    )
    parser.add_argument(
        "--max-average-frame-ms",
        type=float,
        default=0.0,
        help="Optional average-frame failure threshold; zero records performance without enforcing it.",
    )
    args = parser.parse_args()
    failed = False
    for performer_count in args.performers:
        result = run_timed_soak(performer_count, args.minutes)
        print(
            f"{result.performers:>3} performers | {result.frames:>8} frames | "
            f"avg {result.average_frame_ms:>7.3f} ms | max {result.maximum_frame_ms:>7.3f} ms"
        )
        if args.max_average_frame_ms > 0 and result.average_frame_ms > args.max_average_frame_ms:
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
