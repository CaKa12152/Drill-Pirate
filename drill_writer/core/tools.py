from __future__ import annotations

from math import atan2, cos, pi, radians, sin
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


def elliptical_arc_path(
    center: tuple[float, float],
    width: float,
    height: float,
    start_degrees: float,
    sweep_degrees: float,
    rotation_degrees: float = 0.0,
    samples: int = 160,
) -> list[tuple[float, float]]:
    radius_x = max(0.05, width / 2)
    radius_y = max(0.05, height / 2)
    sample_count = max(2, samples)
    rotation = radians(rotation_degrees)
    cos_rotation = cos(rotation)
    sin_rotation = sin(rotation)
    path: list[tuple[float, float]] = []
    for index in range(sample_count):
        progress = index / max(1, sample_count - 1)
        angle = radians(start_degrees + sweep_degrees * progress)
        local_x = cos(angle) * radius_x
        local_y = sin(angle) * radius_y
        path.append(
            (
                center[0] + local_x * cos_rotation - local_y * sin_rotation,
                center[1] + local_x * sin_rotation + local_y * cos_rotation,
            )
        )
    return path


def elliptical_arc_positions(
    count: int,
    center: tuple[float, float],
    width: float,
    height: float,
    start_degrees: float,
    sweep_degrees: float,
    rotation_degrees: float = 0.0,
) -> list[tuple[float, float]]:
    return positions_along_path(
        elliptical_arc_path(center, width, height, start_degrees, sweep_degrees, rotation_degrees),
        count,
    )


def circle_positions(
    count: int,
    center: tuple[float, float],
    radius: float,
    start_degrees: float = 0,
    filled: bool = False,
) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    if filled:
        return solid_ellipse_positions(count, center, radius * 2, radius * 2)
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
    filled: bool = False,
) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    if count == 1:
        return [center]
    if filled:
        return solid_rectangle_positions(count, center, width, height)

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


def ellipse_positions(
    count: int,
    center: tuple[float, float],
    width: float,
    height: float,
    start_degrees: float = 0,
    filled: bool = False,
) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    if filled:
        return solid_ellipse_positions(count, center, width, height)
    radius_x = width / 2
    radius_y = height / 2
    return [
        (
            center[0] + cos((start_degrees + 360 * index / count) * pi / 180) * radius_x,
            center[1] + sin((start_degrees + 360 * index / count) * pi / 180) * radius_y,
        )
        for index in range(count)
    ]


def triangle_positions(
    count: int,
    center: tuple[float, float],
    width: float,
    height: float,
    filled: bool = False,
) -> list[tuple[float, float]]:
    points = [
        (center[0], center[1] - height / 2),
        (center[0] + width / 2, center[1] + height / 2),
        (center[0] - width / 2, center[1] + height / 2),
        (center[0], center[1] - height / 2),
    ]
    if filled:
        return solid_polygon_positions(count, points[:-1])
    return positions_along_path(points, count)


def polygon_positions(
    count: int,
    center: tuple[float, float],
    radius: float,
    sides: int,
    rotation_degrees: float = -90,
    filled: bool = False,
) -> list[tuple[float, float]]:
    sides = max(3, sides)
    points = regular_polygon_points(center, radius, sides, rotation_degrees)
    if filled:
        return solid_polygon_positions(count, points)
    return positions_along_path(points + [points[0]], count)


def star_positions(
    count: int,
    center: tuple[float, float],
    outer_radius: float,
    inner_radius: float,
    points: int,
    rotation_degrees: float = -90,
    filled: bool = False,
) -> list[tuple[float, float]]:
    points = max(3, points)
    vertices: list[tuple[float, float]] = []
    for index in range(points * 2):
        radius = outer_radius if index % 2 == 0 else inner_radius
        angle = radians(rotation_degrees + 360 * index / (points * 2))
        vertices.append((center[0] + cos(angle) * radius, center[1] + sin(angle) * radius))
    if filled:
        return solid_polygon_positions(count, vertices)
    return positions_along_path(vertices + [vertices[0]], count)


def regular_polygon_points(
    center: tuple[float, float],
    radius: float,
    sides: int,
    rotation_degrees: float = -90,
) -> list[tuple[float, float]]:
    return [
        (
            center[0] + cos(radians(rotation_degrees + 360 * index / sides)) * radius,
            center[1] + sin(radians(rotation_degrees + 360 * index / sides)) * radius,
        )
        for index in range(sides)
    ]


