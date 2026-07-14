from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, radians, sin, tan
from typing import Iterable

from drill_writer.core.analysis import segments_intersect, transition_start_positions
from drill_writer.core.animation import distance, interpolate_project, interpolate_props
from drill_writer.core.assignment import greedy_nearest_assignment, hungarian_minimum_assignment, minimum_cost_target_assignment, ordered_targets
from drill_writer.core.models import DrillProject, DrillSet, Marker
from drill_writer.core.timing import local_tempo, set_index_for_count


Point = tuple[float, float]


@dataclass(slots=True)
class TransformParameters:
    offset_x: float = 0.0
    offset_y: float = 0.0
    rotation_degrees: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    skew_x_degrees: float = 0.0
    skew_y_degrees: float = 0.0
    pivot: Point | None = None


@dataclass(slots=True)
class AssignmentScore:
    total_distance: float
    maximum_distance: float
    crossings: int
    spacing_conflicts: int

    @property
    def weighted_score(self) -> float:
        return (
            self.total_distance
            + self.maximum_distance * 2.5
            + self.crossings * 30.0
            + self.spacing_conflicts * 18.0
        )


@dataclass(slots=True)
class TransitionCandidate:
    key: str
    label: str
    positions: dict[str, Point]
    score: AssignmentScore


def selection_center(positions: Iterable[Point]) -> Point:
    values = list(positions)
    if not values:
        return (0.0, 0.0)
    return (
        sum(point[0] for point in values) / len(values),
        sum(point[1] for point in values) / len(values),
    )


def transform_positions(
    positions: dict[str, Point],
    parameters: TransformParameters,
) -> dict[str, Point]:
    if not positions:
        return {}
    pivot_x, pivot_y = parameters.pivot or selection_center(positions.values())
    rotation = radians(parameters.rotation_degrees)
    rotation_cos = cos(rotation)
    rotation_sin = sin(rotation)
    skew_x = tan(radians(max(-80.0, min(80.0, parameters.skew_x_degrees))))
    skew_y = tan(radians(max(-80.0, min(80.0, parameters.skew_y_degrees))))
    transformed: dict[str, Point] = {}
    for dot_id, (x, y) in positions.items():
        local_x = (x - pivot_x) * parameters.scale_x
        local_y = (y - pivot_y) * parameters.scale_y
        skewed_x = local_x + local_y * skew_x
        skewed_y = local_y + local_x * skew_y
        rotated_x = skewed_x * rotation_cos - skewed_y * rotation_sin
        rotated_y = skewed_x * rotation_sin + skewed_y * rotation_cos
        transformed[dot_id] = (
            pivot_x + rotated_x + parameters.offset_x,
            pivot_y + rotated_y + parameters.offset_y,
        )
    return transformed


def transition_candidates(
    project: DrillProject,
    set_index: int,
    dot_ids: list[str],
    targets: list[Point],
    min_spacing: float = 1.25,
) -> list[TransitionCandidate]:
    valid_ids = [dot_id for dot_id in dot_ids if project.dot_by_id(dot_id)]
    if len(valid_ids) != len(targets) or not valid_ids:
        return []
    starts_by_id = transition_start_positions(project, set_index)
    starts = [starts_by_id.get(dot_id, (0.0, 0.0)) for dot_id in valid_ids]

    assignments: list[tuple[str, str, list[int]]] = []
    shortest = (
        minimum_cost_target_assignment(starts, targets)
        if len(valid_ids) <= 220
        else greedy_nearest_assignment(starts, targets)
    )
    assignments.append(("shortest", "Shortest total travel", shortest))
    assignments.append(
        (
            "rank",
            "Preserve ranks / files",
            grouped_assignment(project, valid_ids, starts, targets, "rank", group_weight=1.8),
        )
    )
    assignments.append(
        (
            "section",
            "Preserve sections",
            grouped_assignment(project, valid_ids, starts, targets, "section", group_weight=2.35),
        )
    )
    assignments.append(("clockwise", "Clockwise", angular_assignment(starts, targets, clockwise=True)))
    assignments.append(("counterclockwise", "Counterclockwise", angular_assignment(starts, targets, clockwise=False)))
    assignments.append(("follow_leader", "Follow leader", follow_leader_assignment(starts, targets)))

    base_assignments = [assignment for _key, _label, assignment in assignments]
    lowest_collision = min(
        (improve_assignment(starts, targets, assignment, min_spacing) for assignment in base_assignments),
        key=lambda assignment: score_assignment(starts, [targets[index] for index in assignment], min_spacing).weighted_score,
    )
    assignments.append(("lowest_collision", "Lowest collision risk", lowest_collision))

    candidates: list[TransitionCandidate] = []
    for key, label, assignment in assignments:
        assigned_targets = [targets[index] for index in assignment]
        positions = dict(zip(valid_ids, assigned_targets))
        candidates.append(
            TransitionCandidate(
                key=key,
                label=label,
                positions=positions,
                score=score_assignment(starts, assigned_targets, min_spacing),
            )
        )
    return sorted(candidates, key=lambda candidate: candidate.score.weighted_score)


