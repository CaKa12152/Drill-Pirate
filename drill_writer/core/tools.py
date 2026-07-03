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


def circle_positions(
    count: int,
    center: tuple[float, float],
    radius: float,
    start_degrees: float = 0,
) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    return [
        (
            center[0] + cos((start_degrees + 360 * index / count) * pi / 180) * radius,
            center[1] + sin((start_degrees + 360 * index / count) * pi / 180) * radius,
        )
        for index in range(count)
    ]


def rectangle_positions(
    count: int,
    center: tuple[float, float],
    width: float,
    height: float,
) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    if count == 1:
        return [center]

    corners = [
        (center[0] - width / 2, center[1] - height / 2),
        (center[0] + width / 2, center[1] - height / 2),
        (center[0] + width / 2, center[1] + height / 2),
        (center[0] - width / 2, center[1] + height / 2),
        (center[0] - width / 2, center[1] - height / 2),
    ]
    path: list[tuple[float, float]] = []
    for index in range(len(corners) - 1):
        segment = line_positions(24, corners[index], corners[index + 1])
        path.extend(segment if index == 0 else segment[1:])
    return positions_along_path(path, count)


def spiral_positions(
    count: int,
    center: tuple[float, float],
    radius: float,
    turns: float,
) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    if count == 1:
        return [center]
    positions: list[tuple[float, float]] = []
    for index in range(count):
        progress = index / (count - 1)
        angle = 2 * pi * turns * progress
        current_radius = radius * progress
        positions.append(
            (
                center[0] + cos(angle) * current_radius,
                center[1] + sin(angle) * current_radius,
            )
        )
    return positions


def block_positions(
    count: int,
    center: tuple[float, float],
    columns: int,
    spacing: float,
) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    columns = max(1, min(columns, count))
    rows = (count + columns - 1) // columns
    width = (columns - 1) * spacing
    height = (rows - 1) * spacing
    positions: list[tuple[float, float]] = []
    for index in range(count):
        row = index // columns
        column = index % columns
        positions.append(
            (
                center[0] - width / 2 + column * spacing,
                center[1] + height / 2 - row * spacing,
            )
        )
    return positions


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
    shape: str = "circle",
    min_spacing: float = 1.6,
) -> list[tuple[float, float]]:
    if not positions:
        return []
    center = (
        sum(x for x, _y in positions) / len(positions),
        sum(y for _x, y in positions) / len(positions),
    )
    return organized_scatter_positions(
        len(positions),
        center,
        max(radius, required_scatter_radius(len(positions), min_spacing, shape)),
        seed,
        shape,
        min_spacing,
    )


def organized_scatter_positions(
    count: int,
    center: tuple[float, float],
    radius: float,
    seed: int = 42,
    shape: str = "circle",
    min_spacing: float = 1.6,
) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    random = Random(seed)
    shape = shape.lower()
    if shape == "circle":
        return scatter_circle_positions(count, center, radius, random, min_spacing)
    if shape == "square":
        return scatter_rect_positions(count, center, radius * 2, radius * 2, random, min_spacing)
    return scatter_rect_positions(count, center, radius * 2.4, radius * 1.45, random, min_spacing)


def required_scatter_radius(count: int, min_spacing: float, shape: str) -> float:
    if shape.lower() == "circle":
        return max(4.0, (count * min_spacing * min_spacing / pi) ** 0.5 * 0.95)
    if shape.lower() == "square":
        return max(4.0, ((count**0.5) * min_spacing) / 2)
    return max(5.0, ((count**0.5) * min_spacing) / 1.8)