def solid_rectangle_positions(
    count: int,
    center: tuple[float, float],
    width: float,
    height: float,
) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    columns, rows = balanced_grid_dimensions(count, max(width, 0.1), max(height, 0.1))
    positions: list[tuple[float, float]] = []
    for row in range(rows):
        y = center[1] if rows == 1 else center[1] - height / 2 + height * row / (rows - 1)
        for column in range(columns):
            if len(positions) >= count:
                break
            x = center[0] if columns == 1 else center[0] - width / 2 + width * column / (columns - 1)
            positions.append((x, y))
    return positions


def solid_ellipse_positions(
    count: int,
    center: tuple[float, float],
    width: float,
    height: float,
) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    if count == 1:
        return [center]
    positions = [center]
    radius_x = max(0.1, width / 2)
    radius_y = max(0.1, height / 2)
    ring_count = max(1, int(count**0.5))
    for ring in range(1, ring_count + 1):
        ring_radius = ring / ring_count
        capacity = max(6, round(2 * pi * max(radius_x, radius_y) * ring_radius / max(1.2, min(width, height) / max(1, count**0.5))))
        for slot in range(capacity):
            if len(positions) >= count:
                return positions
            angle = 2 * pi * slot / capacity + (ring % 2) * pi / capacity
            positions.append((center[0] + cos(angle) * radius_x * ring_radius, center[1] + sin(angle) * radius_y * ring_radius))
    while len(positions) < count:
        angle = 2 * pi * len(positions) / count
        positions.append((center[0] + cos(angle) * radius_x, center[1] + sin(angle) * radius_y))
    return positions