def assignment_for_mode(
    project: DrillProject,
    set_index: int,
    dot_ids: list[str],
    targets: list[Point],
    mode: str,
) -> dict[str, Point]:
    candidates = transition_candidates(project, set_index, dot_ids, targets)
    if not candidates:
        return dict(zip(dot_ids, targets))
    if mode in {"automatic", "lowest_collision"}:
        desired = "lowest_collision"
    elif mode in {"section_aware", "section"}:
        desired = "section"
    elif mode in {"preserve_ranks", "rank"}:
        desired = "rank"
    else:
        desired = mode
    return next((candidate.positions for candidate in candidates if candidate.key == desired), candidates[0].positions)


def grouped_assignment(
    project: DrillProject,
    dot_ids: list[str],
    starts: list[Point],
    targets: list[Point],
    attribute: str,
    group_weight: float,
) -> list[int]:
    groups: dict[str, list[int]] = {}
    for index, dot_id in enumerate(dot_ids):
        dot = project.dot_by_id(dot_id)
        value = str(getattr(dot, attribute, "") or f"__{dot_id}").strip().lower()
        groups.setdefault(value, []).append(index)
    group_centers = {
        name: selection_center(starts[index] for index in indices)
        for name, indices in groups.items()
    }
    show_center = selection_center(starts)
    target_center = selection_center(targets)
    costs: list[list[float]] = []
    for marcher_index, (start_x, start_y) in enumerate(starts):
        dot = project.dot_by_id(dot_ids[marcher_index])
        group_name = str(getattr(dot, attribute, "") or f"__{dot_ids[marcher_index]}").strip().lower()
        group_x, group_y = group_centers[group_name]
        relative_group_x = group_x - show_center[0]
        relative_group_y = group_y - show_center[1]
        row: list[float] = []
        for target_x, target_y in targets:
            move = distance((start_x, start_y), (target_x, target_y))
            relative_target_x = target_x - target_center[0]
            relative_target_y = target_y - target_center[1]
            group_displacement = distance(
                (relative_group_x, relative_group_y),
                (relative_target_x, relative_target_y),
            )
            row.append(move * move + group_displacement * group_displacement * group_weight)
        costs.append(row)
    return hungarian_minimum_assignment(costs) if len(costs) <= 220 else greedy_cost_assignment(costs)


def greedy_cost_assignment(costs: list[list[float]]) -> list[int]:
    pairs = sorted(
        (cost, row, column)
        for row, values in enumerate(costs)
        for column, cost in enumerate(values)
    )
    assignment: list[int | None] = [None] * len(costs)
    used_columns: set[int] = set()
    for _cost, row, column in pairs:
        if assignment[row] is not None or column in used_columns:
            continue
        assignment[row] = column
        used_columns.add(column)
        if len(used_columns) == len(costs):
            break
    remaining = [column for column in range(len(costs)) if column not in used_columns]
    for row, column in enumerate(assignment):
        if column is None:
            best = min(remaining, key=lambda candidate: costs[row][candidate])
            assignment[row] = best
            remaining.remove(best)
    return [int(column) for column in assignment]


def angular_assignment(starts: list[Point], targets: list[Point], clockwise: bool) -> list[int]:
    start_center = selection_center(starts)
    target_center = selection_center(targets)
    start_order = sorted(
        range(len(starts)),
        key=lambda index: atan2(starts[index][1] - start_center[1], starts[index][0] - start_center[0]),
        reverse=clockwise,
    )
    target_order = sorted(
        range(len(targets)),
        key=lambda index: atan2(targets[index][1] - target_center[1], targets[index][0] - target_center[0]),
        reverse=clockwise,
    )
    ordered_start_points = [starts[index] for index in start_order]
    ordered_target_points = [targets[index] for index in target_order]
    best_targets = ordered_targets(ordered_start_points, ordered_target_points, allow_reverse=False, allow_rotation=True)
    target_lookup = {point: [] for point in targets}
    for index, point in enumerate(targets):
        target_lookup.setdefault(point, []).append(index)
    assignment = [-1] * len(starts)
    for start_index, point in zip(start_order, best_targets):
        assignment[start_index] = target_lookup[point].pop(0)
    return assignment


