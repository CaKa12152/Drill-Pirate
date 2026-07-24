from __future__ import annotations

from dataclasses import dataclass, field
from math import atan2, degrees, hypot

from drill_writer.core.accelerators import balanced_counts, spatial_id_order
from drill_writer.core.animation import cubic_bezier_point, point_on_polyline, sample_bezier_path
from drill_writer.core.assignment import (
    epsilon_scaling_auction_assignment,
    greedy_nearest_assignment,
    minimum_cost_target_assignment,
)
from drill_writer.core.cad_paths import Point, cad_offset, interpolate, path_to_bezier_nodes, unit_vector
from drill_writer.core.tools import positions_along_path


BezierNode = dict[str, Point]


@dataclass(slots=True)
class CurvilinearFormPlan:
    master_path: list[Point]
    rank_paths: list[list[Point]]
    rank_dot_ids: list[list[str]]
    targets: dict[str, Point] = field(default_factory=dict)


@dataclass(slots=True)
class CurvilinearTransitionPlan:
    paths: dict[str, list[Point]] = field(default_factory=dict)
    path_anchors: dict[str, list[Point]] = field(default_factory=dict)
    path_controls: dict[str, list[dict[str, Point]]] = field(default_factory=dict)
    count_facings: dict[str, dict[float, float]] = field(default_factory=dict)
    end_facings: dict[str, float] = field(default_factory=dict)


def initialize_curvilinear_nodes(
    positions: list[Point],
    node_count: int = 6,
    closed: bool = False,
) -> list[BezierNode]:
    if len(positions) < 2:
        return []
    count = max(2, min(16, int(node_count)))
    ordered = _spatial_point_order(positions, closed)
    if closed:
        sampled = positions_along_path(
            [*ordered, ordered[0]] if ordered[0] != ordered[-1] else ordered,
            count,
        )
    else:
        sampled = _open_centerline_points(positions, count)
    if closed and sampled and sampled[-1] == sampled[0]:
        sampled.pop()
    return _nodes_from_points(sampled, closed)


def sample_curvilinear_nodes(
    nodes: list[BezierNode],
    closed: bool = False,
    samples_per_segment: int = 28,
) -> list[Point]:
    valid = [node for node in nodes if "point" in node]
    if len(valid) < 2:
        return [node["point"] for node in valid]
    sampled: list[Point] = []
    segment_count = len(valid) if closed else len(valid) - 1
    precision = max(6, min(96, int(samples_per_segment)))
    for index in range(segment_count):
        following = (index + 1) % len(valid)
        start = valid[index]["point"]
        end = valid[following]["point"]
        control_out = valid[index].get("out", interpolate(start, end, 1.0 / 3.0))
        control_in = valid[following].get("in", interpolate(start, end, 2.0 / 3.0))
        for sample_index in range(precision):
            if sampled and sample_index == 0:
                continue
            sampled.append(
                cubic_bezier_point(
                    start,
                    control_out,
                    control_in,
                    end,
                    sample_index / precision,
                )
            )
    sampled.append(valid[0]["point"] if closed else valid[-1]["point"])
    return sampled