def solid_polygon_positions(
    count: int,
    polygon: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    if not polygon:
        return []
    if count == 1:
        return [polygon_center(polygon)]
    min_x = min(x for x, _y in polygon)
    max_x = max(x for x, _y in polygon)
    min_y = min(y for _x, y in polygon)
    max_y = max(y for _x, y in polygon)
    width = max(0.1, max_x - min_x)
    height = max(0.1, max_y - min_y)
    columns, rows = balanced_grid_dimensions(max(count * 3, count + 8), width, height)
    candidates: list[tuple[float, float]] = []
    for row in range(rows):
        y = min_y + height * (row + 0.5) / rows
        row_offset = 0.5 if row % 2 else 0.0
        for column in range(columns):
            x = min_x + width * (column + 0.5 + row_offset * 0.35) / columns
            if point_in_polygon((x, y), polygon):
                candidates.append((x, y))
    if len(candidates) < count:
        candidates.extend(positions_along_path(polygon + [polygon[0]], count - len(candidates)))
    center = polygon_center(polygon)
    candidates.sort(key=lambda point: (distance(point, center), atan2(point[1] - center[1], point[0] - center[0])))
    if len(candidates) >= count:
        step = len(candidates) / count
        return [candidates[min(len(candidates) - 1, int(index * step))] for index in range(count)]
    return candidates[:count]


def solid_paths_positions(
    paths: list[list[tuple[float, float]]],
    count: int,
) -> list[tuple[float, float]]:
    closed_paths = [clean_path_points(path) for path in paths if path_is_closed(path) and len(clean_path_points(path)) >= 3]
    if not closed_paths:
        return positions_along_paths(paths, count)
    largest = max(closed_paths, key=lambda path: abs(polygon_area(path)))
    return solid_polygon_positions(count, largest)


def balanced_grid_dimensions(count: int, width: float, height: float) -> tuple[int, int]:
    aspect = max(0.1, width) / max(0.1, height)
    columns = max(1, round((count * aspect) ** 0.5))
    rows = max(1, (count + columns - 1) // columns)
    while columns * rows < count:
        columns += 1
    return columns, rows


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    previous_x, previous_y = polygon[-1]
    for current_x, current_y in polygon:
        if ((current_y > y) != (previous_y > y)) and (
            x < (previous_x - current_x) * (y - current_y) / ((previous_y - current_y) or 1e-9) + current_x
        ):
            inside = not inside
        previous_x, previous_y = current_x, current_y
    return inside


def polygon_center(polygon: list[tuple[float, float]]) -> tuple[float, float]:
    return (
        sum(x for x, _y in polygon) / len(polygon),
        sum(y for _x, y in polygon) / len(polygon),
    )


def polygon_area(polygon: list[tuple[float, float]]) -> float:
    if len(polygon) < 3:
        return 0.0
    return sum(
        polygon[index][0] * polygon[(index + 1) % len(polygon)][1]
        - polygon[(index + 1) % len(polygon)][0] * polygon[index][1]
        for index in range(len(polygon))
    ) / 2


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


def cubic_bezier_point(
    start: tuple[float, float],
    control_1: tuple[float, float],
    control_2: tuple[float, float],
    end: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    inverse = 1 - t
    return (
        inverse**3 * start[0]
        + 3 * inverse * inverse * t * control_1[0]
        + 3 * inverse * t * t * control_2[0]
        + t**3 * end[0],
        inverse**3 * start[1]
        + 3 * inverse * inverse * t * control_1[1]
        + 3 * inverse * t * t * control_2[1]
        + t**3 * end[1],
    )


def sampled_cubic_bezier_path(
    start: tuple[float, float],
    control_1: tuple[float, float],
    control_2: tuple[float, float],
    end: tuple[float, float],
    samples: int = 160,
) -> list[tuple[float, float]]:
    sample_count = max(2, samples)
    return [
        cubic_bezier_point(start, control_1, control_2, end, index / max(1, sample_count - 1))
        for index in range(sample_count)
    ]


def bezier_curve_positions(
    count: int,
    start: tuple[float, float],
    control_1: tuple[float, float],
    control_2: tuple[float, float],
    end: tuple[float, float],
) -> list[tuple[float, float]]:
    return positions_along_path(
        sampled_cubic_bezier_path(start, control_1, control_2, end),
        count,
    )


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
    width = max(width, min_spacing)
    height = max(height, min_spacing)
    positions = blue_noise_rect_positions(count, center, width, height, random, min_spacing)
    return relax_spacing_in_rect(positions, min_spacing, center, width, height)


def blue_noise_rect_positions(
    count: int,
    center: tuple[float, float],
    width: float,
    height: float,
    random: Random,
    min_spacing: float,
) -> list[tuple[float, float]]:
    if count <= 0:
        return []

    left = center[0] - width / 2
    bottom = center[1] - height / 2
    spacing = max(0.05, min_spacing * 0.82)
    cell_size = max(0.05, spacing / 1.41421356237)
    columns = max(1, int(width / cell_size) + 1)
    rows = max(1, int(height / cell_size) + 1)
    grid: list[list[int | None]] = [[None for _column in range(columns)] for _row in range(rows)]
    positions: list[tuple[float, float]] = []

    def grid_cell(point: tuple[float, float]) -> tuple[int, int]:
        return (
            max(0, min(columns - 1, int((point[0] - left) / cell_size))),
            max(0, min(rows - 1, int((point[1] - bottom) / cell_size))),
        )

    def allowed(point: tuple[float, float]) -> bool:
        column, row = grid_cell(point)
        for nearby_row in range(max(0, row - 2), min(rows, row + 3)):
            for nearby_column in range(max(0, column - 2), min(columns, column + 3)):
                existing_index = grid[nearby_row][nearby_column]
                if existing_index is None:
                    continue
                if distance(point, positions[existing_index]) < spacing:
                    return False
        return True

    attempts = max(400, count * 85)
    while len(positions) < count and attempts > 0:
        attempts -= 1
        candidate = (
            left + random.random() * width,
            bottom + random.random() * height,
        )
        if not allowed(candidate):
            continue
        column, row = grid_cell(candidate)
        grid[row][column] = len(positions)
        positions.append(candidate)

    while len(positions) < count:
        best_candidate = (
            left + random.random() * width,
            bottom + random.random() * height,
        )
        best_distance = -1.0
        for _sample in range(32):
            candidate = (
                left + random.random() * width,
                bottom + random.random() * height,
            )
            nearest = min((distance(candidate, point) for point in positions), default=spacing)
            if nearest > best_distance:
                best_candidate = candidate
                best_distance = nearest
        positions.append(best_candidate)

    return positions


def relax_spacing_in_rect(
    positions: list[tuple[float, float]],
    min_spacing: float,
    center: tuple[float, float],
    width: float,
    height: float,
    iterations: int = 8,
) -> list[tuple[float, float]]:
    left = center[0] - width / 2
    right = center[0] + width / 2
    bottom = center[1] - height / 2
    top = center[1] + height / 2
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
                max(left, min(right, x + offset[0] * 0.42)),
                max(bottom, min(top, y + offset[1] * 0.42)),
            )
            for (x, y), offset in zip(relaxed, offsets)
        ]
    return relaxed


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


def scaled_positions(
    positions: list[tuple[float, float]],
    scale_x: float,
    scale_y: float,
    center: tuple[float, float] | None = None,
) -> list[tuple[float, float]]:
    if not positions:
        return []
    pivot = center or (
        sum(position_x for position_x, _position_y in positions) / len(positions),
        sum(position_y for _position_x, position_y in positions) / len(positions),
    )
    return [
        (
            pivot[0] + (position_x - pivot[0]) * scale_x,
            pivot[1] + (position_y - pivot[1]) * scale_y,
        )
        for position_x, position_y in positions
    ]


def scaled_positions_to_size(
    positions: list[tuple[float, float]],
    target_width: float,
    target_height: float,
    lock_aspect: bool = False,
    center: tuple[float, float] | None = None,
) -> list[tuple[float, float]]:
    if not positions:
        return []
    min_x = min(position_x for position_x, _position_y in positions)
    max_x = max(position_x for position_x, _position_y in positions)
    min_y = min(position_y for _position_x, position_y in positions)
    max_y = max(position_y for _position_x, position_y in positions)
    current_width = max_x - min_x
    current_height = max_y - min_y
    scale_x = max(0.01, target_width) / current_width if current_width > 0.001 else 1.0
    scale_y = max(0.01, target_height) / current_height if current_height > 0.001 else 1.0
    if lock_aspect:
        uniform_scale = min(scale_x, scale_y)
        scale_x = uniform_scale
        scale_y = uniform_scale
    return scaled_positions(positions, scale_x, scale_y, center)


def warped_positions(
    positions: list[tuple[float, float]],
    anchors: list[tuple[float, float]],
    strength: float = 1.0,
) -> list[tuple[float, float]]:
    if len(positions) < 2 or len(anchors) < 2:
        return list(positions)
    min_x = min(position_x for position_x, _position_y in positions)
    max_x = max(position_x for position_x, _position_y in positions)
    width = max_x - min_x
    if width <= 0.001:
        min_y = min(position_y for _position_x, position_y in positions)
        max_y = max(position_y for _position_x, position_y in positions)
        height = max_y - min_y
        if height <= 0.001:
            return list(positions)
        baseline_y = sum(y for _x, y in anchors) / len(anchors)
        warped: list[tuple[float, float]] = []
        for x, y in positions:
            progress = (y - min_y) / height
            handle = point_on_polyline(anchors, progress)
            warped.append((x + (handle[0] - x) * strength, y + (handle[1] - baseline_y) * strength))
        return warped

    baseline_y = sum(anchor[1] for anchor in anchors) / len(anchors)
    warped_positions_list: list[tuple[float, float]] = []
    for x, y in positions:
        progress = (x - min_x) / width
        handle = point_on_polyline(anchors, progress)
        warped_positions_list.append((x, y + (handle[1] - baseline_y) * strength))
    return warped_positions_list


def point_on_polyline(points: list[tuple[float, float]], progress: float) -> tuple[float, float]:
    if not points:
        return 0.0, 0.0
    if len(points) == 1:
        return points[0]
    progress = max(0.0, min(1.0, progress))
    scaled = progress * (len(points) - 1)
    index = min(len(points) - 2, int(scaled))
    local_t = scaled - index
    start = points[index]
    end = points[index + 1]
    return (
        start[0] + (end[0] - start[0]) * local_t,
        start[1] + (end[1] - start[1]) * local_t,
    )


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


def sampled_spline_path(
    anchors: list[tuple[float, float]],
    curved: bool = True,
    closed: bool = False,
    samples_per_segment: int = 24,
) -> list[tuple[float, float]]:
    if len(anchors) <= 1:
        return list(anchors)
    if not closed:
        return sampled_shape_path(anchors, curved, samples_per_segment)
    if len(anchors) == 2:
        return [anchors[0], anchors[1], anchors[0]]
    if not curved:
        return [*anchors, anchors[0]]

    samples: list[tuple[float, float]] = []
    anchor_count = len(anchors)
    for index in range(anchor_count):
        p0 = anchors[(index - 1) % anchor_count]
        p1 = anchors[index]
        p2 = anchors[(index + 1) % anchor_count]
        p3 = anchors[(index + 2) % anchor_count]
        for sample_index in range(samples_per_segment):
            samples.append(catmull_rom_point(p0, p1, p2, p3, sample_index / samples_per_segment))
    samples.append(samples[0])
    return samples


def freeform_curve_positions(
    count: int,
    anchors: list[tuple[float, float]],
    closed: bool = False,
    curved: bool = True,
) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    path = sampled_spline_path(anchors, curved=curved, closed=closed)
    return positions_along_path(path, count)


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


def positions_along_paths_spaced(
    paths: list[list[tuple[float, float]]],
    count: int,
    min_spacing: float,
) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    base_positions = positions_along_paths(paths, count)
    if count <= 2 or not base_positions:
        return base_positions

    sample_count = max(count * 18, 360)
    candidate_positions = positions_along_paths(paths, sample_count)
    if len(candidate_positions) <= count:
        return relax_close_positions(base_positions, min_spacing)

    slot_width = max(1.0, len(candidate_positions) / max(1, count))
    chosen: list[tuple[float, float]] = []
    used_indices: set[int] = set()
    for slot_index in range(count):
        target_index = int(round(slot_index * len(candidate_positions) / max(1, count)))
        search_radius = max(8, int(slot_width * 2.5))
        candidate_indices = [
            (target_index + offset) % len(candidate_positions)
            for offset in range(-search_radius, search_radius + 1)
        ]
        candidate_indices.extend(
            (target_index + offset) % len(candidate_positions)
            for offset in range(-search_radius * 3, search_radius * 3 + 1, 3)
        )
        best_index = min(
            candidate_indices,
            key=lambda candidate_index: spaced_candidate_score(
                candidate_positions,
                candidate_index,
                target_index,
                len(candidate_positions),
                chosen,
                used_indices,
                min_spacing,
            ),
        )
        used_indices.add(best_index)
        chosen.append(candidate_positions[best_index])

    return relax_close_positions(chosen, min_spacing)


def spaced_candidate_score(
    candidates: list[tuple[float, float]],
    candidate_index: int,
    target_index: int,
    candidate_count: int,
    chosen: list[tuple[float, float]],
    used_indices: set[int],
    min_spacing: float,
) -> float:
    candidate = candidates[candidate_index]
    index_distance = abs(candidate_index - target_index)
    index_distance = min(index_distance, candidate_count - index_distance)
    score = index_distance / max(1.0, candidate_count)
    if candidate_index in used_indices:
        score += 1000.0
    for placed in chosen:
        current_distance = distance(candidate, placed)
        if current_distance < min_spacing:
            score += ((min_spacing - current_distance) / max(0.001, min_spacing)) ** 2 * 45.0
        elif current_distance < min_spacing * 1.35:
            score += ((min_spacing * 1.35 - current_distance) / max(0.001, min_spacing)) * 2.0
    return score


def relax_close_positions(
    positions: list[tuple[float, float]],
    min_spacing: float,
    iterations: int = 18,
) -> list[tuple[float, float]]:
    if len(positions) <= 1:
        return positions
    relaxed = list(positions)
    originals = list(positions)
    min_x = min(point[0] for point in positions) - min_spacing
    max_x = max(point[0] for point in positions) + min_spacing
    min_y = min(point[1] for point in positions) - min_spacing
    max_y = max(point[1] for point in positions) + min_spacing
    for _iteration in range(iterations):
        offsets = [(0.0, 0.0) for _point in relaxed]
        for first_index in range(len(relaxed)):
            for second_index in range(first_index + 1, len(relaxed)):
                delta_x = relaxed[first_index][0] - relaxed[second_index][0]
                delta_y = relaxed[first_index][1] - relaxed[second_index][1]
                current_distance = (delta_x * delta_x + delta_y * delta_y) ** 0.5
                if current_distance < 0.001:
                    angle = 2 * pi * (first_index + 1) / max(2, len(relaxed))
                    delta_x = cos(angle) * 0.01
                    delta_y = sin(angle) * 0.01
                    current_distance = 0.01
                if current_distance < min_spacing:
                    push = (min_spacing - current_distance) / current_distance * 0.5
                    offsets[first_index] = (
                        offsets[first_index][0] + delta_x * push,
                        offsets[first_index][1] + delta_y * push,
                    )
                    offsets[second_index] = (
                        offsets[second_index][0] - delta_x * push,
                        offsets[second_index][1] - delta_y * push,
                    )
        relaxed = [
            (
                max(min_x, min(max_x, point[0] + offset[0] * 0.58 + (original[0] - point[0]) * 0.025)),
                max(min_y, min(max_y, point[1] + offset[1] * 0.58 + (original[1] - point[1]) * 0.025)),
            )
            for point, offset, original in zip(relaxed, offsets, originals)
        ]
    return relaxed


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
