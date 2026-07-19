from __future__ import annotations

from dataclasses import dataclass, field
from math import atan2, degrees, hypot
from statistics import median


Point = tuple[float, float]


@dataclass(slots=True, frozen=True)
class FollowLeaderOptions:
    advance_spots: float = 1.0
    direction: int = 1
    topology: str = "auto"
    order_mode: str = "automatic"
    curved: bool = True
    samples_per_count: int = 4
    face_direction: bool = False
    facing_offset: float = 0.0


@dataclass(slots=True)
class FollowLeaderPlan:
    ordered_ids: list[str]
    route: list[Point]
    route_closed: bool
    leader_id: str
    spacing: float
    travel_distance: float
    end_positions: dict[str, Point] = field(default_factory=dict)
    count_positions: dict[str, dict[float, Point]] = field(default_factory=dict)
    count_facings: dict[str, dict[float, float]] = field(default_factory=dict)
    end_facings: dict[str, float] = field(default_factory=dict)


def plan_follow_leader(
    dot_ids: list[str],
    positions: dict[str, Point],
    start_count: float,
    end_count: float,
    options: FollowLeaderOptions | None = None,
) -> FollowLeaderPlan:
    settings = options or FollowLeaderOptions()
    valid_ids = [dot_id for dot_id in dot_ids if dot_id in positions]
    if len(valid_ids) < 2:
        raise ValueError("Follow the Leader requires at least two marchers.")
    if float(end_count) <= float(start_count):
        raise ValueError("Follow the Leader requires a set with more than one count.")

    ordered_ids, route_closed = ordered_route_ids(
        valid_ids,
        positions,
        settings.order_mode,
        settings.topology,
    )
    anchors = [positions[dot_id] for dot_id in ordered_ids]
    route, anchor_distances = sampled_follow_route(anchors, settings.curved, route_closed)
    cumulative = cumulative_distances(route)
    route_length = cumulative[-1]
    if route_length <= 0.0001:
        raise ValueError("The selected formation is too small to create a leader route.")

    gaps = route_gaps(anchor_distances, route_length, route_closed)
    spacing = median([gap for gap in gaps if gap > 0.0001]) if gaps else route_length / max(1, len(anchors) - 1)
    direction = 1 if settings.direction >= 0 else -1
    travel_distance = direction * max(0.0, float(settings.advance_spots)) * max(0.0001, spacing)
    count_step = 1.0 / max(1, min(16, int(settings.samples_per_count)))
    span = float(end_count) - float(start_count)
    sample_counts = count_samples(float(start_count), float(end_count), count_step)

    plan = FollowLeaderPlan(
        ordered_ids=ordered_ids,
        route=route,
        route_closed=route_closed,
        leader_id=ordered_ids[-1] if direction > 0 else ordered_ids[0],
        spacing=spacing,
        travel_distance=travel_distance,
    )
    for index, dot_id in enumerate(ordered_ids):
        start_distance = anchor_distances[index]
        end_distance = start_distance + travel_distance
        plan.end_positions[dot_id] = point_at_distance(route, cumulative, end_distance, route_closed)
        position_keyframes: dict[float, Point] = {}
        facing_keyframes: dict[float, float] = {}
        for count in sample_counts:
            progress = (count - float(start_count)) / span
            route_distance = start_distance + travel_distance * progress
            if start_count < count < end_count:
                position_keyframes[normalized_count(count)] = point_at_distance(
                    route,
                    cumulative,
                    route_distance,
                    route_closed,
                )
            if settings.face_direction and abs(travel_distance) > 0.0001:
                facing_keyframes[normalized_count(count)] = facing_at_distance(
                    route,
                    cumulative,
                    route_distance,
                    route_closed,
                    direction,
                    settings.facing_offset,
                )
        plan.count_positions[dot_id] = position_keyframes
        if facing_keyframes:
            plan.count_facings[dot_id] = facing_keyframes
            plan.end_facings[dot_id] = facing_keyframes[normalized_count(float(end_count))]
    return plan