def follow_leader_assignment(starts: list[Point], targets: list[Point]) -> list[int]:
    start_order = nearest_neighbor_order(starts)
    target_order = nearest_neighbor_order(targets)
    ordered_starts = [starts[index] for index in start_order]
    ordered_target_points = [targets[index] for index in target_order]
    ordered_target_points = ordered_targets(
        ordered_starts,
        ordered_target_points,
        allow_reverse=True,
        allow_rotation=True,
    )
    lookup: dict[Point, list[int]] = {}
    for index, point in enumerate(targets):
        lookup.setdefault(point, []).append(index)
    assignment = [-1] * len(starts)
    for start_index, point in zip(start_order, ordered_target_points):
        assignment[start_index] = lookup[point].pop(0)
    return assignment


def nearest_neighbor_order(points: list[Point]) -> list[int]:
    if not points:
        return []
    center = selection_center(points)
    current = min(range(len(points)), key=lambda index: (points[index][0] - center[0]) ** 2 + (points[index][1] - center[1]) ** 2)
    remaining = set(range(len(points)))
    remaining.remove(current)
    order = [current]
    while remaining:
        current = min(remaining, key=lambda index: distance(points[order[-1]], points[index]))
        remaining.remove(current)
        order.append(current)
    return order


def improve_assignment(
    starts: list[Point],
    targets: list[Point],
    assignment: list[int],
    min_spacing: float,
) -> list[int]:
    improved = list(assignment)
    if len(improved) > 240:
        return improved
    for _iteration in range(3):
        changed = False
        for first in range(len(improved) - 1):
            for second in range(first + 1, len(improved)):
                first_target = targets[improved[first]]
                second_target = targets[improved[second]]
                current_cost = distance(starts[first], first_target) + distance(starts[second], second_target)
                swapped_cost = distance(starts[first], second_target) + distance(starts[second], first_target)
                if segments_intersect(starts[first], first_target, starts[second], second_target):
                    current_cost += 30.0
                if segments_intersect(starts[first], second_target, starts[second], first_target):
                    swapped_cost += 30.0
                if swapped_cost + 0.01 < current_cost:
                    improved[first], improved[second] = improved[second], improved[first]
                    changed = True
        if not changed:
            break
    return improved


def score_assignment(
    starts: list[Point],
    assigned_targets: list[Point],
    min_spacing: float,
    detailed_spacing: bool = True,
) -> AssignmentScore:
    move_distances = [distance(start, target) for start, target in zip(starts, assigned_targets)]
    crossings = 0
    spacing_conflicts = 0
    sample_steps = (0.25, 0.5, 0.75) if detailed_spacing else (0.5,)
    for first in range(len(starts) - 1):
        for second in range(first + 1, len(starts)):
            if segments_intersect(starts[first], assigned_targets[first], starts[second], assigned_targets[second]):
                crossings += 1
            for progress in sample_steps:
                first_point = (
                    starts[first][0] + (assigned_targets[first][0] - starts[first][0]) * progress,
                    starts[first][1] + (assigned_targets[first][1] - starts[first][1]) * progress,
                )
                second_point = (
                    starts[second][0] + (assigned_targets[second][0] - starts[second][0]) * progress,
                    starts[second][1] + (assigned_targets[second][1] - starts[second][1]) * progress,
                )
                if distance(first_point, second_point) < min_spacing:
                    spacing_conflicts += 1
                    break
    return AssignmentScore(
        total_distance=sum(move_distances),
        maximum_distance=max(move_distances, default=0.0),
        crossings=crossings,
        spacing_conflicts=spacing_conflicts,
    )