def plan_curvilinear_form(
    dot_ids: list[str],
    start_positions: dict[str, Point],
    nodes: list[BezierNode],
    rank_count: int = 1,
    rank_interval: float = 2.0,
    closed: bool = False,
    preferred_rank_dot_ids: list[list[str]] | None = None,
) -> CurvilinearFormPlan:
    valid_ids = [dot_id for dot_id in dot_ids if dot_id in start_positions]
    if len(valid_ids) < 2:
        raise ValueError("A curvilinear form requires at least two marchers.")
    master_path = sample_curvilinear_nodes(nodes, closed=closed)
    if len(master_path) < 2:
        raise ValueError("The curvilinear spline needs at least two usable nodes.")

    ranks = max(1, min(int(rank_count), len(valid_ids)))
    counts = balanced_counts(len(valid_ids), ranks)
    offsets = [(index - (ranks - 1) / 2.0) * max(0.1, float(rank_interval)) for index in range(ranks)]
    offset_source = master_path[:-1] if closed and master_path[0] == master_path[-1] else master_path
    rank_paths = [
        _close_path(cad_offset(offset_source, offset, closed=closed)) if closed else cad_offset(offset_source, offset)
        for offset in offsets
    ]
    target_rows = [positions_along_path(path, count) for path, count in zip(rank_paths, counts)]
    if _valid_preferred_ranks(preferred_rank_dot_ids, valid_ids, target_rows):
        rank_dot_ids = [list(row) for row in preferred_rank_dot_ids or []]
    else:
        assigned_ranks = _globally_assigned_ranks(valid_ids, start_positions, target_rows)
        rank_dot_ids = _topology_preserving_ranks(
            assigned_ranks,
            start_positions,
            target_rows,
            closed,
        )
    targets: dict[str, Point] = {}
    for row_ids, row_targets in zip(rank_dot_ids, target_rows):
        for dot_id, target in zip(row_ids, row_targets):
            targets[dot_id] = target
    return CurvilinearFormPlan(
        master_path=master_path,
        rank_paths=rank_paths,
        rank_dot_ids=rank_dot_ids,
        targets=targets,
    )


def plan_curvilinear_transition(
    rank_dot_ids: list[list[str]],
    start_positions: dict[str, Point],
    end_positions: dict[str, Point],
    flow_strength: float = 0.8,
    face_direction: bool = False,
    closed: bool = False,
    anchor_count: int = 5,
) -> CurvilinearTransitionPlan:
    result = CurvilinearTransitionPlan()
    strength = max(0.0, min(1.5, float(flow_strength)))
    interior_count = max(1, min(9, int(anchor_count)))
    for row_ids in rank_dot_ids:
        valid = [dot_id for dot_id in row_ids if dot_id in start_positions and dot_id in end_positions]
        if not valid:
            continue
        start_tangents = _ordered_tangents(valid, start_positions, closed)
        end_tangents = _ordered_tangents(valid, end_positions, closed)
        for dot_id in valid:
            start = start_positions[dot_id]
            end = end_positions[dot_id]
            travel = hypot(end[0] - start[0], end[1] - start[1])
            if travel <= 0.0001:
                result.paths[dot_id] = [start, end]
                result.path_anchors[dot_id] = []
                result.path_controls[dot_id] = []
            elif strength <= 0.0001:
                result.path_anchors[dot_id] = []
                result.path_controls[dot_id] = []
                result.paths[dot_id] = [start, end]
            else:
                handle_length = min(8.0, max(0.3, travel * (0.1 + 0.16 * min(1.0, strength))))
                start_tangent = _flow_tangent(start_tangents[dot_id], start, end, strength)
                end_tangent = _flow_tangent(end_tangents[dot_id], start, end, strength)
                control_1 = (
                    start[0] + start_tangent[0] * handle_length,
                    start[1] + start_tangent[1] * handle_length,
                )
                control_2 = (
                    end[0] - end_tangent[0] * handle_length,
                    end[1] - end_tangent[1] * handle_length,
                )
                anchors = [
                    cubic_bezier_point(
                        start,
                        control_1,
                        control_2,
                        end,
                        (index + 1) / (interior_count + 1),
                    )
                    for index in range(interior_count)
                ]
                nodes = path_to_bezier_nodes([start, *anchors, end])
                result.path_anchors[dot_id] = anchors
                result.path_controls[dot_id] = [
                    {"in": node["in"], "out": node["out"]}
                    for node in nodes[1:-1]
                ]
                result.paths[dot_id] = sample_bezier_path(
                    start,
                    end,
                    anchors,
                    result.path_controls[dot_id],
                    samples_per_segment=12,
                )
            if face_direction:
                start_rank_facing = _vector_facing(start_tangents[dot_id])
                end_rank_facing = _vector_facing(end_tangents[dot_id])
                if travel <= 0.0001:
                    facings = {0.0: start_rank_facing, 1.0: end_rank_facing}
                else:
                    facings = _path_facing_keyframes(result.paths[dot_id])
                    for progress, path_facing in list(facings.items()):
                        if progress <= 0.2:
                            facings[progress] = _blend_facing(
                                start_rank_facing,
                                path_facing,
                                _smoothstep(progress / 0.2),
                            )
                        elif progress >= 0.8:
                            facings[progress] = _blend_facing(
                                path_facing,
                                end_rank_facing,
                                _smoothstep((progress - 0.8) / 0.2),
                            )
                facings[0.0] = start_rank_facing
                facings[1.0] = end_rank_facing
                result.count_facings[dot_id] = facings
                result.end_facings[dot_id] = facings[1.0]
    return result


