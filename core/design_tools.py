from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from math import atan2, cos, degrees, pi, sin

from drill_writer.core.cad_paths import (
    Point,
    cumulative_distances,
    interpolate,
    path_length,
    path_to_bezier_nodes,
    point_at_distance,
    point_distance,
    unit_vector,
)
from drill_writer.core.models import ConstructionGuide, ContinuityInstruction, MotionRibbon


@dataclass(slots=True)
class RibbonPlan:
    center_path: list[Point]
    left_edge: list[Point]
    right_edge: list[Point]
    paths: dict[str, list[Point]] = field(default_factory=dict)
    count_positions: dict[str, dict[float, Point]] = field(default_factory=dict)
    count_facings: dict[str, dict[float, float]] = field(default_factory=dict)
    end_facings: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class MorphOptions:
    coherence: float = 0.85
    section_strength: float = 0.65
    samples_per_count: int = 4
    face_direction: bool = False


@dataclass(slots=True)
class MorphPlan:
    count_positions: dict[str, dict[float, Point]] = field(default_factory=dict)
    count_facings: dict[str, dict[float, float]] = field(default_factory=dict)
    end_facings: dict[str, float] = field(default_factory=dict)
    paths: dict[str, list[Point]] = field(default_factory=dict)


def create_motion_ribbon(
    ribbon_id: str,
    name: str,
    dot_ids: list[str],
    start_positions: dict[str, Point],
    end_positions: dict[str, Point],
    bend: float = 0.0,
    orient_to_path: bool = True,
    face_direction: bool = False,
    samples_per_count: int = 4,
) -> MotionRibbon:
    valid_ids = [
        dot_id
        for dot_id in dot_ids
        if dot_id in start_positions and dot_id in end_positions
    ]
    if len(valid_ids) < 2:
        raise ValueError("A motion ribbon requires at least two marchers with start and end positions.")
    start_center = positions_center(start_positions[dot_id] for dot_id in valid_ids)
    end_center = positions_center(end_positions[dot_id] for dot_id in valid_ids)
    midpoint = interpolate(start_center, end_center, 0.5)
    tangent = unit_vector(end_center[0] - start_center[0], end_center[1] - start_center[1])
    normal = (-tangent[1], tangent[0]) if tangent != (0.0, 0.0) else (0.0, 1.0)
    midpoint = (midpoint[0] + normal[0] * bend, midpoint[1] + normal[1] * bend)
    nodes = path_to_bezier_nodes([start_center, midpoint, end_center])
    if len(nodes) < 2:
        nodes = [
            {"point": start_center, "in": start_center, "out": start_center},
            {"point": end_center, "in": end_center, "out": end_center},
        ]
    return MotionRibbon(
        id=ribbon_id,
        name=name,
        dot_ids=valid_ids,
        nodes=nodes,
        orient_to_path=orient_to_path,
        face_direction=face_direction,
        samples_per_count=max(1, min(16, int(samples_per_count))),
    )


def sample_motion_ribbon(ribbon: MotionRibbon, samples_per_segment: int = 28) -> list[Point]:
    nodes = [node for node in ribbon.nodes if "point" in node]
    if len(nodes) < 2:
        return [node["point"] for node in nodes]
    sampled: list[Point] = []
    for index in range(len(nodes) - 1):
        start = nodes[index]["point"]
        end = nodes[index + 1]["point"]
        control_out = nodes[index].get("out", interpolate(start, end, 1.0 / 3.0))
        control_in = nodes[index + 1].get("in", interpolate(start, end, 2.0 / 3.0))
        for sample in range(max(4, samples_per_segment)):
            if index and sample == 0:
                continue
            sampled.append(
                cubic_bezier_point(
                    start,
                    control_out,
                    control_in,
                    end,
                    sample / max(4, samples_per_segment),
                )
            )
    sampled.append(nodes[-1]["point"])
    return sampled