def ripple_set_indices(
    project: DrillProject,
    current_index: int,
    scope: str,
    dot_ids: list[str],
    range_start: int | None = None,
    range_end: int | None = None,
    tolerance: float = 0.04,
) -> list[int]:
    if not project.sets:
        return []
    current_index = max(0, min(current_index, len(project.sets) - 1))
    normalized_scope = scope.strip().lower().replace(" ", "_")
    if normalized_scope in {"current", "current_set", "current_set_only"}:
        return [current_index]
    if normalized_scope in {"forward", "from_current_forward"}:
        return list(range(current_index, len(project.sets)))
    if normalized_scope in {"selected_range", "selected_set_range"}:
        start = max(0, min((range_start or current_index + 1) - 1, len(project.sets) - 1))
        end = max(0, min((range_end or current_index + 1) - 1, len(project.sets) - 1))
        return list(range(min(start, end), max(start, end) + 1))
    if normalized_scope in {"until_next_keyframe", "until_keyframe"}:
        indices = [current_index]
        for index in range(current_index + 1, len(project.sets)):
            drill_set = project.sets[index]
            if any(drill_set.count_positions.get(dot_id) for dot_id in dot_ids):
                break
            indices.append(index)
        return indices
    if normalized_scope in {"matching", "matching_formations", "every_matching_formation"}:
        reference = {
            dot_id: project.sets[current_index].dot_positions[dot_id]
            for dot_id in dot_ids
            if dot_id in project.sets[current_index].dot_positions
        }
        return [
            index
            for index, drill_set in enumerate(project.sets)
            if formations_match(
                reference,
                {dot_id: drill_set.dot_positions[dot_id] for dot_id in reference if dot_id in drill_set.dot_positions},
                tolerance,
            )
        ] or [current_index]
    return [current_index]


def formations_match(first: dict[str, Point], second: dict[str, Point], tolerance: float = 0.04) -> bool:
    if not first or first.keys() != second.keys():
        return False
    first_center = selection_center(first.values())
    second_center = selection_center(second.values())
    first_scale = max((distance(point, first_center) for point in first.values()), default=1.0) or 1.0
    second_scale = max((distance(point, second_center) for point in second.values()), default=1.0) or 1.0
    for dot_id in first:
        first_normalized = (
            (first[dot_id][0] - first_center[0]) / first_scale,
            (first[dot_id][1] - first_center[1]) / first_scale,
        )
        second_normalized = (
            (second[dot_id][0] - second_center[0]) / second_scale,
            (second[dot_id][1] - second_center[1]) / second_scale,
        )
        if distance(first_normalized, second_normalized) > tolerance:
            return False
    return True


def generate_sets_from_markers(
    project: DrillProject,
    markers: list[Marker],
    *,
    include_show_end: bool = True,
) -> list[DrillSet]:
    if not markers:
        return []
    ordered_markers = sorted(markers, key=lambda marker: marker.count)
    boundaries: list[tuple[int, str]] = []
    for marker in ordered_markers:
        count = max(1, int(round(marker.count)))
        if boundaries and boundaries[-1][0] == count:
            boundaries[-1] = (count, marker.label or boundaries[-1][1])
        else:
            boundaries.append((count, marker.label or f"Set {len(boundaries) + 1}"))
    if project.sets and boundaries[0][0] > project.sets[0].start_count:
        boundaries.insert(0, (project.sets[0].start_count, project.sets[0].name or "Opening"))
    if include_show_end and project.sets:
        show_end = project.sets[-1].end_count + 1
    else:
        show_end = boundaries[-1][0] + max(1, project.metadata.default_counts_per_set)
    if boundaries[-1][0] >= show_end:
        show_end = boundaries[-1][0] + max(1, project.metadata.default_counts_per_set)

    generated: list[DrillSet] = []
    for index, (start_count, label) in enumerate(boundaries):
        end_count = (boundaries[index + 1][0] - 1) if index + 1 < len(boundaries) else show_end - 1
        end_count = max(start_count, end_count)
        source_index = set_index_for_count(project, min(float(end_count), float(project.sets[-1].end_count))) if project.sets else 0
        source_count = min(float(end_count), float(project.sets[-1].end_count)) if project.sets else float(end_count)
        positions = interpolate_project(project, source_index, source_count) if project.sets else {
            dot.id: (dot.x, dot.y) for dot in project.dots
        }
        prop_positions = interpolate_props(project, source_index, source_count) if project.sets else {}
        generated.append(
            DrillSet(
                name=label.strip() or f"Set {index + 1}",
                start_count=start_count,
                end_count=end_count,
                tempo=local_tempo(project, float(start_count)),
                dot_positions=dict(positions),
                prop_positions={prop_id: dict(state) for prop_id, state in prop_positions.items()},
            )
        )
    return generated