def _nodes_from_points(points: list[Point], closed: bool) -> list[BezierNode]:
    if len(points) < 2:
        return []
    nodes: list[BezierNode] = []
    for index, point in enumerate(points):
        if closed:
            previous = points[(index - 1) % len(points)]
            following = points[(index + 1) % len(points)]
        else:
            previous = points[max(0, index - 1)]
            following = points[min(len(points) - 1, index + 1)]
        tangent = ((following[0] - previous[0]) / 6.0, (following[1] - previous[1]) / 6.0)
        nodes.append(
            {
                "point": point,
                "in": (point[0] - tangent[0], point[1] - tangent[1]),
                "out": (point[0] + tangent[0], point[1] + tangent[1]),
            }
        )
    return nodes


def _spatial_point_order(positions: list[Point], closed: bool) -> list[Point]:
    indexed = {str(index): point for index, point in enumerate(positions)}
    return [indexed[index] for index in spatial_id_order(list(indexed), indexed, closed=closed)]


def _open_centerline_points(positions: list[Point], count: int) -> list[Point]:
    if len(positions) <= count:
        ordered = _spatial_point_order(positions, False)
        return positions_along_path(ordered, count)
    spread_x = max(point[0] for point in positions) - min(point[0] for point in positions)
    spread_y = max(point[1] for point in positions) - min(point[1] for point in positions)
    if spread_x >= spread_y:
        ordered = sorted(positions, key=lambda point: (point[0], point[1]))
    else:
        ordered = sorted(positions, key=lambda point: (point[1], point[0]))
    centers: list[Point] = []
    for index in range(count):
        start = round(index * len(ordered) / count)
        end = round((index + 1) * len(ordered) / count)
        bucket = ordered[start : max(start + 1, end)]
        centers.append(
            (
                sum(point[0] for point in bucket) / len(bucket),
                sum(point[1] for point in bucket) / len(bucket),
            )
        )
    return centers


def _close_path(path: list[Point]) -> list[Point]:
    if path and path[0] != path[-1]:
        return [*path, path[0]]
    return path


def _valid_preferred_ranks(
    preferred: list[list[str]] | None,
    dot_ids: list[str],
    target_rows: list[list[Point]],
) -> bool:
    if not preferred or len(preferred) != len(target_rows):
        return False
    if [len(row) for row in preferred] != [len(row) for row in target_rows]:
        return False
    flattened = [dot_id for row in preferred for dot_id in row]
    return len(flattened) == len(dot_ids) and set(flattened) == set(dot_ids)


def _globally_assigned_ranks(
    dot_ids: list[str],
    starts: dict[str, Point],
    target_rows: list[list[Point]],
) -> list[list[str]]:
    targets = [target for row in target_rows for target in row]
    source_points = [starts[dot_id] for dot_id in dot_ids]
    if len(dot_ids) <= 160:
        assignment = minimum_cost_target_assignment(source_points, targets)
    elif len(dot_ids) <= 700:
        assignment = epsilon_scaling_auction_assignment(source_points, targets)
    else:
        assignment = greedy_nearest_assignment(source_points, targets)
    ids_by_slot = ["" for _target in targets]
    for dot_id, target_index in zip(dot_ids, assignment):
        ids_by_slot[target_index] = dot_id
    ranks: list[list[str]] = []
    cursor = 0
    for row in target_rows:
        count = len(row)
        ranks.append(ids_by_slot[cursor : cursor + count])
        cursor += count
    return ranks


def _topology_preserving_ranks(
    assigned_ranks: list[list[str]],
    starts: dict[str, Point],
    target_rows: list[list[Point]],
    closed: bool,
) -> list[list[str]]:
    return [
        _align_rank_topology(row_ids, starts, row_targets, closed)
        for row_ids, row_targets in zip(assigned_ranks, target_rows)
    ]


