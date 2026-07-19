from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, pi

from drill_writer.core.models import DrillProject, DrillSet, Prop, Transition, prop_default_state


@dataclass(slots=True)
class PlaybackPosition:
    set_index: int
    count: float
    progress: float


def ease(progress: float, transition: Transition) -> float:
    progress = max(0.0, min(1.0, progress))
    if transition == Transition.EASE_IN_OUT:
        return 0.5 - 0.5 * cos(pi * progress)
    if transition == Transition.CURVED:
        return progress * progress * (3 - 2 * progress)
    return progress


def motion_window_for_dot(drill_set: DrillSet, dot_id: str) -> tuple[float, float]:
    set_start = float(drill_set.start_count)
    set_end = float(drill_set.end_count)
    timing = drill_set.move_timings.get(dot_id, {})
    move_start = float(timing.get("start", set_start))
    move_end = float(timing.get("end", set_end))
    move_start = max(set_start, min(move_start, set_end))
    move_end = max(move_start, min(move_end, set_end))
    return move_start, move_end


def normalize_facing_degrees(value: float) -> float:
    return float(value) % 360.0


def shortest_angle_delta(start: float, end: float) -> float:
    return ((normalize_facing_degrees(end) - normalize_facing_degrees(start) + 180.0) % 360.0) - 180.0


def dot_facing_at_set(project: DrillProject, set_index: int, dot_id: str) -> float:
    if not project.sets:
        return 0.0
    bounded_index = max(0, min(set_index, len(project.sets) - 1))
    for index in range(bounded_index, -1, -1):
        if dot_id in project.sets[index].dot_facings:
            return normalize_facing_degrees(project.sets[index].dot_facings[dot_id])
    return 0.0


def interpolate_dot_facings(project: DrillProject, set_index: int, count: float) -> dict[str, float]:
    if not project.sets:
        return {dot.id: 0.0 for dot in project.dots}

    current_index = max(0, min(set_index, len(project.sets) - 1))
    current = project.sets[current_index]
    previous_index = max(0, current_index - 1)
    facings: dict[str, float] = {}
    for dot in project.dots:
        start = dot_facing_at_set(project, previous_index, dot.id) if current_index > 0 else 0.0
        end = dot_facing_at_set(project, current_index, dot.id)
        motion_start_count, motion_end_count = motion_window_for_dot(current, dot.id)
        keyframes = current.count_facings.get(dot.id, {})
        if keyframes:
            facings[dot.id] = keyframed_facing_value(
                start,
                end,
                keyframes,
                count,
                motion_start_count,
                motion_end_count,
                current.transition,
            )
            continue
        if count <= motion_start_count:
            facings[dot.id] = start
            continue
        if count >= motion_end_count:
            facings[dot.id] = end
            continue
        progress = ease((count - motion_start_count) / max(0.0001, motion_end_count - motion_start_count), current.transition)
        facings[dot.id] = normalize_facing_degrees(start + shortest_angle_delta(start, end) * progress)
    return facings


def keyframed_facing_value(
    start: float,
    end: float,
    keyframes: dict[float, float],
    count: float,
    start_count: float,
    end_count: float,
    transition: Transition,
) -> float:
    timeline: list[tuple[float, float]] = [(float(start_count), normalize_facing_degrees(start))]
    for key_count, facing in sorted(keyframes.items()):
        normalized_count = max(float(start_count), min(float(key_count), float(end_count)))
        normalized_facing = normalize_facing_degrees(facing)
        if timeline and abs(timeline[-1][0] - normalized_count) <= 0.000001:
            timeline[-1] = (normalized_count, normalized_facing)
        else:
            timeline.append((normalized_count, normalized_facing))
    normalized_end = normalize_facing_degrees(end)
    if timeline and abs(timeline[-1][0] - float(end_count)) <= 0.000001:
        timeline[-1] = (float(end_count), timeline[-1][1])
    else:
        timeline.append((float(end_count), normalized_end))
    if count <= timeline[0][0]:
        return timeline[0][1]
    if count >= timeline[-1][0]:
        return timeline[-1][1]
    for index in range(len(timeline) - 1):
        count_a, facing_a = timeline[index]
        count_b, facing_b = timeline[index + 1]
        if count <= count_b:
            progress = ease((float(count) - count_a) / max(0.0001, count_b - count_a), transition)
            return normalize_facing_degrees(facing_a + shortest_angle_delta(facing_a, facing_b) * progress)
    return timeline[-1][1]


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