def plan_motion_ribbon(
    ribbon: MotionRibbon,
    start_positions: dict[str, Point],
    end_positions: dict[str, Point],
    start_count: float,
    end_count: float,
) -> RibbonPlan:
    dot_ids = [
        dot_id
        for dot_id in ribbon.dot_ids
        if dot_id in start_positions and dot_id in end_positions
    ]
    if len(dot_ids) < 2 or end_count <= start_count:
        raise ValueError("The ribbon no longer has enough valid marchers or movement counts.")
    center_path = sample_motion_ribbon(ribbon)
    if not center_path:
        raise ValueError("The motion ribbon center path has no usable geometry.")

    start_center = positions_center(start_positions[dot_id] for dot_id in dot_ids)
    end_center = positions_center(end_positions[dot_id] for dot_id in dot_ids)
    start_angle = tangent_angle(center_path, 0.0)
    end_angle = tangent_angle(center_path, 1.0)
    start_offsets = {
        dot_id: (
            start_positions[dot_id][0] - start_center[0],
            start_positions[dot_id][1] - start_center[1],
        )
        for dot_id in dot_ids
    }
    end_offsets = {
        dot_id: (
            end_positions[dot_id][0] - end_center[0],
            end_positions[dot_id][1] - end_center[1],
        )
        for dot_id in dot_ids
    }
    if ribbon.orient_to_path:
        start_offsets = {
            dot_id: rotate_vector(offset, -start_angle)
            for dot_id, offset in start_offsets.items()
        }
        end_offsets = {
            dot_id: rotate_vector(offset, -end_angle)
            for dot_id, offset in end_offsets.items()
        }
    offset_transform = similarity_transform(dot_ids, start_offsets, end_offsets)
    offset_residuals: dict[str, Point] = {}
    for dot_id in dot_ids:
        coherent_end = coherent_position(start_offsets[dot_id], offset_transform, 1.0)
        offset_residuals[dot_id] = (
            end_offsets[dot_id][0] - coherent_end[0],
            end_offsets[dot_id][1] - coherent_end[1],
        )

    half_width = ribbon_half_width(
        dot_ids,
        start_positions,
        start_center,
        start_angle,
    )
    left_edge: list[Point] = []
    right_edge: list[Point] = []
    for sample_index, center in enumerate(center_path):
        progress = sample_index / max(1, len(center_path) - 1)
        angle = tangent_angle(center_path, progress)
        normal = (-sin(angle), cos(angle))
        left_edge.append((center[0] + normal[0] * half_width, center[1] + normal[1] * half_width))
        right_edge.append((center[0] - normal[0] * half_width, center[1] - normal[1] * half_width))

    counts = count_samples(
        float(start_count),
        float(end_count),
        1.0 / max(1, min(16, int(ribbon.samples_per_count))),
    )
    center_distances = cumulative_distances(center_path)
    center_length = center_distances[-1] if center_distances else 0.0
    route_states: list[tuple[float, float, Point, float]] = []
    for count in counts:
        progress = (count - float(start_count)) / max(0.0001, float(end_count) - float(start_count))
        center = cached_path_point(center_path, center_distances, center_length * progress)
        angle = cached_tangent_angle(center_path, center_distances, center_length, progress)
        route_states.append((count, progress, center, angle))
    result = RibbonPlan(center_path=center_path, left_edge=left_edge, right_edge=right_edge)
    for dot_id in dot_ids:
        position_keys: dict[float, Point] = {}
        facing_keys: dict[float, float] = {}
        path_points: list[Point] = []
        for count, progress, center, angle in route_states:
            offset = coherent_position(start_offsets[dot_id], offset_transform, progress)
            residual = offset_residuals[dot_id]
            correction = smoothstep(progress)
            offset = (
                offset[0] + residual[0] * correction,
                offset[1] + residual[1] * correction,
            )
            if ribbon.orient_to_path:
                offset = rotate_vector(offset, angle)
            position = (center[0] + offset[0], center[1] + offset[1])
            if count <= start_count + 0.000001:
                position = start_positions[dot_id]
            elif count >= end_count - 0.000001:
                position = end_positions[dot_id]
            path_points.append(position)
            if start_count < count < end_count:
                position_keys[normalized_count(count)] = position
            if ribbon.face_direction:
                facing_keys[normalized_count(count)] = facing_degrees_for_angle(angle)
        result.paths[dot_id] = path_points
        result.count_positions[dot_id] = position_keys
        if facing_keys:
            result.count_facings[dot_id] = facing_keys
            result.end_facings[dot_id] = facing_keys[normalized_count(float(end_count))]
    return result


