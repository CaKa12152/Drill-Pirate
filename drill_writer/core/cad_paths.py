from __future__ import annotations

from math import acos, hypot, pi


Point = tuple[float, float]


def clean_path(path: list[Point], tolerance: float = 0.0001) -> list[Point]:
    cleaned: list[Point] = []
    for point in path:
        normalized = (float(point[0]), float(point[1]))
        if not cleaned or point_distance(cleaned[-1], normalized) > tolerance:
            cleaned.append(normalized)
    return cleaned


def cumulative_distances(path: list[Point]) -> list[float]:
    cleaned = clean_path(path)
    if not cleaned:
        return []
    cumulative = [0.0]
    for index in range(1, len(cleaned)):
        cumulative.append(cumulative[-1] + point_distance(cleaned[index - 1], cleaned[index]))
    return cumulative


def path_length(path: list[Point]) -> float:
    cumulative = cumulative_distances(path)
    return cumulative[-1] if cumulative else 0.0


def point_at_distance(path: list[Point], distance_along: float) -> Point:
    cleaned = clean_path(path)
    if not cleaned:
        return (0.0, 0.0)
    if len(cleaned) == 1:
        return cleaned[0]
    cumulative = cumulative_distances(cleaned)
    target = max(0.0, min(float(distance_along), cumulative[-1]))
    for index in range(1, len(cumulative)):
        if cumulative[index] + 0.000001 < target:
            continue
        span = max(0.000001, cumulative[index] - cumulative[index - 1])
        progress = (target - cumulative[index - 1]) / span
        return interpolate(cleaned[index - 1], cleaned[index], progress)
    return cleaned[-1]


def cad_join(paths: list[list[Point]], tolerance: float = 0.5) -> list[Point]:
    remaining = [clean_path(path) for path in paths if clean_path(path)]
    if not remaining:
        return []
    joined = remaining.pop(0)
    while remaining:
        candidates: list[tuple[float, int, bool, bool]] = []
        for index, path in enumerate(remaining):
            candidates.extend(
                [
                    (point_distance(joined[-1], path[0]), index, False, False),
                    (point_distance(joined[-1], path[-1]), index, True, False),
                    (point_distance(joined[0], path[-1]), index, False, True),
                    (point_distance(joined[0], path[0]), index, True, True),
                ]
            )
        gap, path_index, reverse_path, prepend = min(candidates, key=lambda item: item[0])
        next_path = remaining.pop(path_index)
        if reverse_path:
            next_path.reverse()
        if prepend:
            prefix = next_path[:-1] if gap <= tolerance else next_path
            joined = [*prefix, *joined]
        else:
            joined.extend(next_path[1:] if gap <= tolerance else next_path)
    return clean_path(joined)


def cad_split(path: list[Point], fraction: float = 0.5) -> tuple[list[Point], list[Point]]:
    cleaned = clean_path(path)
    if len(cleaned) < 2:
        return cleaned, []
    cumulative = cumulative_distances(cleaned)
    split_distance = cumulative[-1] * max(0.0, min(1.0, float(fraction)))
    split_point = point_at_distance(cleaned, split_distance)
    first = [point for point, distance in zip(cleaned, cumulative) if distance < split_distance]
    second = [point for point, distance in zip(cleaned, cumulative) if distance > split_distance]
    return clean_path([*first, split_point]), clean_path([split_point, *second])


def cad_trim(path: list[Point], start_fraction: float = 0.0, end_fraction: float = 1.0) -> list[Point]:
    cleaned = clean_path(path)
    if len(cleaned) < 2:
        return cleaned
    start = max(0.0, min(1.0, float(start_fraction)))
    end = max(start, min(1.0, float(end_fraction)))
    cumulative = cumulative_distances(cleaned)
    total = cumulative[-1]
    start_distance = total * start
    end_distance = total * end
    interior = [
        point
        for point, distance in zip(cleaned, cumulative)
        if start_distance < distance < end_distance
    ]
    return clean_path(
        [
            point_at_distance(cleaned, start_distance),
            *interior,
            point_at_distance(cleaned, end_distance),
        ]
    )


def cad_extend(path: list[Point], start_distance: float = 0.0, end_distance: float = 0.0) -> list[Point]:
    cleaned = clean_path(path)
    if len(cleaned) < 2:
        return cleaned
    result = list(cleaned)
    if start_distance > 0:
        tangent = unit_vector(
            cleaned[0][0] - cleaned[1][0],
            cleaned[0][1] - cleaned[1][1],
        )
        result.insert(
            0,
            (
                cleaned[0][0] + tangent[0] * start_distance,
                cleaned[0][1] + tangent[1] * start_distance,
            ),
        )
    if end_distance > 0:
        tangent = unit_vector(
            cleaned[-1][0] - cleaned[-2][0],
            cleaned[-1][1] - cleaned[-2][1],
        )
        result.append(
            (
                cleaned[-1][0] + tangent[0] * end_distance,
                cleaned[-1][1] + tangent[1] * end_distance,
            )
        )
    return clean_path(result)


def cad_offset(path: list[Point], distance: float, closed: bool = False) -> list[Point]:
    cleaned = clean_path(path)
    if len(cleaned) < 2 or abs(distance) <= 0.000001:
        return cleaned
    count = len(cleaned)
    normals: list[Point] = []
    for index in range(count):
        if closed:
            previous = cleaned[(index - 1) % count]
            following = cleaned[(index + 1) % count]
        elif index == 0:
            previous, following = cleaned[0], cleaned[1]
        elif index == count - 1:
            previous, following = cleaned[-2], cleaned[-1]
        else:
            previous, following = cleaned[index - 1], cleaned[index + 1]
        tangent = unit_vector(following[0] - previous[0], following[1] - previous[1])
        normals.append((-tangent[1], tangent[0]))
    return [
        (point[0] + normal[0] * distance, point[1] + normal[1] * distance)
        for point, normal in zip(cleaned, normals)
    ]


