from __future__ import annotations

from math import atan2, cos, pi, sin
from typing import Any

from drill_writer.core.models import DotConstraint


Point = tuple[float, float]


def solve_constraints(
    positions: dict[str, Point],
    constraints: list[DotConstraint],
    *,
    changed_dot_ids: set[str] | None = None,
    fallback_spacing: float = 2.0,
) -> dict[str, Point]:
    solved = dict(positions)
    changed = changed_dot_ids or set(positions)
    for _iteration in range(3):
        for constraint in constraints:
            ids = [dot_id for dot_id in constraint.dot_ids if dot_id in solved]
            if len(ids) < 2 or not changed.intersection(ids):
                continue
            if constraint.constraint_type in {"line", "interval"}:
                apply_line_constraint(solved, ids, constraint.spacing or fallback_spacing)
            elif constraint.constraint_type in {"relative", "pivot"}:
                apply_relative_constraint(solved, ids, constraint.metadata)
            elif constraint.constraint_type == "arc":
                apply_arc_constraint(solved, ids, constraint.metadata)
            elif constraint.constraint_type == "block":
                apply_block_constraint(solved, ids, constraint.metadata, constraint.spacing or fallback_spacing)
    return solved


def apply_line_constraint(positions: dict[str, Point], ids: list[str], spacing: float) -> None:
    points = [positions[dot_id] for dot_id in ids]
    start = points[0]
    end = points[-1]
    vector = (end[0] - start[0], end[1] - start[1])
    length = (vector[0] ** 2 + vector[1] ** 2) ** 0.5
    if length <= 0.001:
        spread_x = max(x for x, _y in points) - min(x for x, _y in points)
        spread_y = max(y for _x, y in points) - min(y for _x, y in points)
        direction = (1.0, 0.0) if spread_x >= spread_y else (0.0, 1.0)
    else:
        direction = (vector[0] / length, vector[1] / length)
    center = center_of(points)
    first_offset = -spacing * (len(ids) - 1) / 2
    for index, dot_id in enumerate(ids):
        positions[dot_id] = (
            center[0] + direction[0] * (first_offset + spacing * index),
            center[1] + direction[1] * (first_offset + spacing * index),
        )


def apply_relative_constraint(positions: dict[str, Point], ids: list[str], metadata: dict[str, Any]) -> None:
    pivot_id = str(metadata.get("pivot_id") or ids[0])
    if pivot_id not in ids or pivot_id not in positions:
        pivot_id = ids[0]
    offsets = normalized_offsets(metadata.get("offsets", {}))
    if not offsets:
        return
    pivot = positions[pivot_id]
    pivot_offset = offsets.get(pivot_id, (0.0, 0.0))
    origin = (pivot[0] - pivot_offset[0], pivot[1] - pivot_offset[1])
    for dot_id in ids:
        offset = offsets.get(dot_id)
        if offset is not None:
            positions[dot_id] = (origin[0] + offset[0], origin[1] + offset[1])


def apply_arc_constraint(positions: dict[str, Point], ids: list[str], metadata: dict[str, Any]) -> None:
    points = [positions[dot_id] for dot_id in ids]
    current_center = center_of(points)
    radius = float(metadata.get("radius") or average_radius(points, current_center) or 4.0)
    start_angle = float(metadata.get("start_angle", 0.0))
    sweep = float(metadata.get("sweep", 360.0 if len(ids) > 2 else 180.0))
    denominator = len(ids) if abs(sweep) >= 359.9 else max(1, len(ids) - 1)
    for index, dot_id in enumerate(ids):
        angle = start_angle + sweep * index / denominator
        radians = angle * pi / 180
        positions[dot_id] = (
            current_center[0] + cos(radians) * radius,
            current_center[1] + sin(radians) * radius,
        )


def apply_block_constraint(
    positions: dict[str, Point],
    ids: list[str],
    metadata: dict[str, Any],
    fallback_spacing: float,
) -> None:
    columns = max(1, int(metadata.get("columns") or round(len(ids) ** 0.5) or 1))
    spacing_x = float(metadata.get("spacing_x") or fallback_spacing)
    spacing_y = float(metadata.get("spacing_y") or fallback_spacing)
    points = [positions[dot_id] for dot_id in ids]
    center = center_of(points)
    rows = (len(ids) + columns - 1) // columns
    for index, dot_id in enumerate(ids):
        row = index // columns
        column = index % columns
        row_count = min(columns, len(ids) - row * columns)
        row_width = (row_count - 1) * spacing_x
        block_height = (rows - 1) * spacing_y
        positions[dot_id] = (
            center[0] - row_width / 2 + column * spacing_x,
            center[1] + block_height / 2 - row * spacing_y,
        )


def make_relative_metadata(
    ids: list[str],
    positions: dict[str, Point],
    *,
    pivot_id: str | None = None,
) -> dict[str, Any]:
    pivot = pivot_id or (ids[0] if ids else "")
    if pivot and pivot in positions:
        origin = positions[pivot]
    else:
        origin = center_of([positions[dot_id] for dot_id in ids])
    return {
        "pivot_id": pivot,
        "offsets": {
            dot_id: {
                "x": positions[dot_id][0] - origin[0],
                "y": positions[dot_id][1] - origin[1],
            }
            for dot_id in ids
            if dot_id in positions
        },
    }


def make_arc_metadata(ids: list[str], positions: dict[str, Point]) -> dict[str, Any]:
    points = [positions[dot_id] for dot_id in ids if dot_id in positions]
    center = center_of(points)
    angles = [atan2(point[1] - center[1], point[0] - center[0]) * 180 / pi for point in points]
    if not angles:
        return {}
    sweep = normalize_sweep(angles[-1] - angles[0])
    if abs(sweep) < 1 and len(ids) > 2:
        sweep = 360.0
    return {
        "radius": average_radius(points, center),
        "start_angle": angles[0],
        "sweep": sweep,
    }


def make_block_metadata(ids: list[str], positions: dict[str, Point], spacing: float) -> dict[str, Any]:
    points = [positions[dot_id] for dot_id in ids if dot_id in positions]
    spread_x = max((x for x, _y in points), default=0.0) - min((x for x, _y in points), default=0.0)
    spread_y = max((y for _x, y in points), default=0.0) - min((y for _x, y in points), default=0.0)
    aspect = max(spread_x, spacing) / max(spread_y, spacing)
    columns = max(1, round((len(ids) * aspect) ** 0.5))
    return {
        "columns": min(len(ids), columns),
        "spacing_x": spacing,
        "spacing_y": spacing,
    }


def normalized_offsets(payload: object) -> dict[str, Point]:
    if not isinstance(payload, dict):
        return {}
    offsets: dict[str, Point] = {}
    for dot_id, value in payload.items():
        if isinstance(value, dict):
            offsets[str(dot_id)] = (float(value.get("x", 0.0)), float(value.get("y", 0.0)))
        elif isinstance(value, (list, tuple)) and len(value) >= 2:
            offsets[str(dot_id)] = (float(value[0]), float(value[1]))
    return offsets


def center_of(points: list[Point]) -> Point:
    if not points:
        return (0.0, 0.0)
    return (
        sum(x for x, _y in points) / len(points),
        sum(y for _x, y in points) / len(points),
    )


def average_radius(points: list[Point], center: Point) -> float:
    if not points:
        return 0.0
    return sum(((x - center[0]) ** 2 + (y - center[1]) ** 2) ** 0.5 for x, y in points) / len(points)


def normalize_sweep(value: float) -> float:
    while value <= -180:
        value += 360
    while value > 180:
        value -= 360
    return value
