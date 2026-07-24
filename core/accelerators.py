from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, pi, radians, sin
from typing import Iterable
from uuid import uuid4

from drill_writer.core.assignment import minimum_cost_target_assignment
from drill_writer.core.cad_paths import cad_offset
from drill_writer.core.tools import positions_along_path


Point = tuple[float, float]


@dataclass(slots=True)
class ArrayOptions:
    mode: str = "linear"
    copies: int = 2
    columns: int = 2
    spacing_x: float = 12.0
    spacing_y: float = 8.0
    angle_degrees: float = 0.0
    radius: float = 18.0
    sweep_degrees: float = 360.0
    rotate_copies: bool = True


@dataclass(slots=True)
class ParallelFormOptions:
    ranks: int = 2
    interval: float = 2.0
    placement: str = "centered"
    closed: bool = False


def assign_targets_minimum_cost(
    dot_ids: list[str],
    starts: dict[str, Point],
    targets: list[Point],
) -> dict[str, Point]:
    usable_ids = [dot_id for dot_id in dot_ids if dot_id in starts]
    if len(usable_ids) != len(targets):
        raise ValueError("The target form must contain exactly one spot per selected marcher.")
    if not usable_ids:
        return {}
    assignment = minimum_cost_target_assignment([starts[dot_id] for dot_id in usable_ids], targets)
    return {
        dot_id: targets[target_index]
        for dot_id, target_index in zip(usable_ids, assignment)
    }


def array_target_points(
    source_points: list[Point],
    total_count: int,
    options: ArrayOptions,
    path: list[Point] | None = None,
) -> list[Point]:
    copies = max(1, min(int(options.copies), max(1, total_count)))
    if total_count < copies or total_count % copies:
        raise ValueError(
            f"Select a marcher count divisible by {copies}; each repeated form needs the same number of performers."
        )
    motif_count = total_count // copies
    if len(source_points) < motif_count:
        raise ValueError("Not enough source points are available to build the master form.")
    motif = spatial_path_order(source_points[:motif_count], closed=False)
    motif_center = points_center(motif)
    local = [(x - motif_center[0], y - motif_center[1]) for x, y in motif]
    overall_center = points_center(source_points)
    mode = options.mode.strip().lower()
    centers: list[Point] = []
    rotations: list[float] = []

    if mode == "polar":
        sweep = float(options.sweep_degrees)
        closed_sweep = abs(abs(sweep) - 360.0) < 0.001
        denominator = copies if closed_sweep else max(1, copies - 1)
        for copy_index in range(copies):
            angle = radians(float(options.angle_degrees) + sweep * copy_index / denominator)
            centers.append(
                (
                    overall_center[0] + cos(angle) * max(0.0, float(options.radius)),
                    overall_center[1] + sin(angle) * max(0.0, float(options.radius)),
                )
            )
            rotations.append(angle if options.rotate_copies else 0.0)
    elif mode == "rows":
        columns = max(1, min(int(options.columns), copies))
        rows = (copies + columns - 1) // columns
        for copy_index in range(copies):
            column = copy_index % columns
            row = copy_index // columns
            centers.append(
                (
                    overall_center[0] + (column - (columns - 1) / 2) * float(options.spacing_x),
                    overall_center[1] - (row - (rows - 1) / 2) * float(options.spacing_y),
                )
            )
            rotations.append(0.0)
    elif mode == "path":
        if not path or len(path) < 2:
            raise ValueError("Path arrays require a selected construction guide with at least two points.")
        centers = positions_along_path(path, copies)
        for index, center in enumerate(centers):
            if not options.rotate_copies:
                rotations.append(0.0)
                continue
            before = centers[max(0, index - 1)]
            after = centers[min(len(centers) - 1, index + 1)]
            rotations.append(atan2(after[1] - before[1], after[0] - before[0]))
    else:
        angle = radians(float(options.angle_degrees))
        direction = (cos(angle), sin(angle))
        spacing = float(options.spacing_x)
        for copy_index in range(copies):
            offset = (copy_index - (copies - 1) / 2) * spacing
            centers.append(
                (
                    overall_center[0] + direction[0] * offset,
                    overall_center[1] + direction[1] * offset,
                )
            )
            rotations.append(angle if options.rotate_copies else 0.0)

    targets: list[Point] = []
    for center, rotation in zip(centers, rotations):
        cosine = cos(rotation)
        sine = sin(rotation)
        for local_x, local_y in local:
            targets.append(
                (
                    center[0] + local_x * cosine - local_y * sine,
                    center[1] + local_x * sine + local_y * cosine,
                )
            )
    return targets


