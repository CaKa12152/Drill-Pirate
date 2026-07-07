from __future__ import annotations

from dataclasses import dataclass

from drill_writer.core.animation import distance, interpolate_project, sample_transition_path
from drill_writer.core.models import DrillProject


@dataclass(slots=True)
class PathWarning:
    severity: str
    set_index: int
    set_name: str
    message: str
    dot_a: str = ""
    dot_b: str = ""
    count: float = 0.0


@dataclass(slots=True)
class ConflictTimelineEntry:
    set_index: int
    set_name: str
    count: float
    spacing_conflicts: int = 0
    speed_conflicts: int = 0
    crossing_conflicts: int = 0
    worst_spacing: float = 999.0
    fastest_yards_per_count: float = 0.0

    @property
    def total(self) -> int:
        return self.spacing_conflicts + self.speed_conflicts + self.crossing_conflicts


def detect_path_warnings(
    project: DrillProject,
    set_index: int,
    min_spacing: float = 1.25,
    max_yards_per_count: float = 4.0,
    samples: int = 24,
    dot_ids: list[str] | None = None,
    warning_limit: int = 500,
) -> list[PathWarning]:
    if not project.sets or not 0 <= set_index < len(project.sets):
        return []

    drill_set = project.sets[set_index]
    warnings: list[PathWarning] = []
    all_dot_ids = [dot.id for dot in project.dots]
    selected_dot_ids = set(dot_ids or all_dot_ids)
    sampled_counts = [
        drill_set.start_count
        + (drill_set.end_count - drill_set.start_count) * sample_index / max(1, samples - 1)
        for sample_index in range(samples)
    ]
    sampled_positions = [interpolate_project(project, set_index, count) for count in sampled_counts]

    for first_index, dot_a in enumerate(all_dot_ids):
        for dot_b in all_dot_ids[first_index + 1 :]:
            if dot_a not in selected_dot_ids and dot_b not in selected_dot_ids:
                continue
            closest_distance = float("inf")
            closest_count = drill_set.start_count
            for count, positions in zip(sampled_counts, sampled_positions):
                current_distance = distance(positions[dot_a], positions[dot_b])
                if current_distance < closest_distance:
                    closest_distance = current_distance
                    closest_count = count
            if closest_distance < min_spacing:
                warnings.append(
                    PathWarning(
                        "spacing",
                        set_index,
                        drill_set.name,
                        f"{dot_a} and {dot_b} get within {closest_distance:.2f} yd",
                        dot_a,
                        dot_b,
                        closest_count,
                    )
                )
                if len(warnings) >= warning_limit:
                    return warnings

    if set_index > 0:
        previous = project.sets[set_index - 1]
        path_by_dot = {
            dot_id: sample_transition_path(
                previous.dot_positions.get(dot_id, project.dot_by_id(dot_id) and (project.dot_by_id(dot_id).x, project.dot_by_id(dot_id).y) or (0, 0)),
                drill_set.dot_positions.get(dot_id, project.dot_by_id(dot_id) and (project.dot_by_id(dot_id).x, project.dot_by_id(dot_id).y) or (0, 0)),
                drill_set.path_anchors.get(dot_id, []),
                drill_set.path_controls.get(dot_id, []),
                samples=12,
            )
            for dot_id in all_dot_ids
        }

        check_crossings = len(all_dot_ids) <= 450 or dot_ids is not None
        if check_crossings:
            for first_index, dot_a in enumerate(all_dot_ids):
                for dot_b in all_dot_ids[first_index + 1 :]:
                    if dot_a not in selected_dot_ids and dot_b not in selected_dot_ids:
                        continue
                    if polylines_cross(path_by_dot[dot_a], path_by_dot[dot_b]):
                        warnings.append(
                            PathWarning(
                                "crossing",
                                set_index,
                                drill_set.name,
                                f"{dot_a} path crosses {dot_b}",
                                dot_a,
                                dot_b,
                                drill_set.start_count,
                            )
                        )
                        if len(warnings) >= warning_limit:
                            return warnings

        for dot_id in all_dot_ids:
            if dot_id not in selected_dot_ids:
                continue
            path = path_by_dot[dot_id]
            length = sum(distance(path[index], path[index + 1]) for index in range(len(path) - 1))
            yards_per_count = length / max(1, drill_set.duration_counts)
            if yards_per_count > max_yards_per_count:
                warnings.append(
                    PathWarning(
                        "speed",
                        set_index,
                        drill_set.name,
                        f"{dot_id} travels {yards_per_count:.2f} yd/count (stride/speed risk)",
                        dot_id,
                        "",
                        drill_set.start_count,
                    )
                )
                if len(warnings) >= warning_limit:
                    return warnings

    return warnings