def cad_simplify(path: list[Point], tolerance: float = 0.25) -> list[Point]:
    cleaned = clean_path(path)
    if len(cleaned) <= 2:
        return cleaned

    first = cleaned[0]
    last = cleaned[-1]
    max_distance = 0.0
    split_index = 0
    for index in range(1, len(cleaned) - 1):
        current = point_segment_distance(cleaned[index], first, last)
        if current > max_distance:
            max_distance = current
            split_index = index
    if max_distance <= max(0.0001, tolerance):
        return [first, last]
    left = cad_simplify(cleaned[: split_index + 1], tolerance)
    right = cad_simplify(cleaned[split_index:], tolerance)
    return [*left[:-1], *right]


def cad_smooth(path: list[Point], iterations: int = 2, closed: bool = False) -> list[Point]:
    result = clean_path(path)
    for _iteration in range(max(0, min(6, int(iterations)))):
        if len(result) < 3:
            break
        smoothed: list[Point] = [] if closed else [result[0]]
        segment_count = len(result) if closed else len(result) - 1
        for index in range(segment_count):
            first = result[index]
            second = result[(index + 1) % len(result)]
            smoothed.append(interpolate(first, second, 0.25))
            smoothed.append(interpolate(first, second, 0.75))
        if not closed:
            smoothed.append(result[-1])
        result = clean_path(smoothed)
    return result


def cad_reverse(path: list[Point]) -> list[Point]:
    return list(reversed(clean_path(path)))


def cad_fillet(
    path: list[Point],
    radius: float = 1.0,
    samples_per_corner: int = 5,
    closed: bool = False,
) -> list[Point]:
    cleaned = clean_path(path)
    if len(cleaned) < 3 or radius <= 0:
        return cleaned
    result: list[Point] = []
    indices = range(len(cleaned)) if closed else range(1, len(cleaned) - 1)
    if not closed:
        result.append(cleaned[0])
    for index in indices:
        previous = cleaned[(index - 1) % len(cleaned)]
        corner = cleaned[index]
        following = cleaned[(index + 1) % len(cleaned)]
        incoming = unit_vector(previous[0] - corner[0], previous[1] - corner[1])
        outgoing = unit_vector(following[0] - corner[0], following[1] - corner[1])
        dot = max(-1.0, min(1.0, incoming[0] * outgoing[0] + incoming[1] * outgoing[1]))
        angle = acos(dot)
        if angle <= 0.01 or abs(pi - angle) <= 0.01:
            result.append(corner)
            continue
        trim = min(
            float(radius),
            point_distance(previous, corner) * 0.45,
            point_distance(corner, following) * 0.45,
        )
        entry = (corner[0] + incoming[0] * trim, corner[1] + incoming[1] * trim)
        exit_point = (corner[0] + outgoing[0] * trim, corner[1] + outgoing[1] * trim)
        result.append(entry)
        for sample in range(1, max(2, samples_per_corner)):
            progress = sample / max(2, samples_per_corner)
            result.append(quadratic_bezier(entry, corner, exit_point, progress))
        result.append(exit_point)
    if not closed:
        result.append(cleaned[-1])
    return clean_path(result)


def path_to_bezier_nodes(path: list[Point]) -> list[dict[str, Point]]:
    cleaned = clean_path(path)
    if not cleaned:
        return []
    nodes: list[dict[str, Point]] = []
    for index, point in enumerate(cleaned):
        previous = cleaned[max(0, index - 1)]
        following = cleaned[min(len(cleaned) - 1, index + 1)]
        tangent = ((following[0] - previous[0]) / 6.0, (following[1] - previous[1]) / 6.0)
        nodes.append(
            {
                "point": point,
                "in": (point[0] - tangent[0], point[1] - tangent[1]),
                "out": (point[0] + tangent[0], point[1] + tangent[1]),
            }
        )
    return nodes


def point_segment_distance(point: Point, start: Point, end: Point) -> float:
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    length_squared = delta_x * delta_x + delta_y * delta_y
    if length_squared <= 0.000001:
        return point_distance(point, start)
    progress = (
        (point[0] - start[0]) * delta_x + (point[1] - start[1]) * delta_y
    ) / length_squared
    progress = max(0.0, min(1.0, progress))
    projection = (start[0] + delta_x * progress, start[1] + delta_y * progress)
    return point_distance(point, projection)


def quadratic_bezier(start: Point, control: Point, end: Point, progress: float) -> Point:
    inverse = 1.0 - progress
    return (
        inverse * inverse * start[0]
        + 2.0 * inverse * progress * control[0]
        + progress * progress * end[0],
        inverse * inverse * start[1]
        + 2.0 * inverse * progress * control[1]
        + progress * progress * end[1],
    )


def interpolate(first: Point, second: Point, progress: float) -> Point:
    return (
        first[0] + (second[0] - first[0]) * progress,
        first[1] + (second[1] - first[1]) * progress,
    )


def point_distance(first: Point, second: Point) -> float:
    return hypot(second[0] - first[0], second[1] - first[1])


def unit_vector(delta_x: float, delta_y: float) -> Point:
    length = hypot(delta_x, delta_y)
    if length <= 0.000001:
        return (0.0, 0.0)
    return (delta_x / length, delta_y / length)
