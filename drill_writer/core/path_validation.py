from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, isfinite

from drill_writer.core.animation import distance, sample_transition_path
from drill_writer.core.design_tools import plan_motion_ribbon, sample_motion_ribbon
from drill_writer.core.models import DrillProject, MotionRibbon
from drill_writer.core.specialized_design import surface_contains_point


Point = tuple[float, float]


@dataclass(frozen=True, slots=True)
class PathValidationIssue:
    severity: str
    set_index: int
    set_name: str
    owner_kind: str
    owner_id: str
    code: str
    message: str
    suggestion: str
    count: float = 0.0


def validate_authored_paths(
    project: DrillProject,
    set_index: int,
    dot_ids: list[str] | None = None,
    *,
    min_spacing: float = 1.0,
) -> list[PathValidationIssue]:
    if not 0 <= set_index < len(project.sets):
        return []
    drill_set = project.sets[set_index]
    selected = set(dot_ids or [dot.id for dot in project.dots])
    starts = (
        dict(project.sets[set_index - 1].dot_positions)
        if set_index > 0
        else {dot.id: (dot.x, dot.y) for dot in project.dots}
    )
    issues: list[PathValidationIssue] = []
    for dot_id in selected:
        anchors = list(drill_set.path_anchors.get(dot_id, []))
        controls = list(drill_set.path_controls.get(dot_id, []))
        if not anchors and not controls:
            continue
        start = starts.get(dot_id)
        end = drill_set.dot_positions.get(dot_id)
        if start is None or end is None:
            issues.append(
                _issue(
                    drill_set.name,
                    set_index,
                    "path",
                    dot_id,
                    "missing_endpoint",
                    "error",
                    f"{dot_id} has an authored path but is missing a transition endpoint.",
                    "Restore the marcher in both pictures or clear the orphaned path.",
                    drill_set.start_count,
                )
            )
            continue
        if controls and not anchors:
            issues.append(
                _issue(
                    drill_set.name,
                    set_index,
                    "path",
                    dot_id,
                    "orphaned_controls",
                    "error",
                    f"{dot_id} has Bezier handles without anchor points.",
                    "Clear the handles or add the missing anchor points.",
                    drill_set.start_count,
                )
            )
            continue
        if controls and len(controls) != len(anchors):
            issues.append(
                _issue(
                    drill_set.name,
                    set_index,
                    "path",
                    dot_id,
                    "control_count_mismatch",
                    "error",
                    f"{dot_id} has {len(anchors)} path anchors but {len(controls)} Bezier handle sets.",
                    "Open Path Edit and rebuild the missing handles before playback or export.",
                    drill_set.start_count,
                )
            )
        points = [start, *anchors, end]
        invalid_points = [point for point in points if not finite_point(point)]
        invalid_controls = [
            point
            for control_set in controls
            for key, point in control_set.items()
            if key in {"in", "out"} and not finite_point(point)
        ]
        if invalid_points or invalid_controls:
            issues.append(
                _issue(
                    drill_set.name,
                    set_index,
                    "path",
                    dot_id,
                    "non_finite_geometry",
                    "error",
                    f"{dot_id} contains an invalid or non-finite path coordinate.",
                    "Reset the affected anchor or handle; invalid geometry cannot be played or exported safely.",
                    drill_set.start_count,
                )
            )
            continue
        for point_index in range(len(points) - 1):
            if distance(points[point_index], points[point_index + 1]) < 0.02:
                issues.append(
                    _issue(
                        drill_set.name,
                        set_index,
                        "path",
                        dot_id,
                        "duplicate_anchor",
                        "warning",
                        f"{dot_id} has consecutive path points on top of each other.",
                        "Remove the duplicate anchor to prevent an abrupt tangent or velocity spike.",
                        drill_set.start_count,
                    )
                )
                break
        issues.extend(
            _validate_anchor_handles(
                drill_set.name,
                set_index,
                dot_id,
                points,
                controls,
                drill_set.start_count,
                control_point_offset=1,
            )
        )
        sampled = sample_transition_path(start, end, anchors, controls, samples=96)
        issues.extend(
            _validate_sampled_path(
                project,
                drill_set.name,
                set_index,
                "path",
                dot_id,
                sampled,
                start,
                end,
                drill_set.start_count,
            )
        )

    for ribbon in drill_set.motion_ribbons:
        if selected.isdisjoint(ribbon.dot_ids):
            continue
        issues.extend(
            validate_motion_ribbon(
                project,
                set_index,
                ribbon,
                starts,
                min_spacing=min_spacing,
            )
        )
    return deduplicate_issues(issues)