def parallel_form_target_points(
    master_path: list[Point],
    total_count: int,
    options: ParallelFormOptions,
) -> list[Point]:
    ranks = max(1, min(int(options.ranks), max(1, total_count)))
    if len(master_path) < 2:
        raise ValueError("Draw or select a master path with at least two points.")
    counts = balanced_counts(total_count, ranks)
    path = spatial_path_order(master_path, closed=options.closed)
    if options.closed and path[0] == path[-1]:
        path = path[:-1]
    targets: list[Point] = []
    for rank_index, marcher_count in enumerate(counts):
        distance = parallel_offset(rank_index, ranks, options.interval, options.placement)
        if options.closed:
            distance *= closed_outward_sign(path)
        offset_path = cad_offset(path, distance, closed=options.closed)
        if options.closed and offset_path and offset_path[0] != offset_path[-1]:
            offset_path = [*offset_path, offset_path[0]]
        targets.extend(positions_along_path(offset_path, marcher_count))
    return targets


def rank_file_target_points(
    master_path: list[Point],
    total_count: int,
    ranks: int,
    interval: float,
    centered: bool = True,
    closed: bool = False,
) -> list[Point]:
    return parallel_form_target_points(
        master_path,
        total_count,
        ParallelFormOptions(
            ranks=ranks,
            interval=interval,
            placement="centered" if centered else "outward",
            closed=closed,
        ),
    )


def create_live_symmetry_record(
    dot_ids: Iterable[str],
    positions: dict[str, Point],
    axis_point: Point = (0.0, 0.0),
    axis_angle_degrees: float = 90.0,
    tolerance: float = 0.3,
    name: str = "Live Symmetry",
) -> dict:
    selected = [dot_id for dot_id in dot_ids if dot_id in positions]
    if len(selected) < 2:
        raise ValueError("Select at least two marchers to create live symmetry.")
    positive: list[str] = []
    negative: list[str] = []
    center_ids: list[str] = []
    for dot_id in selected:
        side = signed_axis_distance(positions[dot_id], axis_point, axis_angle_degrees)
        if abs(side) <= max(0.01, tolerance):
            center_ids.append(dot_id)
        elif side > 0:
            positive.append(dot_id)
        else:
            negative.append(dot_id)
    if len(positive) != len(negative):
        raise ValueError(
            "Live symmetry needs matching marcher counts on both sides of the axis; marchers on the axis are allowed."
        )
    reflected = [reflect_point(positions[dot_id], axis_point, axis_angle_degrees) for dot_id in positive]
    target_points = [positions[dot_id] for dot_id in negative]
    assignment = minimum_cost_target_assignment(reflected, target_points) if positive else []
    pairs = [[positive[index], negative[target_index]] for index, target_index in enumerate(assignment)]
    return {
        "id": f"symmetry-{uuid4().hex[:10]}",
        "name": name.strip() or "Live Symmetry",
        "axis_point": [float(axis_point[0]), float(axis_point[1])],
        "axis_angle": float(axis_angle_degrees),
        "pairs": pairs,
        "center_ids": center_ids,
        "enabled": True,
    }


def expand_live_symmetry_changes(
    records: Iterable[dict],
    before: dict[str, Point],
    proposed: dict[str, Point],
    locked_ids: Iterable[str] = (),
) -> dict[str, Point]:
    expanded = dict(proposed)
    explicit = set(proposed)
    locked = set(locked_ids)
    for record in records:
        if not bool(record.get("enabled", True)):
            continue
        axis_values = record.get("axis_point", [0.0, 0.0])
        axis_point = (float(axis_values[0]), float(axis_values[1]))
        axis_angle = float(record.get("axis_angle", 90.0))
        for pair in record.get("pairs", []):
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            first, second = str(pair[0]), str(pair[1])
            if first in explicit and second in explicit:
                first_move = point_distance(before.get(first, proposed[first]), proposed[first])
                second_move = point_distance(before.get(second, proposed[second]), proposed[second])
                if second_move > first_move + 0.0001 and first not in locked:
                    expanded[first] = reflect_point(proposed[second], axis_point, axis_angle)
                elif second not in locked:
                    expanded[second] = reflect_point(proposed[first], axis_point, axis_angle)
            elif first in explicit and second not in explicit and second not in locked:
                expanded[second] = reflect_point(proposed[first], axis_point, axis_angle)
            elif second in explicit and first not in explicit and first not in locked:
                expanded[first] = reflect_point(proposed[second], axis_point, axis_angle)
        for dot_id in record.get("center_ids", []):
            dot_id = str(dot_id)
            if dot_id in explicit and dot_id not in locked:
                expanded[dot_id] = project_point_to_axis(proposed[dot_id], axis_point, axis_angle)
    return expanded