def plan_formation_morph(
    dot_ids: list[str],
    start_positions: dict[str, Point],
    end_positions: dict[str, Point],
    sections: dict[str, str],
    start_count: float,
    end_count: float,
    options: MorphOptions | None = None,
) -> MorphPlan:
    settings = options or MorphOptions()
    valid_ids = [
        dot_id
        for dot_id in dot_ids
        if dot_id in start_positions and dot_id in end_positions
    ]
    if len(valid_ids) < 2 or end_count <= start_count:
        raise ValueError("Formation Morph requires at least two marchers and multiple counts.")

    global_transform = similarity_transform(valid_ids, start_positions, end_positions)
    section_transforms: dict[str, tuple[Point, Point, float, float]] = {}
    for section in {sections.get(dot_id, "") for dot_id in valid_ids}:
        section_ids = [dot_id for dot_id in valid_ids if sections.get(dot_id, "") == section]
        if len(section_ids) >= 2:
            section_transforms[section] = similarity_transform(
                section_ids,
                start_positions,
                end_positions,
            )

    counts = count_samples(
        float(start_count),
        float(end_count),
        1.0 / max(1, min(16, int(settings.samples_per_count))),
    )
    coherence = max(0.0, min(1.0, float(settings.coherence)))
    section_strength = max(0.0, min(1.0, float(settings.section_strength)))
    result = MorphPlan()
    for dot_id in valid_ids:
        transform = section_transforms.get(sections.get(dot_id, ""), global_transform)
        path: list[Point] = []
        keys: dict[float, Point] = {}
        facings: dict[float, float] = {}
        final_coherent = coherent_position(start_positions[dot_id], transform, 1.0)
        residual = (
            end_positions[dot_id][0] - final_coherent[0],
            end_positions[dot_id][1] - final_coherent[1],
        )
        global_final = coherent_position(start_positions[dot_id], global_transform, 1.0)
        global_residual = (
            end_positions[dot_id][0] - global_final[0],
            end_positions[dot_id][1] - global_final[1],
        )
        for count in counts:
            progress = (count - float(start_count)) / max(0.0001, float(end_count) - float(start_count))
            eased = smoothstep(progress)
            section_position = coherent_position(start_positions[dot_id], transform, progress)
            section_position = (
                section_position[0] + residual[0] * eased,
                section_position[1] + residual[1] * eased,
            )
            global_position = coherent_position(start_positions[dot_id], global_transform, progress)
            global_position = (
                global_position[0] + global_residual[0] * eased,
                global_position[1] + global_residual[1] * eased,
            )
            coherent = interpolate(global_position, section_position, section_strength)
            direct = interpolate(start_positions[dot_id], end_positions[dot_id], eased)
            position = interpolate(direct, coherent, coherence)
            if count <= start_count + 0.000001:
                position = start_positions[dot_id]
            elif count >= end_count - 0.000001:
                position = end_positions[dot_id]
            path.append(position)
            if start_count < count < end_count:
                keys[normalized_count(count)] = position
        if settings.face_direction and len(path) > 1:
            for index, count in enumerate(counts):
                previous = path[max(0, index - 1)]
                following = path[min(len(path) - 1, index + 1)]
                angle = atan2(following[1] - previous[1], following[0] - previous[0])
                facings[normalized_count(count)] = facing_degrees_for_angle(angle)
        result.paths[dot_id] = path
        result.count_positions[dot_id] = keys
        if facings:
            result.count_facings[dot_id] = facings
            result.end_facings[dot_id] = facings[normalized_count(float(end_count))]
    return result


def continuity_for_dot(
    instructions: list[ContinuityInstruction],
    dot_id: str,
    count: float | None = None,
) -> list[ContinuityInstruction]:
    matches = [instruction for instruction in instructions if dot_id in instruction.dot_ids]
    if count is not None:
        matches = [
            instruction
            for instruction in matches
            if instruction.start_count <= count <= instruction.end_count
        ]
    return sorted(matches, key=lambda item: (item.start_count, item.end_count, item.id))


def continuity_summary(instruction: ContinuityInstruction) -> str:
    parts = [instruction.direction.replace("_", " ").title(), instruction.step_size]
    if instruction.body_facing is not None:
        parts.append(f"body {instruction.body_facing:g}°")
    if instruction.horn_facing is not None:
        parts.append(f"horn {instruction.horn_facing:g}°")
    if instruction.text.strip():
        parts.append(instruction.text.strip())
    return "; ".join(parts)