def validate_motion_ribbon(
    project: DrillProject,
    set_index: int,
    ribbon: MotionRibbon,
    start_positions: dict[str, Point] | None = None,
    *,
    min_spacing: float = 1.0,
) -> list[PathValidationIssue]:
    drill_set = project.sets[set_index]
    starts = start_positions or (
        dict(project.sets[set_index - 1].dot_positions)
        if set_index > 0
        else {dot.id: (dot.x, dot.y) for dot in project.dots}
    )
    issues: list[PathValidationIssue] = []
    if len(ribbon.dot_ids) != len(set(ribbon.dot_ids)):
        issues.append(
            _issue(
                drill_set.name,
                set_index,
                "ribbon",
                ribbon.id,
                "duplicate_performer",
                "error",
                f"Motion ribbon '{ribbon.name}' contains the same performer more than once.",
                "Remove duplicate performers and regenerate the ribbon plan.",
                drill_set.start_count,
            )
        )
    missing = [
        dot_id
        for dot_id in ribbon.dot_ids
        if project.dot_by_id(dot_id) is None
        or dot_id not in starts
        or dot_id not in drill_set.dot_positions
    ]
    if missing:
        issues.append(
            _issue(
                drill_set.name,
                set_index,
                "ribbon",
                ribbon.id,
                "missing_performer",
                "error",
                f"Motion ribbon '{ribbon.name}' references missing performers: {', '.join(missing[:8])}.",
                "Remove missing performers from the ribbon or restore their set positions.",
                drill_set.start_count,
            )
        )
    nodes = [node for node in ribbon.nodes if isinstance(node, dict) and "point" in node]
    if len(nodes) < 2:
        issues.append(
            _issue(
                drill_set.name,
                set_index,
                "ribbon",
                ribbon.id,
                "insufficient_nodes",
                "error",
                f"Motion ribbon '{ribbon.name}' needs at least two valid route nodes.",
                "Recreate the ribbon or add route nodes before applying it.",
                drill_set.start_count,
            )
        )
        return issues
    all_points = [
        point
        for node in nodes
        for key, point in node.items()
        if key in {"point", "in", "out"}
    ]
    if any(not finite_point(point) for point in all_points):
        issues.append(
            _issue(
                drill_set.name,
                set_index,
                "ribbon",
                ribbon.id,
                "non_finite_geometry",
                "error",
                f"Motion ribbon '{ribbon.name}' contains an invalid route coordinate.",
                "Reset the affected route node or tangent handle.",
                drill_set.start_count,
            )
        )
        return issues
    node_points = [node["point"] for node in nodes]
    node_controls = [
        {key: point for key, point in node.items() if key in {"in", "out"}}
        for node in nodes
    ]
    issues.extend(
        _validate_anchor_handles(
            drill_set.name,
            set_index,
            ribbon.id,
            node_points,
            node_controls,
            drill_set.start_count,
            owner_kind="ribbon",
        )
    )
    sampled = sample_motion_ribbon(ribbon, 40)
    issues.extend(
        _validate_sampled_path(
            project,
            drill_set.name,
            set_index,
            "ribbon",
            ribbon.id,
            sampled,
            node_points[0],
            node_points[-1],
            drill_set.start_count,
        )
    )
    if missing or len(ribbon.dot_ids) < 2:
        return issues
    try:
        plan = plan_motion_ribbon(
            ribbon,
            starts,
            drill_set.dot_positions,
            float(drill_set.start_count),
            float(drill_set.end_count),
        )
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        issues.append(
            _issue(
                drill_set.name,
                set_index,
                "ribbon",
                ribbon.id,
                "planning_failure",
                "error",
                f"Motion ribbon '{ribbon.name}' cannot generate a safe transition: {exc}",
                "Repair its nodes, performer list, or movement count range, then regenerate it.",
                drill_set.start_count,
            )
        )
        return issues
    path_values = list(plan.paths.items())
    if not path_values:
        return issues
    sample_count = min(len(path) for _dot_id, path in path_values)
    worst_spacing = float("inf")
    worst_pair = ("", "")
    worst_index = 0
    for sample_index in range(sample_count):
        positions = [(dot_id, path[sample_index]) for dot_id, path in path_values]
        for first in range(len(positions) - 1):
            for second in range(first + 1, len(positions)):
                current = distance(positions[first][1], positions[second][1])
                if current < worst_spacing:
                    worst_spacing = current
                    worst_pair = (positions[first][0], positions[second][0])
                    worst_index = sample_index
    if worst_spacing < min_spacing:
        progress = worst_index / max(1, sample_count - 1)
        count = drill_set.start_count + (drill_set.end_count - drill_set.start_count) * progress
        issues.append(
            _issue(
                drill_set.name,
                set_index,
                "ribbon",
                ribbon.id,
                "generated_overlap",
                "error" if worst_spacing < min_spacing * 0.5 else "warning",
                f"Motion ribbon '{ribbon.name}' compresses {worst_pair[0]} and {worst_pair[1]} to {worst_spacing:.2f} yd.",
                "Widen the ribbon, reduce its bend, or change performer order before applying it.",
                count,
            )
        )
    return issues