def split_follow_leader_groups(
    dot_ids: list[str],
    positions: dict[str, Point],
    mode: str = "auto",
    sections: dict[str, str] | None = None,
) -> list[list[str]]:
    valid_ids = [dot_id for dot_id in dot_ids if dot_id in positions]
    if len(valid_ids) < 2 or mode == "single":
        return [valid_ids]
    normalized = str(mode or "auto").strip().lower()
    if normalized == "sections":
        grouped: dict[str, list[str]] = {}
        for dot_id in valid_ids:
            grouped.setdefault(str((sections or {}).get(dot_id, "Unassigned")), []).append(dot_id)
        return [group for group in grouped.values() if len(group) >= 2]
    if normalized in {"rows", "files"}:
        axis = 1 if normalized == "rows" else 0
        nearest = nearest_neighbor_distances([positions[dot_id] for dot_id in valid_ids])
        tolerance = max(0.35, median(nearest) * 0.42 if nearest else 0.75)
        ordered = sorted(valid_ids, key=lambda dot_id: (positions[dot_id][axis], positions[dot_id][1 - axis]))
        groups: list[list[str]] = []
        centers: list[float] = []
        for dot_id in ordered:
            value = positions[dot_id][axis]
            if not groups or abs(value - centers[-1]) > tolerance:
                groups.append([dot_id])
                centers.append(value)
            else:
                groups[-1].append(dot_id)
                centers[-1] = sum(positions[item][axis] for item in groups[-1]) / len(groups[-1])
        return [group for group in groups if len(group) >= 2]
    return connected_route_groups(valid_ids, positions)


def ordered_route_ids(
    dot_ids: list[str],
    positions: dict[str, Point],
    order_mode: str = "automatic",
    topology: str = "auto",
) -> tuple[list[str], bool]:
    normalized_order = str(order_mode or "automatic").strip().lower()
    normalized_topology = str(topology or "auto").strip().lower()
    if normalized_order == "roster":
        order = list(range(len(dot_ids)))
    elif normalized_order == "horizontal":
        order = sorted(
            range(len(dot_ids)),
            key=lambda index: (positions[dot_ids[index]][0], positions[dot_ids[index]][1]),
        )
    elif normalized_order == "vertical":
        order = sorted(
            range(len(dot_ids)),
            key=lambda index: (positions[dot_ids[index]][1], positions[dot_ids[index]][0]),
        )
    else:
        order = automatic_open_order([positions[dot_id] for dot_id in dot_ids])

    points = [positions[dot_ids[index]] for index in order]
    route_closed = normalized_topology == "closed"
    if normalized_topology == "auto":
        route_closed = auto_route_is_closed(points)
    if route_closed and normalized_order == "automatic":
        order = two_opt_order([positions[dot_id] for dot_id in dot_ids], order, closed=True)
    elif not route_closed and normalized_order == "automatic":
        order = two_opt_order([positions[dot_id] for dot_id in dot_ids], order, closed=False)
    return [dot_ids[index] for index in order], route_closed


def automatic_open_order(points: list[Point]) -> list[int]:
    if len(points) <= 2:
        return list(range(len(points)))
    first, second = farthest_pair(points)
    candidates = [nearest_order(points, first), nearest_order(points, second)]
    return min(candidates, key=lambda order: order_length(points, order, closed=False))


def nearest_order(points: list[Point], start_index: int) -> list[int]:
    remaining = set(range(len(points)))
    remaining.remove(start_index)
    order = [start_index]
    while remaining:
        current = order[-1]
        next_index = min(remaining, key=lambda index: (point_distance(points[current], points[index]), index))
        order.append(next_index)
        remaining.remove(next_index)
    return order


def two_opt_order(points: list[Point], order: list[int], closed: bool) -> list[int]:
    if len(order) < 4:
        return list(order)
    optimized = list(order)
    for _iteration in range(6):
        changed = False
        upper = len(optimized) if closed else len(optimized) - 1
        for first in range(upper - 1):
            for second in range(first + 2, len(optimized)):
                if closed and first == 0 and second == len(optimized) - 1:
                    continue
                first_a = optimized[first]
                first_b = optimized[first + 1]
                second_a = optimized[second]
                has_second_edge = closed or second + 1 < len(optimized)
                second_b = optimized[(second + 1) % len(optimized)] if has_second_edge else -1
                before = point_distance(points[first_a], points[first_b])
                after = point_distance(points[first_a], points[second_a])
                if has_second_edge:
                    before += point_distance(points[second_a], points[second_b])
                    after += point_distance(points[first_b], points[second_b])
                if after + 0.0001 < before:
                    optimized[first + 1 : second + 1] = reversed(optimized[first + 1 : second + 1])
                    changed = True
        if not changed:
            break
    return optimized