def _align_rank_topology(
    dot_ids: list[str],
    starts: dict[str, Point],
    targets: list[Point],
    closed: bool,
) -> list[str]:
    if len(dot_ids) < 2:
        return list(dot_ids)
    ordered = spatial_id_order(dot_ids, starts, closed=closed)
    if not closed:
        forward_cost = _ordered_target_cost(ordered, starts, targets)
        reversed_ids = list(reversed(ordered))
        reverse_cost = _ordered_target_cost(reversed_ids, starts, targets)
        return reversed_ids if reverse_cost + 0.000001 < forward_cost else ordered

    candidates: list[list[str]] = []
    for direction in (ordered, list(reversed(ordered))):
        for offset in range(len(direction)):
            candidates.append(direction[offset:] + direction[:offset])
    return min(candidates, key=lambda candidate: _ordered_target_cost(candidate, starts, targets))


def _ordered_target_cost(
    dot_ids: list[str],
    starts: dict[str, Point],
    targets: list[Point],
) -> float:
    return sum(
        (starts[dot_id][0] - target[0]) ** 2 + (starts[dot_id][1] - target[1]) ** 2
        for dot_id, target in zip(dot_ids, targets)
    )


def _ordered_tangents(ids: list[str], positions: dict[str, Point], closed: bool) -> dict[str, Point]:
    tangents: dict[str, Point] = {}
    for index, dot_id in enumerate(ids):
        if closed and len(ids) > 2:
            previous = positions[ids[(index - 1) % len(ids)]]
            following = positions[ids[(index + 1) % len(ids)]]
        else:
            previous = positions[ids[max(0, index - 1)]]
            following = positions[ids[min(len(ids) - 1, index + 1)]]
        tangent = unit_vector(following[0] - previous[0], following[1] - previous[1])
        if tangent == (0.0, 0.0):
            tangent = (1.0, 0.0)
        tangents[dot_id] = tangent
    return tangents


def _orient_tangent(tangent: Point, start: Point, end: Point) -> Point:
    travel = unit_vector(end[0] - start[0], end[1] - start[1])
    if travel != (0.0, 0.0) and tangent[0] * travel[0] + tangent[1] * travel[1] < -0.2:
        return (-tangent[0], -tangent[1])
    return tangent


def _flow_tangent(tangent: Point, start: Point, end: Point, strength: float) -> Point:
    travel = unit_vector(end[0] - start[0], end[1] - start[1])
    if travel == (0.0, 0.0):
        return tangent
    oriented = _orient_tangent(tangent, start, end)
    curve_weight = max(0.0, min(0.78, float(strength) * 0.72))
    blended = unit_vector(
        travel[0] * (1.0 - curve_weight) + oriented[0] * curve_weight,
        travel[1] * (1.0 - curve_weight) + oriented[1] * curve_weight,
    )
    return blended if blended != (0.0, 0.0) else travel


def _facing_degrees(before: Point, after: Point) -> float:
    return degrees(atan2(-(after[0] - before[0]), -(after[1] - before[1]))) % 360.0


def _vector_facing(vector: Point) -> float:
    return _facing_degrees((0.0, 0.0), vector)


def _blend_facing(start: float, end: float, progress: float) -> float:
    delta = ((end - start + 180.0) % 360.0) - 180.0
    return (start + delta * max(0.0, min(1.0, progress))) % 360.0


def _smoothstep(progress: float) -> float:
    bounded = max(0.0, min(1.0, progress))
    return bounded * bounded * (3.0 - 2.0 * bounded)


def _path_facing_keyframes(path: list[Point], sample_count: int = 32) -> dict[float, float]:
    samples = max(8, min(128, int(sample_count)))
    tangent_window = 0.35 / samples
    facings: dict[float, float] = {}
    for sample_index in range(samples + 1):
        progress = sample_index / samples
        before = point_on_polyline(path, max(0.0, progress - tangent_window))
        after = point_on_polyline(path, min(1.0, progress + tangent_window))
        facings[progress] = _facing_degrees(before, after)
    return facings