def alternating_selection(
    dot_ids: list[str],
    positions: dict[str, Point],
    mode: str,
    every: int = 2,
    ranks: dict[str, str] | None = None,
    count: int = 4,
    anchor: Point | None = None,
) -> list[str]:
    available = [dot_id for dot_id in dot_ids if dot_id in positions]
    if not available:
        return []
    normalized = mode.strip().lower()
    ordered = spatial_id_order(available, positions)
    if normalized in {"every", "alternate"}:
        step = max(2, int(every))
        return ordered[::step]
    if normalized in {"odd_ranks", "even_ranks"}:
        rank_values = ranks or {}
        rank_names = sorted({str(rank_values.get(dot_id, "")).strip() for dot_id in available if str(rank_values.get(dot_id, "")).strip()}, key=natural_rank_key)
        parity = 0 if normalized == "odd_ranks" else 1
        selected_ranks = {name for index, name in enumerate(rank_names) if index % 2 == parity}
        return [dot_id for dot_id in available if str(rank_values.get(dot_id, "")).strip() in selected_ranks]
    if normalized == "endpoints":
        return [ordered[0]] if len(ordered) == 1 else [ordered[0], ordered[-1]]
    if normalized == "corners":
        hull = convex_hull([(positions[dot_id], dot_id) for dot_id in available])
        if len(hull) <= max(1, count):
            return [dot_id for _point, dot_id in hull]
        scored: list[tuple[float, str]] = []
        for index, (point, dot_id) in enumerate(hull):
            before_point = hull[index - 1][0]
            after_point = hull[(index + 1) % len(hull)][0]
            first_angle = atan2(before_point[1] - point[1], before_point[0] - point[0])
            second_angle = atan2(after_point[1] - point[1], after_point[0] - point[0])
            turn = abs(normalize_angle(second_angle - first_angle))
            scored.append((abs(pi - turn), dot_id))
        return [dot_id for _score, dot_id in sorted(scored, reverse=True)[: max(1, count)]]
    if normalized == "nearest":
        origin = anchor or points_center([positions[dot_id] for dot_id in available])
        return sorted(available, key=lambda dot_id: point_distance(positions[dot_id], origin))[: max(1, count)]
    return ordered


def spatial_id_order(dot_ids: list[str], positions: dict[str, Point], closed: bool = False) -> list[str]:
    ordered_points = spatial_path_order([(positions[dot_id][0], positions[dot_id][1], dot_id) for dot_id in dot_ids], closed=closed)
    return [str(point[2]) for point in ordered_points]


def spatial_path_order(points: list, closed: bool = False) -> list:
    if len(points) < 3:
        return list(points)
    point_xy = lambda point: (float(point[0]), float(point[1]))
    if closed:
        center = points_center([point_xy(point) for point in points])
        return sorted(points, key=lambda point: atan2(point_xy(point)[1] - center[1], point_xy(point)[0] - center[0]))
    spread_x = max(point_xy(point)[0] for point in points) - min(point_xy(point)[0] for point in points)
    spread_y = max(point_xy(point)[1] for point in points) - min(point_xy(point)[1] for point in points)
    remaining = list(points)
    current = min(remaining, key=lambda point: (point_xy(point)[0], point_xy(point)[1]) if spread_x >= spread_y else (point_xy(point)[1], point_xy(point)[0]))
    ordered = [current]
    remaining.remove(current)
    while remaining:
        current_xy = point_xy(current)
        current = min(remaining, key=lambda point: point_distance(current_xy, point_xy(point)))
        ordered.append(current)
        remaining.remove(current)
    return ordered