def auto_route_is_closed(points: list[Point]) -> bool:
    if len(points) < 4:
        return False
    adjacent = [point_distance(points[index], points[index + 1]) for index in range(len(points) - 1)]
    usable = [value for value in adjacent if value > 0.0001]
    if not usable:
        return False
    closure = point_distance(points[-1], points[0])
    typical = median(usable)
    return closure <= max(typical * 1.8, min(usable) * 2.2)


def sampled_follow_route(
    anchors: list[Point],
    curved: bool,
    closed: bool,
    samples_per_segment: int = 24,
) -> tuple[list[Point], list[float]]:
    if len(anchors) < 2:
        return list(anchors), [0.0 for _point in anchors]
    segment_count = len(anchors) if closed else len(anchors) - 1
    samples_per_segment = max(2, int(samples_per_segment))
    route: list[Point] = []
    anchor_indices: list[int] = []
    for index in range(segment_count):
        anchor_indices.append(len(route))
        p1 = anchors[index]
        p2 = anchors[(index + 1) % len(anchors)]
        if curved and len(anchors) > 2:
            p0 = anchors[(index - 1) % len(anchors)] if closed or index > 0 else extrapolated_point(p1, p2)
            p3 = (
                anchors[(index + 2) % len(anchors)]
                if closed or index + 2 < len(anchors)
                else extrapolated_point(p2, p1)
            )
            segment = [
                centripetal_catmull_rom_point(p0, p1, p2, p3, sample / samples_per_segment)
                for sample in range(samples_per_segment)
            ]
        else:
            segment = [interpolate_point(p1, p2, sample / samples_per_segment) for sample in range(samples_per_segment)]
        route.extend(segment)
    route.append(anchors[0] if closed else anchors[-1])
    cumulative = cumulative_distances(route)
    anchor_distances = [cumulative[index] for index in anchor_indices]
    if not closed:
        anchor_distances.append(cumulative[-1])
    return route, anchor_distances


def centripetal_catmull_rom_point(p0: Point, p1: Point, p2: Point, p3: Point, progress: float) -> Point:
    t0 = 0.0
    t1 = t0 + max(0.0001, point_distance(p0, p1) ** 0.5)
    t2 = t1 + max(0.0001, point_distance(p1, p2) ** 0.5)
    t3 = t2 + max(0.0001, point_distance(p2, p3) ** 0.5)
    t = t1 + (t2 - t1) * max(0.0, min(1.0, progress))
    a1 = time_interpolate(p0, p1, t0, t1, t)
    a2 = time_interpolate(p1, p2, t1, t2, t)
    a3 = time_interpolate(p2, p3, t2, t3, t)
    b1 = time_interpolate(a1, a2, t0, t2, t)
    b2 = time_interpolate(a2, a3, t1, t3, t)
    return time_interpolate(b1, b2, t1, t2, t)


def time_interpolate(first: Point, second: Point, first_time: float, second_time: float, value: float) -> Point:
    span = max(0.0001, second_time - first_time)
    ratio = (value - first_time) / span
    return interpolate_point(first, second, ratio)


def extrapolated_point(origin: Point, toward: Point) -> Point:
    return (origin[0] * 2.0 - toward[0], origin[1] * 2.0 - toward[1])


def interpolate_point(first: Point, second: Point, progress: float) -> Point:
    return (
        first[0] + (second[0] - first[0]) * progress,
        first[1] + (second[1] - first[1]) * progress,
    )


def cumulative_distances(route: list[Point]) -> list[float]:
    cumulative = [0.0]
    for index in range(1, len(route)):
        cumulative.append(cumulative[-1] + point_distance(route[index - 1], route[index]))
    return cumulative


def point_at_distance(route: list[Point], cumulative: list[float], distance_along: float, closed: bool) -> Point:
    if not route:
        return (0.0, 0.0)
    if len(route) == 1 or cumulative[-1] <= 0.0001:
        return route[0]
    total = cumulative[-1]
    target = distance_along % total if closed else distance_along
    if not closed and target < 0.0:
        tangent = unit_vector(route[1][0] - route[0][0], route[1][1] - route[0][1])
        return (route[0][0] + tangent[0] * target, route[0][1] + tangent[1] * target)
    if not closed and target > total:
        tangent = unit_vector(route[-1][0] - route[-2][0], route[-1][1] - route[-2][1])
        overflow = target - total
        return (route[-1][0] + tangent[0] * overflow, route[-1][1] + tangent[1] * overflow)
    low = 0
    high = len(cumulative) - 1
    while low < high:
        middle = (low + high) // 2
        if cumulative[middle] < target:
            low = middle + 1
        else:
            high = middle
    end_index = max(1, low)
    start_index = end_index - 1
    segment = max(0.0001, cumulative[end_index] - cumulative[start_index])
    progress = (target - cumulative[start_index]) / segment
    return interpolate_point(route[start_index], route[end_index], progress)