def scatter_circle_positions(
    count: int,
    center: tuple[float, float],
    radius: float,
    random: Random,
    min_spacing: float,
) -> list[tuple[float, float]]:
    positions: list[tuple[float, float]] = []
    ring_spacing = max(min_spacing, 1.2)
    rings = max(1, int(radius / ring_spacing))
    for ring in range(rings + 1):
        ring_radius = radius * ring / max(1, rings)
        capacity = 1 if ring == 0 else max(6, int(2 * pi * ring_radius / min_spacing))
        angle_offset = random.random() * 2 * pi
        for slot in range(capacity):
            if len(positions) >= count:
                break
            jitter_radius = random.uniform(-0.22, 0.22) * min_spacing
            jitter_angle = random.uniform(-0.2, 0.2)
            angle = angle_offset + 2 * pi * slot / capacity + jitter_angle
            current_radius = max(0, min(radius, ring_radius + jitter_radius))
            positions.append(
                (
                    center[0] + cos(angle) * current_radius,
                    center[1] + sin(angle) * current_radius,
                )
            )
        if len(positions) >= count:
            break
    while len(positions) < count:
        ring_radius = radius + ring_spacing * (1 + (len(positions) - count) / max(1, count))
        capacity = max(6, int(2 * pi * abs(ring_radius) / min_spacing))
        angle_offset = random.random() * 2 * pi
        for slot in range(capacity):
            if len(positions) >= count:
                break
            angle = angle_offset + 2 * pi * slot / capacity + random.uniform(-0.16, 0.16)
            current_radius = abs(ring_radius) + random.uniform(-0.2, 0.2) * min_spacing
            positions.append(
                (
                    center[0] + cos(angle) * current_radius,
                    center[1] + sin(angle) * current_radius,
                )
            )
    return relax_spacing(positions, min_spacing, center)