def sample_waypoint_path(
    waypoints: list[tuple[float, float]],
    samples_per_segment: int = 16,
) -> list[tuple[float, float]]:
    if len(waypoints) <= 1:
        return waypoints
    if len(waypoints) == 2:
        return [
            (
                waypoints[0][0] + (waypoints[1][0] - waypoints[0][0]) * index / samples_per_segment,
                waypoints[0][1] + (waypoints[1][1] - waypoints[0][1]) * index / samples_per_segment,
            )
            for index in range(samples_per_segment + 1)
        ]

    sampled: list[tuple[float, float]] = []
    padded = [waypoints[0], *waypoints, waypoints[-1]]
    for index in range(1, len(padded) - 2):
        for sample_index in range(samples_per_segment):
            sampled.append(
                catmull_rom_point(
                    padded[index - 1],
                    padded[index],
                    padded[index + 1],
                    padded[index + 2],
                    sample_index / samples_per_segment,
                )
            )
    sampled.append(waypoints[-1])
    return sampled


def point_on_polyline(points: list[tuple[float, float]], progress: float) -> tuple[float, float]:
    if not points:
        return (0, 0)
    if len(points) == 1:
        return points[0]

    progress = max(0.0, min(1.0, progress))
    segment_lengths = [
        distance(points[index], points[index + 1])
        for index in range(len(points) - 1)
    ]
    total_length = sum(segment_lengths)
    if total_length == 0:
        return points[0]

    target_distance = total_length * progress
    traveled = 0.0
    for index, segment_length in enumerate(segment_lengths):
        if traveled + segment_length >= target_distance or index == len(segment_lengths) - 1:
            local_t = (target_distance - traveled) / (segment_length or 1)
            start = points[index]
            end = points[index + 1]
            return (
                start[0] + (end[0] - start[0]) * local_t,
                start[1] + (end[1] - start[1]) * local_t,
            )
        traveled += segment_length
    return points[-1]


def transition_position(
    start: tuple[float, float],
    end: tuple[float, float],
    anchors: list[tuple[float, float]],
    progress: float,
) -> tuple[float, float]:
    if anchors:
        return point_on_polyline(sample_waypoint_path([start, *anchors, end]), progress)
    return (
        start[0] + (end[0] - start[0]) * progress,
        start[1] + (end[1] - start[1]) * progress,
    )


