from __future__ import annotations

from math import cos, pi, radians, sin
from random import Random


def line_positions(count: int, start: tuple[float, float], end: tuple[float, float]) -> list[tuple[float, float]]:
    if count <= 1:
        return [start]
    return [
        (
            start[0] + (end[0] - start[0]) * index / (count - 1),
            start[1] + (end[1] - start[1]) * index / (count - 1),
        )
        for index in range(count)
    ]


def arc_positions(
    count: int,
    center: tuple[float, float],
    radius: float,
    start_degrees: float,
    sweep_degrees: float,
) -> list[tuple[float, float]]:
    if count <= 1:
        return [(center[0] + radius, center[1])]
    return [
        (
            center[0] + cos((start_degrees + sweep_degrees * index / (count - 1)) * pi / 180) * radius,
            center[1] + sin((start_degrees + sweep_degrees * index / (count - 1)) * pi / 180) * radius,
        )
        for index in range(count)
    ]


def curve_positions(
    positions: list[tuple[float, float]],
    control: tuple[float, float],
    strength: float = 0.5,
) -> list[tuple[float, float]]:
    if len(positions) <= 2:
        return positions
    start = positions[0]
    end = positions[-1]
    curved: list[tuple[float, float]] = []
    for index, _position in enumerate(positions):
        t = index / (len(positions) - 1)
        base_x = (1 - t) * start[0] + t * end[0]
        base_y = (1 - t) * start[1] + t * end[1]
        bezier_x = (1 - t) ** 2 * start[0] + 2 * (1 - t) * t * control[0] + t**2 * end[0]
        bezier_y = (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * control[1] + t**2 * end[1]
        curved.append((base_x + (bezier_x - base_x) * strength, base_y + (bezier_y - base_y) * strength))
    return curved


def scatter_positions(
    positions: list[tuple[float, float]],
    radius: float,
    seed: int = 42,
) -> list[tuple[float, float]]:
    random = Random(seed)
    scattered: list[tuple[float, float]] = []
    for x, y in positions:
        angle = random.random() * 2 * pi
        distance = random.random() * radius
        scattered.append((x + cos(angle) * distance, y + sin(angle) * distance))
    return scattered


def mirror_positions(
    positions: list[tuple[float, float]],
    axis: str,
    origin: float = 0,
) -> list[tuple[float, float]]:
    if axis == "horizontal":
        return [(x, origin - (y - origin)) for x, y in positions]
    return [(origin - (x - origin), y) for x, y in positions]


def rotate_positions(
    positions: list[tuple[float, float]],
    degrees: float,
    center: tuple[float, float] | None = None,
) -> list[tuple[float, float]]:
    if not positions:
        return []
    pivot = center or (
        sum(x for x, _y in positions) / len(positions),
        sum(y for _x, y in positions) / len(positions),
    )
    angle = radians(degrees)
    rotated: list[tuple[float, float]] = []
    for x, y in positions:
        offset_x = x - pivot[0]
        offset_y = y - pivot[1]
        rotated.append(
            (
                pivot[0] + offset_x * cos(angle) - offset_y * sin(angle),
                pivot[1] + offset_x * sin(angle) + offset_y * cos(angle),
            )
        )
    return rotated


def centered_positions(
    positions: list[tuple[float, float]],
    target: tuple[float, float] = (0, 0),
) -> list[tuple[float, float]]:
    if not positions:
        return []
    center = (
        sum(x for x, _y in positions) / len(positions),
        sum(y for _x, y in positions) / len(positions),
    )
    offset_x = target[0] - center[0]
    offset_y = target[1] - center[1]
    return [(x + offset_x, y + offset_y) for x, y in positions]


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


def sampled_shape_path(
    anchors: list[tuple[float, float]],
    curved: bool,
    samples_per_segment: int = 16,
) -> list[tuple[float, float]]:
    if len(anchors) <= 1:
        return anchors
    if not curved:
        samples: list[tuple[float, float]] = []
        for index in range(len(anchors) - 1):
            segment = line_positions(samples_per_segment, anchors[index], anchors[index + 1])
            samples.extend(segment if index == 0 else segment[1:])
        return samples

    samples = []
    padded = [anchors[0], *anchors, anchors[-1]]
    for index in range(1, len(padded) - 2):
        for sample_index in range(samples_per_segment):
            samples.append(
                catmull_rom_point(
                    padded[index - 1],
                    padded[index],
                    padded[index + 1],
                    padded[index + 2],
                    sample_index / samples_per_segment,
                )
            )
    samples.append(anchors[-1])
    return samples


def positions_along_path(
    path: list[tuple[float, float]],
    count: int,
) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    if len(path) <= 1:
        return path * count
    if count == 1:
        return [path[0]]

    segment_lengths = [
        distance(path[index], path[index + 1])
        for index in range(len(path) - 1)
    ]
    total_length = sum(segment_lengths)
    if total_length == 0:
        return [path[0] for _ in range(count)]

    placed: list[tuple[float, float]] = []
    segment_index = 0
    distance_before_segment = 0.0
    for slot_index in range(count):
        target_distance = total_length * slot_index / (count - 1)
        while (
            segment_index < len(segment_lengths) - 1
            and distance_before_segment + segment_lengths[segment_index] < target_distance
        ):
            distance_before_segment += segment_lengths[segment_index]
            segment_index += 1
        segment_length = segment_lengths[segment_index] or 1
        local_t = (target_distance - distance_before_segment) / segment_length
        start = path[segment_index]
        end = path[segment_index + 1]
        placed.append(
            (
                start[0] + (end[0] - start[0]) * local_t,
                start[1] + (end[1] - start[1]) * local_t,
            )
        )
    return placed