def guide_path(guide: ConstructionGuide, arc_samples: int = 48) -> list[Point]:
    points = list(guide.points)
    guide_type = guide.guide_type.lower()
    if guide_type in {"line", "diagonal", "ruler", "annotation_arrow"}:
        return points[:2]
    if guide_type in {"annotation_text", "annotation_note"} and points:
        center = points[0]
        return [(center[0] - 0.4, center[1]), (center[0] + 0.4, center[1])]
    if guide_type == "center" and points:
        center = points[0]
        size = float(guide.metadata.get("size", 8.0))
        return [
            (center[0] - size, center[1]),
            (center[0] + size, center[1]),
            center,
            (center[0], center[1] - size),
            (center[0], center[1] + size),
        ]
    if guide_type in {"circle", "no_go_circle"} and len(points) >= 2:
        center = points[0]
        radius = point_distance(center, points[1])
        return [
            (
                center[0] + cos(2 * pi * index / arc_samples) * radius,
                center[1] + sin(2 * pi * index / arc_samples) * radius,
            )
            for index in range(arc_samples + 1)
        ]
    if guide_type == "arc" and len(points) >= 3:
        center = points[0]
        radius = point_distance(center, points[1])
        start = atan2(points[1][1] - center[1], points[1][0] - center[0])
        end = atan2(points[2][1] - center[1], points[2][0] - center[0])
        sweep = normalize_signed_angle(end - start)
        return [
            (
                center[0] + cos(start + sweep * index / arc_samples) * radius,
                center[1] + sin(start + sweep * index / arc_samples) * radius,
            )
            for index in range(arc_samples + 1)
        ]
    if guide_type in {
        "rectangle",
        "grid",
        "no_go_rectangle",
        "annotation_box",
        "annotation_image",
    } and len(points) >= 2:
        first, second = points[0], points[1]
        return [
            (first[0], first[1]),
            (second[0], first[1]),
            (second[0], second[1]),
            (first[0], second[1]),
            (first[0], first[1]),
        ]
    return points


def guide_contains_point(guide: ConstructionGuide, point: Point) -> bool:
    guide_type = guide.guide_type.lower()
    if guide_type == "no_go_rectangle" and len(guide.points) >= 2:
        first, second = guide.points[0], guide.points[1]
        return (
            min(first[0], second[0]) <= point[0] <= max(first[0], second[0])
            and min(first[1], second[1]) <= point[1] <= max(first[1], second[1])
        )
    if guide_type == "no_go_circle" and len(guide.points) >= 2:
        return point_distance(guide.points[0], point) <= point_distance(
            guide.points[0], guide.points[1]
        )
    return False


def guide_measurement_label(guide: ConstructionGuide) -> str:
    if guide.guide_type.lower() == "ruler" and len(guide.points) >= 2:
        yards = point_distance(guide.points[0], guide.points[1])
        return f"{yards:.2f} yd / {yards * 8:.1f} steps"
    return guide.name


def motion_ribbon_by_id(ribbons: list[MotionRibbon], ribbon_id: str) -> MotionRibbon | None:
    return next((ribbon for ribbon in ribbons if ribbon.id == ribbon_id), None)


def point_on_path_progress(path: list[Point], progress: float) -> Point:
    return point_at_distance(path, path_length(path) * max(0.0, min(1.0, progress)))


def cached_path_point(
    path: list[Point],
    cumulative: list[float],
    distance_along: float,
) -> Point:
    if not path:
        return (0.0, 0.0)
    if len(path) == 1 or not cumulative or cumulative[-1] <= 0.000001:
        return path[0]
    target = max(0.0, min(float(distance_along), cumulative[-1]))
    index = max(1, min(len(path) - 1, bisect_left(cumulative, target)))
    span = max(0.000001, cumulative[index] - cumulative[index - 1])
    progress = (target - cumulative[index - 1]) / span
    return interpolate(path[index - 1], path[index], progress)


def cached_tangent_angle(
    path: list[Point],
    cumulative: list[float],
    total: float,
    progress: float,
) -> float:
    if len(path) < 2 or total <= 0.000001:
        return 0.0
    target = total * max(0.0, min(1.0, progress))
    epsilon = max(0.01, total / max(10000.0, len(path) * 20.0))
    before = cached_path_point(path, cumulative, max(0.0, target - epsilon))
    after = cached_path_point(path, cumulative, min(total, target + epsilon))
    if point_distance(before, after) <= 0.000001:
        return 0.0
    return atan2(after[1] - before[1], after[0] - before[0])