def _validate_anchor_handles(
    set_name: str,
    set_index: int,
    owner_id: str,
    points: list[Point],
    controls: list[dict[str, Point]],
    count: float,
    *,
    owner_kind: str = "path",
    control_point_offset: int = 0,
) -> list[PathValidationIssue]:
    issues: list[PathValidationIssue] = []
    if len(points) < 2:
        return issues
    for node_index, point in enumerate(points):
        control_index = node_index - control_point_offset
        if not 0 <= control_index < len(controls):
            continue
        control_set = controls[control_index]
        adjacent_lengths = []
        if node_index > 0:
            adjacent_lengths.append(distance(points[node_index - 1], point))
        if node_index + 1 < len(points):
            adjacent_lengths.append(distance(point, points[node_index + 1]))
        reference = max(0.25, min(adjacent_lengths, default=0.25))
        for key in ("in", "out"):
            handle = control_set.get(key)
            if handle is not None and distance(point, handle) > max(4.0, reference * 2.5):
                issues.append(
                    _issue(
                        set_name,
                        set_index,
                        owner_kind,
                        owner_id,
                        "oversized_handle",
                        "warning",
                        f"{owner_kind.title()} '{owner_id}' has a {key} handle much longer than its adjacent segment.",
                        "Shorten the tangent handle to avoid loops, overshoot, and sudden direction changes.",
                        count,
                    )
                )
        if 0 < node_index < len(points) - 1:
            incoming = control_set.get("in")
            outgoing = control_set.get("out")
            if incoming is not None and outgoing is not None:
                incoming_angle = atan2(point[1] - incoming[1], point[0] - incoming[0])
                outgoing_angle = atan2(outgoing[1] - point[1], outgoing[0] - point[0])
                turn = abs(angle_delta_degrees(degrees(incoming_angle), degrees(outgoing_angle)))
                if turn > 95.0:
                    issues.append(
                        _issue(
                            set_name,
                            set_index,
                            owner_kind,
                            owner_id,
                            "broken_tangent",
                            "warning",
                            f"{owner_kind.title()} '{owner_id}' reverses {turn:.0f} degrees at a Bezier anchor.",
                            "Align the in/out tangent handles or intentionally split the move at a count keyframe.",
                            count,
                        )
                    )
    return issues