def balanced_counts(total: int, groups: int) -> list[int]:
    groups = max(1, min(groups, max(1, total)))
    base, remainder = divmod(total, groups)
    return [base + (1 if index < remainder else 0) for index in range(groups)]


def parallel_offset(index: int, count: int, interval: float, placement: str) -> float:
    spacing = max(0.01, float(interval))
    normalized = placement.strip().lower()
    if normalized == "outward":
        return index * spacing
    if normalized == "inward":
        return -index * spacing
    return (index - (count - 1) / 2) * spacing


def closed_outward_sign(path: list[Point]) -> float:
    area = 0.0
    for first, second in zip(path, [*path[1:], path[0]]):
        area += first[0] * second[1] - second[0] * first[1]
    return -1.0 if area > 0 else 1.0


def reflect_point(point: Point, axis_point: Point, axis_angle_degrees: float) -> Point:
    angle = radians(axis_angle_degrees)
    direction = (cos(angle), sin(angle))
    relative = (point[0] - axis_point[0], point[1] - axis_point[1])
    parallel = relative[0] * direction[0] + relative[1] * direction[1]
    projection = (axis_point[0] + parallel * direction[0], axis_point[1] + parallel * direction[1])
    return (projection[0] * 2 - point[0], projection[1] * 2 - point[1])


def project_point_to_axis(point: Point, axis_point: Point, axis_angle_degrees: float) -> Point:
    angle = radians(axis_angle_degrees)
    direction = (cos(angle), sin(angle))
    relative = (point[0] - axis_point[0], point[1] - axis_point[1])
    parallel = relative[0] * direction[0] + relative[1] * direction[1]
    return (axis_point[0] + parallel * direction[0], axis_point[1] + parallel * direction[1])


def signed_axis_distance(point: Point, axis_point: Point, axis_angle_degrees: float) -> float:
    angle = radians(axis_angle_degrees)
    direction = (cos(angle), sin(angle))
    relative = (point[0] - axis_point[0], point[1] - axis_point[1])
    return direction[0] * relative[1] - direction[1] * relative[0]


def points_center(points: Iterable[Point]) -> Point:
    values = list(points)
    if not values:
        return (0.0, 0.0)
    return (
        sum(point[0] for point in values) / len(values),
        sum(point[1] for point in values) / len(values),
    )


def point_distance(first: Point, second: Point) -> float:
    return hypot(second[0] - first[0], second[1] - first[1])


def normalize_angle(value: float) -> float:
    while value <= -pi:
        value += 2 * pi
    while value > pi:
        value -= 2 * pi
    return value


def natural_rank_key(value: str) -> tuple:
    number = "".join(character for character in value if character.isdigit())
    prefix = value[: value.find(number)] if number else value
    return (prefix.casefold(), int(number) if number else 0, value.casefold())


def convex_hull(points: list[tuple[Point, str]]) -> list[tuple[Point, str]]:
    unique = sorted({(point[0], point[1], dot_id) for point, dot_id in points})
    if len(unique) <= 2:
        return [((x, y), dot_id) for x, y, dot_id in unique]

    def cross(origin, first, second) -> float:
        return (first[0] - origin[0]) * (second[1] - origin[1]) - (first[1] - origin[1]) * (second[0] - origin[0])

    lower = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return [((x, y), dot_id) for x, y, dot_id in [*lower[:-1], *upper[:-1]]]


def describe_measurements(
    points: list[Point],
    path_lengths: Iterable[float] = (),
    duration_counts: float = 0.0,
) -> dict[str, float]:
    ordered = spatial_path_order(points, closed=False)
    intervals = [point_distance(first, second) for first, second in zip(ordered, ordered[1:])]
    center = points_center(points)
    radii = [point_distance(center, point) for point in points]
    angle = 0.0
    if len(ordered) >= 2:
        angle = degrees(atan2(ordered[-1][1] - ordered[0][1], ordered[-1][0] - ordered[0][0]))
    travel = list(path_lengths)
    return {
        "minimum_interval_yards": min(intervals, default=0.0),
        "average_interval_yards": sum(intervals) / len(intervals) if intervals else 0.0,
        "total_form_length_yards": sum(intervals),
        "angle_degrees": angle,
        "average_radius_yards": sum(radii) / len(radii) if radii else 0.0,
        "maximum_travel_yards": max(travel, default=0.0),
        "maximum_yards_per_count": max(travel, default=0.0) / max(0.001, duration_counts),
    }