def tangent_angle(path: list[Point], progress: float) -> float:
    if len(path) < 2:
        return 0.0
    total = path_length(path)
    target = total * max(0.0, min(1.0, progress))
    epsilon = max(0.01, total / max(10000.0, len(path) * 20.0))
    before = point_at_distance(path, max(0.0, target - epsilon))
    after = point_at_distance(path, min(total, target + epsilon))
    if point_distance(before, after) <= 0.000001:
        return 0.0
    return atan2(after[1] - before[1], after[0] - before[0])


def ribbon_half_width(
    dot_ids: list[str],
    positions: dict[str, Point],
    center: Point,
    angle: float,
) -> float:
    normal = (-sin(angle), cos(angle))
    return max(
        0.75,
        max(
            abs(
                (positions[dot_id][0] - center[0]) * normal[0]
                + (positions[dot_id][1] - center[1]) * normal[1]
            )
            for dot_id in dot_ids
        )
        + 0.65,
    )


def similarity_transform(
    dot_ids: list[str],
    start_positions: dict[str, Point],
    end_positions: dict[str, Point],
) -> tuple[Point, Point, float, float]:
    start_center = positions_center(start_positions[dot_id] for dot_id in dot_ids)
    end_center = positions_center(end_positions[dot_id] for dot_id in dot_ids)
    cross = 0.0
    dot_product = 0.0
    start_energy = 0.0
    end_energy = 0.0
    for dot_id in dot_ids:
        start = (
            start_positions[dot_id][0] - start_center[0],
            start_positions[dot_id][1] - start_center[1],
        )
        end = (
            end_positions[dot_id][0] - end_center[0],
            end_positions[dot_id][1] - end_center[1],
        )
        dot_product += start[0] * end[0] + start[1] * end[1]
        cross += start[0] * end[1] - start[1] * end[0]
        start_energy += start[0] * start[0] + start[1] * start[1]
        end_energy += end[0] * end[0] + end[1] * end[1]
    angle = atan2(cross, dot_product) if abs(cross) + abs(dot_product) > 0.000001 else 0.0
    scale = (end_energy / start_energy) ** 0.5 if start_energy > 0.000001 else 1.0
    return start_center, end_center, angle, scale


def coherent_position(
    start: Point,
    transform: tuple[Point, Point, float, float],
    progress: float,
) -> Point:
    start_center, end_center, angle, scale = transform
    center = interpolate(start_center, end_center, progress)
    offset = (start[0] - start_center[0], start[1] - start_center[1])
    offset = rotate_vector(offset, angle * progress)
    current_scale = 1.0 + (scale - 1.0) * progress
    return (center[0] + offset[0] * current_scale, center[1] + offset[1] * current_scale)


def cubic_bezier_point(
    start: Point,
    control_out: Point,
    control_in: Point,
    end: Point,
    progress: float,
) -> Point:
    inverse = 1.0 - progress
    return (
        inverse**3 * start[0]
        + 3 * inverse * inverse * progress * control_out[0]
        + 3 * inverse * progress * progress * control_in[0]
        + progress**3 * end[0],
        inverse**3 * start[1]
        + 3 * inverse * inverse * progress * control_out[1]
        + 3 * inverse * progress * progress * control_in[1]
        + progress**3 * end[1],
    )


def positions_center(positions) -> Point:
    values = list(positions)
    if not values:
        return (0.0, 0.0)
    return (
        sum(point[0] for point in values) / len(values),
        sum(point[1] for point in values) / len(values),
    )


def rotate_vector(vector: Point, angle_radians: float) -> Point:
    cosine = cos(angle_radians)
    sine = sin(angle_radians)
    return (
        vector[0] * cosine - vector[1] * sine,
        vector[0] * sine + vector[1] * cosine,
    )


def facing_degrees_for_angle(angle_radians: float) -> float:
    delta_x = cos(angle_radians)
    delta_y = sin(angle_radians)
    return degrees(atan2(-delta_x, -delta_y)) % 360.0


def smoothstep(progress: float) -> float:
    bounded = max(0.0, min(1.0, progress))
    return bounded * bounded * (3.0 - 2.0 * bounded)


def count_samples(start_count: float, end_count: float, step: float) -> list[float]:
    span = end_count - start_count
    steps = max(1, int(round(span / max(0.0001, step))))
    return [start_count + span * index / steps for index in range(steps + 1)]


def normalized_count(count: float) -> float:
    return round(float(count), 6)


def normalize_signed_angle(angle: float) -> float:
    return (angle + pi) % (2 * pi) - pi