def scatter_rect_positions(
    count: int,
    center: tuple[float, float],
    width: float,
    height: float,
    random: Random,
    min_spacing: float,
) -> list[tuple[float, float]]:
    columns = max(1, int(width / min_spacing))
    rows = max(1, (count + columns - 1) // columns)
    height = max(height, rows * min_spacing)
    positions: list[tuple[float, float]] = []
    for row in range(rows):
        for column in range(columns):
            if len(positions) >= count:
                break
            base_x = center[0] - width / 2 + (column + 0.5) * width / columns
            base_y = center[1] - height / 2 + (row + 0.5) * height / rows
            positions.append(
                (
                    base_x + random.uniform(-0.24, 0.24) * min_spacing,
                    base_y + random.uniform(-0.24, 0.24) * min_spacing,
                )
            )
        if len(positions) >= count:
            break
    return relax_spacing(positions, min_spacing, center)


def relax_spacing(
    positions: list[tuple[float, float]],
    min_spacing: float,
    center: tuple[float, float],
    iterations: int = 10,
) -> list[tuple[float, float]]:
    relaxed = list(positions)
    for _iteration in range(iterations):
        offsets = [(0.0, 0.0) for _point in relaxed]
        for first in range(len(relaxed)):
            for second in range(first + 1, len(relaxed)):
                dx = relaxed[first][0] - relaxed[second][0]
                dy = relaxed[first][1] - relaxed[second][1]
                current_distance = (dx * dx + dy * dy) ** 0.5
                if 0.001 < current_distance < min_spacing:
                    push = (min_spacing - current_distance) / current_distance * 0.5
                    offsets[first] = (offsets[first][0] + dx * push, offsets[first][1] + dy * push)
                    offsets[second] = (offsets[second][0] - dx * push, offsets[second][1] - dy * push)
        relaxed = [
            (
                x + offset[0] * 0.55 - (x - center[0]) * 0.01,
                y + offset[1] * 0.55 - (y - center[1]) * 0.01,
            )
            for (x, y), offset in zip(relaxed, offsets)
        ]
    return relaxed


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
    cleaned_path = clean_path_points(path)
    if len(cleaned_path) <= 1:
        return cleaned_path * count
    if count == 1:
        return [cleaned_path[0]]

    is_closed = path_is_closed(path)
    sample_path = cleaned_path

    segment_lengths = [
        distance(sample_path[index], sample_path[(index + 1) % len(sample_path)])
        for index in range(len(sample_path) if is_closed else len(sample_path) - 1)
    ]
    total_length = sum(segment_lengths)
    if total_length == 0:
        return [sample_path[0] for _index in range(count)]

    placed: list[tuple[float, float]] = []
    segment_index = 0
    distance_before_segment = 0.0
    for slot_index in range(count):
        target_distance = total_length * slot_index / (count if is_closed else count - 1)
        while (
            segment_index < len(segment_lengths) - 1
            and distance_before_segment + segment_lengths[segment_index] < target_distance
        ):
            distance_before_segment += segment_lengths[segment_index]
            segment_index += 1
        segment_length = segment_lengths[segment_index] or 1
        local_t = (target_distance - distance_before_segment) / segment_length
        start = sample_path[segment_index]
        end = sample_path[(segment_index + 1) % len(sample_path)]
        placed.append(
            (
                start[0] + (end[0] - start[0]) * local_t,
                start[1] + (end[1] - start[1]) * local_t,
            )
        )
    return placed


def clean_path_points(
    path: list[tuple[float, float]],
    tolerance: float = 0.0001,
) -> list[tuple[float, float]]:
    cleaned: list[tuple[float, float]] = []
    for point in path:
        if not cleaned or distance(cleaned[-1], point) > tolerance:
            cleaned.append(point)
    if len(cleaned) > 1 and distance(cleaned[0], cleaned[-1]) <= tolerance:
        cleaned.pop()
    return cleaned


def path_is_closed(
    path: list[tuple[float, float]],
    tolerance: float = 0.0001,
) -> bool:
    return len(path) > 2 and distance(path[0], path[-1]) <= tolerance


def positions_along_paths(
    paths: list[list[tuple[float, float]]],
    count: int,
) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    usable_paths = [path for path in paths if len(path) > 1]
    if not usable_paths:
        single_points = [path[0] for path in paths if path]
        if not single_points:
            return []
        return [single_points[index % len(single_points)] for index in range(count)]
    if len(usable_paths) == 1:
        return positions_along_path(usable_paths[0], count)

    lengths = [path_length(path) for path in usable_paths]
    total_length = sum(lengths)
    if total_length <= 0:
        return [usable_paths[0][0] for _index in range(count)]

    allocations = [0 for _path in usable_paths]
    if count >= len(usable_paths):
        allocations = [1 for _path in usable_paths]
        remaining = count - len(usable_paths)
    else:
        ranked = sorted(range(len(usable_paths)), key=lambda index: lengths[index], reverse=True)
        for index in ranked[:count]:
            allocations[index] = 1
        remaining = 0

    raw_extra = [
        (length / total_length) * remaining
        for length in lengths
    ]
    for index, value in enumerate(raw_extra):
        whole = int(value)
        allocations[index] += whole
        remaining -= whole

    remainders = sorted(
        range(len(usable_paths)),
        key=lambda index: raw_extra[index] - int(raw_extra[index]),
        reverse=True,
    )
    for index in remainders[:remaining]:
        allocations[index] += 1

    placed: list[tuple[float, float]] = []
    for path, allocation in zip(usable_paths, allocations):
        if allocation > 0:
            placed.extend(positions_along_path(path, allocation))
    return placed[:count]


def path_length(path: list[tuple[float, float]]) -> float:
    cleaned_path = clean_path_points(path)
    if len(cleaned_path) <= 1:
        return 0.0
    is_closed = path_is_closed(path)
    return sum(
        distance(cleaned_path[index], cleaned_path[(index + 1) % len(cleaned_path)])
        for index in range(len(cleaned_path) if is_closed else len(cleaned_path) - 1)
    )


def conveyor_follow_positions(
    positions: list[tuple[float, float]],
    shift_degrees: float,
) -> tuple[list[tuple[float, float]], list[list[tuple[float, float]]]]:
    if len(positions) < 2:
        return list(positions), [[] for _position in positions]

    shifted_positions = list(positions)
    anchors_by_index: list[list[tuple[float, float]]] = [[] for _position in positions]
    shift_fraction = shift_degrees / 360
    if abs(shift_fraction) < 0.0001:
        return shifted_positions, anchors_by_index

    for cluster in outline_clusters(positions):
        if len(cluster) < 2:
            continue
        order = ordered_closed_outline_indices(positions, cluster)
        contour = [positions[index] for index in order]
        perimeter = closed_path_length(contour)
        if perimeter <= 0.001:
            continue
        shift_distance = perimeter * shift_fraction
        average_spacing = perimeter / max(1, len(contour))
        anchor_count = max(1, min(8, int(abs(shift_distance) / max(2.0, average_spacing * 0.9)) + 1))
        for index in order:
            distance_along = distance_along_closed_path(contour, positions[index])
            shifted_positions[index] = point_on_closed_path(contour, distance_along + shift_distance)
            anchors_by_index[index] = sample_closed_path_between(
                contour,
                distance_along,
                shift_distance,
                anchor_count,
            )

    return shifted_positions, anchors_by_index


def outline_clusters(positions: list[tuple[float, float]]) -> list[list[int]]:
    if len(positions) <= 2:
        return [list(range(len(positions)))]

    nearest_distances = []
    for index, point in enumerate(positions):
        nearest_distances.append(
            min(
                distance(point, other)
                for other_index, other in enumerate(positions)
                if other_index != index
            )
        )
    sorted_nearest = sorted(nearest_distances)
    median_nearest = sorted_nearest[len(sorted_nearest) // 2]
    threshold = max(4.0, median_nearest * 3.25)

    parents = list(range(len(positions)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        root_a = find(first)
        root_b = find(second)
        if root_a != root_b:
            parents[root_b] = root_a

    for first in range(len(positions)):
        for second in range(first + 1, len(positions)):
            if distance(positions[first], positions[second]) <= threshold:
                union(first, second)

    groups: dict[int, list[int]] = {}
    for index in range(len(positions)):
        groups.setdefault(find(index), []).append(index)
    return sorted(groups.values(), key=lambda group: (-len(group), min(group)))


def ordered_closed_outline_indices(
    positions: list[tuple[float, float]],
    indices: list[int],
) -> list[int]:
    if len(indices) <= 2:
        return list(indices)

    remaining = set(indices)
    current = min(indices, key=lambda index: (positions[index][0], positions[index][1]))
    order = [current]
    remaining.remove(current)
    while remaining:
        current = min(remaining, key=lambda index: distance(positions[current], positions[index]))
        order.append(current)
        remaining.remove(current)

    return two_opt_closed_order(positions, order)


def two_opt_closed_order(
    positions: list[tuple[float, float]],
    order: list[int],
) -> list[int]:
    if len(order) < 4:
        return order
    optimized = list(order)
    for _iteration in range(4):
        changed = False
        for first in range(len(optimized) - 2):
            for second in range(first + 2, len(optimized)):
                if first == 0 and second == len(optimized) - 1:
                    continue
                a = optimized[first]
                b = optimized[(first + 1) % len(optimized)]
                c = optimized[second]
                d = optimized[(second + 1) % len(optimized)]
                current = distance(positions[a], positions[b]) + distance(positions[c], positions[d])
                swapped = distance(positions[a], positions[c]) + distance(positions[b], positions[d])
                if swapped + 0.01 < current:
                    optimized[first + 1 : second + 1] = reversed(optimized[first + 1 : second + 1])
                    changed = True
        if not changed:
            break
    return optimized


def closed_path_length(path: list[tuple[float, float]]) -> float:
    if len(path) <= 1:
        return 0.0
    return path_length(path) + distance(path[-1], path[0])


def point_on_closed_path(
    path: list[tuple[float, float]],
    distance_along: float,
) -> tuple[float, float]:
    if not path:
        return (0.0, 0.0)
    if len(path) == 1:
        return path[0]
    perimeter = closed_path_length(path)
    if perimeter <= 0.001:
        return path[0]
    target = distance_along % perimeter
    walked = 0.0
    for index in range(len(path)):
        start = path[index]
        end = path[(index + 1) % len(path)]
        segment_length = distance(start, end)
        if segment_length <= 0.001:
            continue
        if walked + segment_length >= target:
            local_t = (target - walked) / segment_length
            return (
                start[0] + (end[0] - start[0]) * local_t,
                start[1] + (end[1] - start[1]) * local_t,
            )
        walked += segment_length
    return path[-1]


def distance_along_closed_path(
    path: list[tuple[float, float]],
    point: tuple[float, float],
) -> float:
    if len(path) <= 1:
        return 0.0
    best_distance = float("inf")
    best_along = 0.0
    walked = 0.0
    for index in range(len(path)):
        start = path[index]
        end = path[(index + 1) % len(path)]
        segment_length = distance(start, end)
        if segment_length <= 0.001:
            continue
        projection = project_point_to_segment(point, start, end)
        current_distance = distance(point, projection)
        if current_distance < best_distance:
            best_distance = current_distance
            best_along = walked + distance(start, projection)
        walked += segment_length
    return best_along


def project_point_to_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[float, float]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared <= 0.001:
        return start
    t = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared
    t = max(0.0, min(1.0, t))
    return (start[0] + dx * t, start[1] + dy * t)


def sample_closed_path_between(
    path: list[tuple[float, float]],
    start_distance: float,
    shift_distance: float,
    anchor_count: int,
) -> list[tuple[float, float]]:
    if anchor_count <= 0 or len(path) <= 1 or abs(shift_distance) <= 0.001:
        return []
    return [
        point_on_closed_path(path, start_distance + shift_distance * step / (anchor_count + 1))
        for step in range(1, anchor_count + 1)
    ]