def facing_at_distance(
    route: list[Point],
    cumulative: list[float],
    distance_along: float,
    closed: bool,
    direction: int,
    offset: float = 0.0,
) -> float:
    epsilon = max(0.01, cumulative[-1] / max(10000.0, len(route) * 20.0))
    current = point_at_distance(route, cumulative, distance_along, closed)
    ahead = point_at_distance(route, cumulative, distance_along + epsilon * direction, closed)
    delta_x = ahead[0] - current[0]
    delta_y = ahead[1] - current[1]
    if hypot(delta_x, delta_y) <= 0.000001:
        return float(offset) % 360.0
    return (degrees(atan2(-delta_x, -delta_y)) + float(offset)) % 360.0


def route_gaps(anchor_distances: list[float], route_length: float, closed: bool) -> list[float]:
    gaps = [anchor_distances[index + 1] - anchor_distances[index] for index in range(len(anchor_distances) - 1)]
    if closed and anchor_distances:
        gaps.append(route_length - anchor_distances[-1] + anchor_distances[0])
    return gaps


def count_samples(start_count: float, end_count: float, step: float) -> list[float]:
    span = end_count - start_count
    steps = max(1, int(round(span / max(0.0001, step))))
    return [start_count + span * index / steps for index in range(steps + 1)]


def normalized_count(count: float) -> float:
    return round(float(count), 6)


def connected_route_groups(dot_ids: list[str], positions: dict[str, Point]) -> list[list[str]]:
    if len(dot_ids) <= 2:
        return [dot_ids]
    points = [positions[dot_id] for dot_id in dot_ids]
    nearest = nearest_neighbor_distances(points)
    threshold = max(2.0, median(nearest) * 2.8 if nearest else 4.0)
    remaining = set(dot_ids)
    groups: list[list[str]] = []
    while remaining:
        seed = min(remaining, key=dot_ids.index)
        queue = [seed]
        group: list[str] = []
        remaining.remove(seed)
        while queue:
            current = queue.pop()
            group.append(current)
            neighbors = [
                candidate
                for candidate in list(remaining)
                if point_distance(positions[current], positions[candidate]) <= threshold
            ]
            for candidate in neighbors:
                remaining.remove(candidate)
                queue.append(candidate)
        groups.append([dot_id for dot_id in dot_ids if dot_id in set(group)])
    usable = [group for group in groups if len(group) >= 2]
    singletons = [group[0] for group in groups if len(group) == 1]
    if singletons and usable:
        for dot_id in singletons:
            nearest_group = min(
                usable,
                key=lambda group: min(point_distance(positions[dot_id], positions[item]) for item in group),
            )
            nearest_group.append(dot_id)
    return usable or [dot_ids]


def nearest_neighbor_distances(points: list[Point]) -> list[float]:
    if len(points) < 2:
        return []
    return [
        min(point_distance(point, other) for other_index, other in enumerate(points) if other_index != index)
        for index, point in enumerate(points)
    ]


def farthest_pair(points: list[Point]) -> tuple[int, int]:
    best = (0, 1)
    best_distance = -1.0
    for first in range(len(points)):
        for second in range(first + 1, len(points)):
            current = point_distance(points[first], points[second])
            if current > best_distance:
                best = (first, second)
                best_distance = current
    return best


def order_length(points: list[Point], order: list[int], closed: bool) -> float:
    total = sum(point_distance(points[order[index]], points[order[index + 1]]) for index in range(len(order) - 1))
    if closed and len(order) > 2:
        total += point_distance(points[order[-1]], points[order[0]])
    return total


def point_distance(first: Point, second: Point) -> float:
    return hypot(second[0] - first[0], second[1] - first[1])


def unit_vector(delta_x: float, delta_y: float) -> Point:
    length = hypot(delta_x, delta_y)
    if length <= 0.000001:
        return (0.0, 0.0)
    return (delta_x / length, delta_y / length)
