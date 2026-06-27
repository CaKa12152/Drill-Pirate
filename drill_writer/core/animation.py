from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi

from drill_writer.core.models import DrillProject, Transition


@dataclass(slots=True)
class PlaybackPosition:
    set_index: int
    count: float
    progress: float


def ease(progress: float, transition: Transition) -> float:
    progress = max(0.0, min(1.0, progress))
    if transition == Transition.EASE_IN_OUT:
        return 0.5 - 0.5 * cos(pi * progress)
    if transition == Transition.CURVED:
        return progress * progress * (3 - 2 * progress)
    return progress


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5


def catmull_rom_point(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    t2 = t * t
    t3 = t2 * t
    return (
        0.5
        * (
            (2 * p1[0])
            + (-p0[0] + p2[0]) * t
            + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
            + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
        ),
        0.5
        * (
            (2 * p1[1])
            + (-p0[1] + p2[1]) * t
            + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
            + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
        ),
    )


def sample_waypoint_path(
    waypoints: list[tuple[float, float]],
    samples_per_segment: int = 16,
) -> list[tuple[float, float]]:
    if len(waypoints) <= 1:
        return waypoints
    if len(waypoints) == 2:
        return [
            (
                waypoints[0][0] + (waypoints[1][0] - waypoints[0][0]) * index / samples_per_segment,
                waypoints[0][1] + (waypoints[1][1] - waypoints[0][1]) * index / samples_per_segment,
            )
            for index in range(samples_per_segment + 1)
        ]

    sampled: list[tuple[float, float]] = []
    padded = [waypoints[0], *waypoints, waypoints[-1]]
    for index in range(1, len(padded) - 2):
        for sample_index in range(samples_per_segment):
            sampled.append(
                catmull_rom_point(
                    padded[index - 1],
                    padded[index],
                    padded[index + 1],
                    padded[index + 2],
                    sample_index / samples_per_segment,
                )
            )
    sampled.append(waypoints[-1])
    return sampled


def point_on_polyline(points: list[tuple[float, float]], progress: float) -> tuple[float, float]:
    if not points:
        return (0, 0)
    if len(points) == 1:
        return points[0]

    progress = max(0.0, min(1.0, progress))
    segment_lengths = [
        distance(points[index], points[index + 1])
        for index in range(len(points) - 1)
    ]
    total_length = sum(segment_lengths)
    if total_length == 0:
        return points[0]

    target_distance = total_length * progress
    traveled = 0.0
    for index, segment_length in enumerate(segment_lengths):
        if traveled + segment_length >= target_distance or index == len(segment_lengths) - 1:
            local_t = (target_distance - traveled) / (segment_length or 1)
            start = points[index]
            end = points[index + 1]
            return (
                start[0] + (end[0] - start[0]) * local_t,
                start[1] + (end[1] - start[1]) * local_t,
            )
        traveled += segment_length
    return points[-1]


def transition_position(
    start: tuple[float, float],
    end: tuple[float, float],
    anchors: list[tuple[float, float]],
    progress: float,
) -> tuple[float, float]:
    if anchors:
        return point_on_polyline(sample_waypoint_path([start, *anchors, end]), progress)
    return (
        start[0] + (end[0] - start[0]) * progress,
        start[1] + (end[1] - start[1]) * progress,
    )


def sample_transition_path(
    start: tuple[float, float],
    end: tuple[float, float],
    anchors: list[tuple[float, float]],
    samples: int = 32,
) -> list[tuple[float, float]]:
    if anchors:
        return sample_waypoint_path([start, *anchors, end], max(2, samples // max(1, len(anchors) + 1)))
    return [
        transition_position(start, end, [], index / max(1, samples - 1))
        for index in range(samples)
    ]


def interpolate_project(project: DrillProject, set_index: int, count: float) -> dict[str, tuple[float, float]]:
    if not project.sets:
        return {dot.id: (dot.x, dot.y) for dot in project.dots}

    current = project.sets[max(0, min(set_index, len(project.sets) - 1))]
    previous = project.sets[set_index - 1] if set_index > 0 else current
    movement_counts = max(1, current.end_count - current.start_count)
    progress = (count - current.start_count) / movement_counts
    eased = ease(progress, current.transition)

    positions: dict[str, tuple[float, float]] = {}
    for dot in project.dots:
        start = previous.dot_positions.get(dot.id, (dot.x, dot.y))
        end = current.dot_positions.get(dot.id, (dot.x, dot.y))
        positions[dot.id] = transition_position(
            start,
            end,
            current.path_anchors.get(dot.id, []),
            eased,
        )
    return positions