def cubic_bezier_point(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    return (
        (1 - t) ** 3 * p0[0]
        + 3 * (1 - t) ** 2 * t * p1[0]
        + 3 * (1 - t) * t**2 * p2[0]
        + t**3 * p3[0],
        (1 - t) ** 3 * p0[1]
        + 3 * (1 - t) ** 2 * t * p1[1]
        + 3 * (1 - t) * t**2 * p2[1]
        + t**3 * p3[1],
    )


def sample_bezier_path(
    start: tuple[float, float],
    end: tuple[float, float],
    anchors: list[tuple[float, float]],
    controls: list[dict[str, tuple[float, float]]],
    samples_per_segment: int = 20,
) -> list[tuple[float, float]]:
    points = [start, *anchors, end]
    if len(points) <= 1:
        return points
    sampled: list[tuple[float, float]] = []
    for index in range(len(points) - 1):
        p0 = points[index]
        p3 = points[index + 1]
        p1 = default_segment_control(p0, p3, 1 / 3)
        p2 = default_segment_control(p0, p3, 2 / 3)
        if index > 0 and index - 1 < len(controls):
            p1 = controls[index - 1].get("out", p1)
        if index < len(controls):
            p2 = controls[index].get("in", p2)
        for sample_index in range(samples_per_segment):
            if index > 0 and sample_index == 0:
                continue
            sampled.append(cubic_bezier_point(p0, p1, p2, p3, sample_index / samples_per_segment))
    sampled.append(end)
    return sampled


def default_segment_control(
    start: tuple[float, float],
    end: tuple[float, float],
    ratio: float,
) -> tuple[float, float]:
    return (
        start[0] + (end[0] - start[0]) * ratio,
        start[1] + (end[1] - start[1]) * ratio,
    )


def keyframed_transition_position(
    start: tuple[float, float],
    end: tuple[float, float],
    keyframes: dict[float, tuple[float, float]],
    count: float,
    start_count: float,
    end_count: float,
    transition: Transition,
) -> tuple[float, float]:
    timeline = [(float(start_count), start)]
    timeline.extend(
        (float(key_count), position)
        for key_count, position in sorted(keyframes.items())
        if start_count < float(key_count) < end_count
    )
    timeline.append((float(end_count), end))

    for index in range(len(timeline) - 1):
        count_a, position_a = timeline[index]
        count_b, position_b = timeline[index + 1]
        if count <= count_b or index == len(timeline) - 2:
            span = max(0.0001, count_b - count_a)
            local_progress = ease((count - count_a) / span, transition)
            return transition_position(position_a, position_b, [], local_progress)
    return end


def sample_transition_path(
    start: tuple[float, float],
    end: tuple[float, float],
    anchors: list[tuple[float, float]],
    controls: list[dict[str, tuple[float, float]]] | None = None,
    samples: int = 32,
) -> list[tuple[float, float]]:
    if anchors and controls:
        return sample_bezier_path(start, end, anchors, controls, max(4, samples // max(1, len(anchors) + 1)))
    if anchors:
        return sample_waypoint_path([start, *anchors, end], max(2, samples // max(1, len(anchors) + 1)))
    return [
        transition_position(start, end, [], index / max(1, samples - 1))
        for index in range(samples)
    ]


def interpolate_project(project: DrillProject, set_index: int, count: float) -> dict[str, tuple[float, float]]:
    if not project.sets:
        return {dot.id: (dot.x, dot.y) for dot in project.dots}

    current_index = max(0, min(set_index, len(project.sets) - 1))
    current = project.sets[current_index]
    previous = project.sets[current_index - 1] if current_index > 0 else None

    positions: dict[str, tuple[float, float]] = {}
    for dot in project.dots:
        start = previous.dot_positions.get(dot.id, (dot.x, dot.y)) if previous else (dot.x, dot.y)
        end = current.dot_positions.get(dot.id, (dot.x, dot.y))
        motion_start_count, motion_end_count = motion_window_for_dot(current, dot.id)
        if count <= motion_start_count:
            positions[dot.id] = start
            continue
        if count >= motion_end_count:
            positions[dot.id] = end
            continue
        movement_counts = max(0.0001, motion_end_count - motion_start_count)
        progress = (count - motion_start_count) / movement_counts
        eased = ease(progress, current.transition)
        keyframes = current.count_positions.get(dot.id, {})
        if keyframes:
            positions[dot.id] = keyframed_transition_position(
                start,
                end,
                keyframes,
                count,
                motion_start_count,
                motion_end_count,
                current.transition,
            )
        else:
            anchors = current.path_anchors.get(dot.id, [])
            controls = current.path_controls.get(dot.id, [])
            if anchors and controls:
                path = sample_bezier_path(start, end, anchors, controls)
                positions[dot.id] = point_on_polyline(path, eased)
                continue
            positions[dot.id] = transition_position(
                start,
                end,
                anchors,
                eased,
            )
    return positions


def interpolate_props(project: DrillProject, set_index: int, count: float) -> dict[str, dict[str, float]]:
    if not project.sets:
        return {prop.id: prop_default_state(prop) for prop in project.props}

    current_index = max(0, min(set_index, len(project.sets) - 1))
    current = project.sets[current_index]
    previous = project.sets[current_index - 1] if current_index > 0 else None
    motion_start_count = current.start_count
    movement_counts = max(1, current.end_count - motion_start_count)
    progress = ease((count - motion_start_count) / movement_counts, current.transition)

    states: dict[str, dict[str, float]] = {}
    for prop in project.props:
        start = previous.prop_positions.get(prop.id, prop_default_state(prop)) if previous else prop_default_state(prop)
        end = current.prop_positions.get(prop.id, prop_default_state(prop))
        states[prop.id] = interpolate_prop_state(prop, start, end, progress)
    if project.prop_attachments:
        from drill_writer.core.specialized_design import apply_prop_attachments

        dot_positions = interpolate_project(project, set_index, count)
        dot_facings = interpolate_dot_facings(project, set_index, count)
        if any(
            attachment.enabled
            and attachment.rotation_behavior == "direction_of_travel"
            and attachment.start_count <= count <= attachment.end_count
            for attachment in project.prop_attachments
        ):
            previous_count = max(float(current.start_count), float(count) - 0.05)
            previous_positions = interpolate_project(project, set_index, previous_count)
            for attachment in project.prop_attachments:
                if attachment.rotation_behavior != "direction_of_travel":
                    continue
                leader_id = attachment.leader_dot_id or (attachment.dot_ids[0] if attachment.dot_ids else "")
                if leader_id not in dot_positions or leader_id not in previous_positions:
                    continue
                dx = dot_positions[leader_id][0] - previous_positions[leader_id][0]
                dy = dot_positions[leader_id][1] - previous_positions[leader_id][1]
                if hypot(dx, dy) > 0.0001:
                    dot_facings[leader_id] = degrees(atan2(dx, -dy)) % 360.0
        states = apply_prop_attachments(
            project,
            count,
            dot_positions,
            dot_facings,
            states,
        )
    return states


def interpolate_prop_state(
    prop: Prop,
    start: dict[str, float],
    end: dict[str, float],
    progress: float,
) -> dict[str, float]:
    default = prop_default_state(prop)
    state: dict[str, float] = {}
    for key in ("x", "y", "width", "height", "rotation"):
        start_value = float(start.get(key, default[key]))
        end_value = float(end.get(key, default[key]))
        state[key] = start_value + (end_value - start_value) * progress
    return state