def build_conflict_timeline(
    project: DrillProject,
    set_index: int,
    min_spacing: float = 1.25,
    max_yards_per_count: float = 4.0,
    samples: int = 24,
    dot_ids: list[str] | None = None,
) -> list[ConflictTimelineEntry]:
    if not project.sets or not 0 <= set_index < len(project.sets):
        return []
    drill_set = project.sets[set_index]
    all_dot_ids = [dot.id for dot in project.dots]
    selected_dot_ids = set(dot_ids or all_dot_ids)
    sampled_counts = [
        drill_set.start_count
        + (drill_set.end_count - drill_set.start_count) * sample_index / max(1, samples - 1)
        for sample_index in range(samples)
    ]
    sampled_positions = [interpolate_project(project, set_index, count) for count in sampled_counts]
    entries = [
        ConflictTimelineEntry(set_index=set_index, set_name=drill_set.name, count=count)
        for count in sampled_counts
    ]

    for sample_index, positions in enumerate(sampled_positions):
        entry = entries[sample_index]
        for first_index, dot_a in enumerate(all_dot_ids):
            for dot_b in all_dot_ids[first_index + 1 :]:
                if dot_a not in selected_dot_ids and dot_b not in selected_dot_ids:
                    continue
                current_distance = distance(positions[dot_a], positions[dot_b])
                entry.worst_spacing = min(entry.worst_spacing, current_distance)
                if current_distance < min_spacing:
                    entry.spacing_conflicts += 1

    for sample_index in range(1, len(sampled_positions)):
        previous_count = sampled_counts[sample_index - 1]
        current_count = sampled_counts[sample_index]
        count_span = max(0.0001, current_count - previous_count)
        entry = entries[sample_index]
        previous_positions = sampled_positions[sample_index - 1]
        current_positions = sampled_positions[sample_index]
        for dot_id in all_dot_ids:
            if dot_id not in selected_dot_ids:
                continue
            yards_per_count = distance(previous_positions[dot_id], current_positions[dot_id]) / count_span
            entry.fastest_yards_per_count = max(entry.fastest_yards_per_count, yards_per_count)
            if yards_per_count > max_yards_per_count:
                entry.speed_conflicts += 1

    if set_index > 0 and (len(all_dot_ids) <= 450 or dot_ids is not None):
        previous = project.sets[set_index - 1]
        path_by_dot = {
            dot_id: sample_transition_path(
                previous.dot_positions.get(dot_id, project.dot_by_id(dot_id) and (project.dot_by_id(dot_id).x, project.dot_by_id(dot_id).y) or (0, 0)),
                drill_set.dot_positions.get(dot_id, project.dot_by_id(dot_id) and (project.dot_by_id(dot_id).x, project.dot_by_id(dot_id).y) or (0, 0)),
                drill_set.path_anchors.get(dot_id, []),
                drill_set.path_controls.get(dot_id, []),
                samples=max(12, samples),
            )
            for dot_id in all_dot_ids
        }
        crossing_count = 0
        for first_index, dot_a in enumerate(all_dot_ids):
            for dot_b in all_dot_ids[first_index + 1 :]:
                if dot_a not in selected_dot_ids and dot_b not in selected_dot_ids:
                    continue
                if polylines_cross(path_by_dot[dot_a], path_by_dot[dot_b]):
                    crossing_count += 1
        if crossing_count and entries:
            midpoint = entries[len(entries) // 2]
            midpoint.crossing_conflicts = crossing_count

    return [entry for entry in entries if entry.total > 0]


def auto_plan_paths(
    project: DrillProject,
    set_index: int,
    dot_ids: list[str],
    min_spacing: float = 1.25,
) -> int:
    if set_index <= 0 or not 0 <= set_index < len(project.sets):
        return 0
    selected = set(dot_ids) if dot_ids else {dot.id for dot in project.dots}
    current = project.sets[set_index]
    previous = project.sets[set_index - 1]
    anchors_added = 0
    planned_dots: set[str] = set()
    planned_pairs: set[tuple[str, str]] = set()
    max_anchors = min(32, max(4, len(selected) // 4))

    for dot_id in selected:
        current.path_anchors.pop(dot_id, None)
        current.path_controls.pop(dot_id, None)

    warnings = detect_path_warnings(
        project,
        set_index,
        min_spacing=min_spacing,
        samples=12,
        dot_ids=list(selected),
        warning_limit=160,
    )
    for warning in warnings:
        if warning.severity not in {"spacing", "crossing"} or not warning.dot_a or not warning.dot_b:
            continue
        pair = tuple(sorted((warning.dot_a, warning.dot_b)))
        if pair in planned_pairs:
            continue
        planned_pairs.add(pair)
        if (
            warning.severity == "spacing"
            and (warning.count <= current.start_count + 0.25 or warning.count >= current.end_count - 0.25)
        ):
            continue
        route_dot = choose_route_dot(
            warning.dot_a,
            warning.dot_b,
            selected,
            planned_dots,
            previous.dot_positions,
            current.dot_positions,
        )
        if not route_dot:
            continue
        avoid_dot = warning.dot_a if route_dot == warning.dot_b else warning.dot_b
        if route_path_away_from_conflict(
            previous.dot_positions,
            current.dot_positions,
            current.path_anchors,
            route_dot,
            avoid_dot,
            min_spacing,
            anchors_added,
        ):
            current.path_controls.pop(route_dot, None)
            planned_dots.add(route_dot)
            anchors_added += 1
        if anchors_added >= max_anchors:
            return anchors_added

    return anchors_added


def choose_route_dot(
    dot_a: str,
    dot_b: str,
    selected: set[str],
    planned_dots: set[str],
    previous_positions: dict[str, tuple[float, float]],
    current_positions: dict[str, tuple[float, float]],
) -> str:
    candidates = [
        dot_id
        for dot_id in (dot_a, dot_b)
        if dot_id in selected and dot_id not in planned_dots
    ]
    moving_candidates = [
        dot_id
        for dot_id in candidates
        if dot_id in previous_positions
        and dot_id in current_positions
        and distance(previous_positions[dot_id], current_positions[dot_id]) > 0.25
    ]
    if not moving_candidates:
        return ""
    return min(
        moving_candidates,
        key=lambda dot_id: distance(previous_positions[dot_id], current_positions[dot_id]),
    )


def route_path_away_from_conflict(
    previous_positions: dict[str, tuple[float, float]],
    current_positions: dict[str, tuple[float, float]],
    path_anchors: dict[str, list[tuple[float, float]]],
    route_dot: str,
    avoid_dot: str,
    min_spacing: float,
    _route_index: int,
) -> bool:
    start = previous_positions.get(route_dot)
    end = current_positions.get(route_dot)
    avoid_start = previous_positions.get(avoid_dot)
    avoid_end = current_positions.get(avoid_dot)
    if not start or not end or not avoid_start or not avoid_end or distance(start, end) < 0.1:
        return False

    midpoint = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    direction = (end[0] - start[0], end[1] - start[1])
    path_length = distance(start, end)
    if path_length < 0.1:
        return False
    perpendicular = (-direction[1] / path_length, direction[0] / path_length)
    avoid_midpoint = ((avoid_start[0] + avoid_end[0]) / 2, (avoid_start[1] + avoid_end[1]) / 2)
    offset = min(6.0, max(2.0, min_spacing * 1.75))
    candidates = [
        (
            midpoint[0] + perpendicular[0] * offset,
            midpoint[1] + perpendicular[1] * offset,
        ),
        (
            midpoint[0] - perpendicular[0] * offset,
            midpoint[1] - perpendicular[1] * offset,
        ),
    ]
    anchor = max(
        candidates,
        key=lambda point: distance(point, avoid_midpoint) - field_penalty(point),
    )
    path_anchors[route_dot] = [clamp_to_field(anchor)]
    return True


def clamp_to_field(point: tuple[float, float]) -> tuple[float, float]:
    return (
        max(-58.0, min(58.0, point[0])),
        max(-25.5, min(25.5, point[1])),
    )


def field_penalty(point: tuple[float, float]) -> float:
    x, y = point
    penalty = 0.0
    if x < -58.0:
        penalty += (-58.0 - x) * 4
    elif x > 58.0:
        penalty += (x - 58.0) * 4
    if y < -25.5:
        penalty += (-25.5 - y) * 4
    elif y > 25.5:
        penalty += (y - 25.5) * 4
    return penalty


def polylines_cross(
    first: list[tuple[float, float]],
    second: list[tuple[float, float]],
) -> bool:
    for first_index in range(len(first) - 1):
        for second_index in range(len(second) - 1):
            if not segment_bounds_overlap(
                first[first_index],
                first[first_index + 1],
                second[second_index],
                second[second_index + 1],
            ):
                continue
            if segments_intersect(
                first[first_index],
                first[first_index + 1],
                second[second_index],
                second[second_index + 1],
            ):
                return True
    return False


def segment_bounds_overlap(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
    padding: float = 0.05,
) -> bool:
    return not (
        max(a[0], b[0]) + padding < min(c[0], d[0])
        or max(c[0], d[0]) + padding < min(a[0], b[0])
        or max(a[1], b[1]) + padding < min(c[1], d[1])
        or max(c[1], d[1]) + padding < min(a[1], b[1])
    )


def segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    if min(distance(a, c), distance(a, d), distance(b, c), distance(b, d)) < 0.05:
        return False

    def orientation(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> float:
        return (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])

    o1 = orientation(a, b, c)
    o2 = orientation(a, b, d)
    o3 = orientation(c, d, a)
    o4 = orientation(c, d, b)
    return o1 * o2 < 0 and o3 * o4 < 0