def _validate_sampled_path(
    project: DrillProject,
    set_name: str,
    set_index: int,
    owner_kind: str,
    owner_id: str,
    sampled: list[Point],
    start: Point,
    end: Point,
    count: float,
) -> list[PathValidationIssue]:
    issues: list[PathValidationIssue] = []
    if len(sampled) < 2 or any(not finite_point(point) for point in sampled):
        return [
            _issue(
                set_name,
                set_index,
                owner_kind,
                owner_id,
                "invalid_sampled_path",
                "error",
                f"{owner_kind.title()} '{owner_id}' does not produce finite playback geometry.",
                "Reset its Bezier handles or rebuild the path.",
                count,
            )
        ]
    if any(not surface_contains_point(project.surface, point, margin=0.01) for point in sampled):
        issues.append(
            _issue(
                set_name,
                set_index,
                owner_kind,
                owner_id,
                "outside_surface",
                "warning",
                f"{owner_kind.title()} '{owner_id}' leaves the authored performance surface.",
                "Move the path inside the surface or intentionally resize the surface.",
                count,
            )
        )
    if path_self_intersects(sampled):
        issues.append(
            _issue(
                set_name,
                set_index,
                owner_kind,
                owner_id,
                "self_intersection",
                "error",
                f"{owner_kind.title()} '{owner_id}' loops across itself.",
                "Move or shorten the Bezier handles until the route no longer self-intersects.",
                count,
            )
        )
    total_length = sum(distance(first, second) for first, second in zip(sampled, sampled[1:]))
    direct_length = distance(start, end)
    if direct_length > 0.25 and total_length > max(direct_length * 3.0, direct_length + 12.0):
        issues.append(
            _issue(
                set_name,
                set_index,
                owner_kind,
                owner_id,
                "excessive_detour",
                "warning",
                f"{owner_kind.title()} '{owner_id}' travels {total_length:.1f} yd for a {direct_length:.1f} yd displacement.",
                "Simplify the route or add counts if the long detour is intentional.",
                count,
            )
        )
    worst_turn = 0.0
    for first, second, third in zip(sampled, sampled[1:], sampled[2:]):
        if distance(first, second) < 0.01 or distance(second, third) < 0.01:
            continue
        incoming = degrees(atan2(second[1] - first[1], second[0] - first[0]))
        outgoing = degrees(atan2(third[1] - second[1], third[0] - second[0]))
        worst_turn = max(worst_turn, abs(angle_delta_degrees(incoming, outgoing)))
    if worst_turn > 105.0:
        issues.append(
            _issue(
                set_name,
                set_index,
                owner_kind,
                owner_id,
                "abrupt_direction_change",
                "warning",
                f"{owner_kind.title()} '{owner_id}' changes travel direction by {worst_turn:.0f} degrees at one point.",
                "Smooth the tangent or place the direction change at an authored halt/count keyframe.",
                count,
            )
        )
    return issues


def finite_point(point: object) -> bool:
    return (
        isinstance(point, (tuple, list))
        and len(point) >= 2
        and isfinite(float(point[0]))
        and isfinite(float(point[1]))
    )


def angle_delta_degrees(first: float, second: float) -> float:
    return (second - first + 180.0) % 360.0 - 180.0


def path_self_intersects(points: list[Point]) -> bool:
    if len(points) < 4:
        return False
    for first_index in range(len(points) - 1):
        for second_index in range(first_index + 2, len(points) - 1):
            if first_index == 0 and second_index == len(points) - 2 and distance(points[0], points[-1]) < 0.02:
                continue
            if raw_segments_intersect(
                points[first_index],
                points[first_index + 1],
                points[second_index],
                points[second_index + 1],
            ):
                return True
    return False


def raw_segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    def orientation(first: Point, second: Point, third: Point) -> float:
        return (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (third[0] - first[0])

    if (
        max(a[0], b[0]) < min(c[0], d[0])
        or max(c[0], d[0]) < min(a[0], b[0])
        or max(a[1], b[1]) < min(c[1], d[1])
        or max(c[1], d[1]) < min(a[1], b[1])
    ):
        return False
    first = orientation(a, b, c)
    second = orientation(a, b, d)
    third = orientation(c, d, a)
    fourth = orientation(c, d, b)
    return first * second < -1e-9 and third * fourth < -1e-9


def deduplicate_issues(issues: list[PathValidationIssue]) -> list[PathValidationIssue]:
    result: list[PathValidationIssue] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in issues:
        key = (issue.owner_kind, issue.owner_id, issue.code)
        if key in seen:
            continue
        seen.add(key)
        result.append(issue)
    return result


def _issue(
    set_name: str,
    set_index: int,
    owner_kind: str,
    owner_id: str,
    code: str,
    severity: str,
    message: str,
    suggestion: str,
    count: float,
) -> PathValidationIssue:
    return PathValidationIssue(
        severity=severity,
        set_index=set_index,
        set_name=set_name,
        owner_kind=owner_kind,
        owner_id=owner_id,
        code=code,
        message=message,
        suggestion=suggestion,
        count=float(count),
    )
