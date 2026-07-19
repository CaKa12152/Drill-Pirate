from __future__ import annotations

from dataclasses import dataclass, replace
from math import atan2, cos, degrees, hypot, radians, sin

from drill_writer.core.models import (
    ChoreographyEvent,
    Dot,
    DrillProject,
    PerformerPhysicalLimits,
    PropAttachment,
    SurfaceDefinition,
)


@dataclass(frozen=True, slots=True)
class ResolvedPhysicalLimits:
    max_yards_per_count: float = 1.5
    max_backward_yards_per_count: float = 1.05
    max_lateral_yards_per_count: float = 1.15
    max_rotation_degrees_per_count: float = 90.0
    max_toss_revolutions: float = 6.0
    minimum_recovery_counts: float = 1.0
    carry_speed_multiplier: float = 0.75
    profile_name: str = "General performer"


@dataclass(frozen=True, slots=True)
class SpecializedWarning:
    severity: str
    rule: str
    dot_id: str
    count: float
    message: str
    suggestion: str


def surface_presets() -> dict[str, SurfaceDefinition]:
    return {
        "college": SurfaceDefinition(),
        "high_school": SurfaceDefinition(
            name="High School Football Field",
            hash_style="high_school",
            front_hash_yards=-8.8888,
            back_hash_yards=8.8888,
        ),
        "indoor": SurfaceDefinition(
            name="Indoor Performance Floor",
            surface_type="indoor",
            width_yards=30.0,
            height_yards=20.0,
            hash_style="none",
            front_hash_yards=0.0,
            back_hash_yards=0.0,
            endzone_depth_yards=0.0,
            grid_spacing_yards=1.0,
            show_yard_numbers=False,
            show_end_zones=False,
        ),
        "parade": SurfaceDefinition(
            name="Parade Route",
            surface_type="parade",
            width_yards=120.0,
            height_yards=30.0,
            hash_style="none",
            front_hash_yards=0.0,
            back_hash_yards=0.0,
            endzone_depth_yards=0.0,
            grid_spacing_yards=5.0,
            route_points=[(-55.0, 0.0), (-20.0, 0.0), (5.0, 6.0), (30.0, 6.0), (55.0, 0.0)],
            route_width_yards=8.0,
            show_yard_numbers=False,
            show_end_zones=False,
        ),
        "staging": SurfaceDefinition(
            name="Staging Surface",
            surface_type="staging",
            width_yards=40.0,
            height_yards=30.0,
            hash_style="none",
            front_hash_yards=0.0,
            back_hash_yards=0.0,
            endzone_depth_yards=0.0,
            grid_spacing_yards=1.0,
            show_yard_numbers=False,
            show_end_zones=False,
        ),
    }


def surface_preset(name: str) -> SurfaceDefinition:
    return replace(surface_presets().get(name, surface_presets()["college"]))


def normalized_surface(surface: SurfaceDefinition) -> SurfaceDefinition:
    result = replace(surface)
    result.surface_type = result.surface_type if result.surface_type in {"football", "indoor", "parade", "staging"} else "staging"
    result.width_yards = max(2.0, min(5000.0, float(result.width_yards)))
    result.height_yards = max(2.0, min(1000.0, float(result.height_yards)))
    result.grid_spacing_yards = max(0.25, min(25.0, float(result.grid_spacing_yards)))
    result.endzone_depth_yards = max(0.0, min(result.width_yards / 3.0, float(result.endzone_depth_yards)))
    result.route_width_yards = max(0.5, min(result.height_yards, float(result.route_width_yards)))
    result.front_hash_yards = max(-result.half_height, min(result.half_height, float(result.front_hash_yards)))
    result.back_hash_yards = max(-result.half_height, min(result.half_height, float(result.back_hash_yards)))
    if result.front_hash_yards > result.back_hash_yards:
        result.front_hash_yards, result.back_hash_yards = result.back_hash_yards, result.front_hash_yards
    return result


def surface_contains_point(surface: SurfaceDefinition, point: tuple[float, float], margin: float = 0.0) -> bool:
    normalized = normalized_surface(surface)
    return (
        -normalized.half_width - margin <= point[0] <= normalized.half_width + margin
        and -normalized.half_height - margin <= point[1] <= normalized.half_height + margin
    )


def closest_route_position(
    surface: SurfaceDefinition,
    point: tuple[float, float],
) -> tuple[float, float, tuple[float, float]]:
    points = surface.route_points
    if len(points) < 2:
        return (0.0, hypot(point[0], point[1]), (0.0, 0.0))
    best_distance = float("inf")
    best_station = 0.0
    best_side = 0.0
    best_point = points[0]
    station = 0.0
    for start, end in zip(points, points[1:]):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length_squared = dx * dx + dy * dy
        length = hypot(dx, dy)
        if length_squared <= 1e-9:
            continue
        progress = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared))
        nearest = (start[0] + dx * progress, start[1] + dy * progress)
        offset_x = point[0] - nearest[0]
        offset_y = point[1] - nearest[1]
        current_distance = hypot(offset_x, offset_y)
        if current_distance < best_distance:
            best_distance = current_distance
            best_station = station + length * progress
            best_side = (dx * offset_y - dy * offset_x) / max(length, 1e-9)
            best_point = nearest
        station += length
    return best_station, best_side, best_point


def validate_choreography(project: DrillProject) -> list[str]:
    errors: list[str] = []
    events = sorted(project.choreography, key=lambda item: (item.start_count, item.end_count, item.id))
    for event in events:
        if not event.dot_ids:
            errors.append(f"{event.name}: select at least one performer.")
        if event.event_type == "equipment_change" and not event.equipment_to.strip():
            errors.append(f"{event.name}: equipment changes require a destination equipment.")
        if event.event_type == "toss" and event.end_count <= event.start_count:
            errors.append(f"{event.name}: tosses require a positive duration.")
    for index, first in enumerate(events):
        for second in events[index + 1 :]:
            if second.start_count > first.end_count:
                break
            shared = set(first.dot_ids) & set(second.dot_ids)
            if shared and first.event_type in {"toss", "equipment_change"} and second.event_type in {"toss", "equipment_change"}:
                errors.append(f"{first.name} overlaps {second.name} for {', '.join(sorted(shared))}.")
    return errors


def equipment_for_dot_at_count(project: DrillProject, dot_id: str, count: float) -> str:
    dot = project.dot_by_id(dot_id)
    equipment = dot.equipment if dot else ""
    for event in sorted(project.choreography, key=lambda item: (item.start_count, item.end_count)):
        if event.event_type == "equipment_change" and dot_id in event.dot_ids and event.end_count <= count:
            equipment = event.equipment_to
    return equipment


def active_prop_attachments(project: DrillProject, count: float) -> list[PropAttachment]:
    return [
        attachment
        for attachment in project.prop_attachments
        if attachment.enabled and attachment.start_count <= count <= attachment.end_count
    ]


def apply_prop_attachments(
    project: DrillProject,
    count: float,
    dot_positions: dict[str, tuple[float, float]],
    dot_facings: dict[str, float],
    prop_states: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    result = {prop_id: dict(state) for prop_id, state in prop_states.items()}
    claimed_props: set[str] = set()
    for attachment in sorted(active_prop_attachments(project, count), key=lambda item: (item.start_count, item.id)):
        if attachment.prop_id in claimed_props:
            continue
        positions = [dot_positions[dot_id] for dot_id in attachment.dot_ids if dot_id in dot_positions]
        if not positions or attachment.prop_id not in result:
            continue
        leader_id = attachment.leader_dot_id if attachment.leader_dot_id in dot_positions else attachment.dot_ids[0]
        leader_position = dot_positions.get(leader_id, positions[0])
        anchor = (
            sum(position[0] for position in positions) / len(positions),
            sum(position[1] for position in positions) / len(positions),
        )
        if attachment.mode in {"push", "rotate"}:
            anchor = leader_position
        facing = float(dot_facings.get(leader_id, 0.0))
        offset_x = float(attachment.offset_x)
        offset_y = float(attachment.offset_y)
        if attachment.rotation_behavior in {"performer_facing", "direction_of_travel"}:
            angle = radians(facing)
            offset_x, offset_y = (
                offset_x * cos(angle) + offset_y * sin(angle),
                -offset_x * sin(angle) + offset_y * cos(angle),
            )
        state = result[attachment.prop_id]
        state["x"] = anchor[0] + offset_x
        state["y"] = anchor[1] + offset_y
        if attachment.rotation_behavior in {"performer_facing", "direction_of_travel"}:
            state["rotation"] = facing + attachment.rotation_offset
        elif attachment.mode == "rotate":
            elapsed = max(0.0, count - attachment.start_count)
            state["rotation"] = float(state.get("rotation", 0.0)) + attachment.rotation_offset + attachment.rotation_rate * elapsed
        else:
            state["rotation"] = float(state.get("rotation", 0.0)) + attachment.rotation_offset
        state["rotation"] %= 360.0
        claimed_props.add(attachment.prop_id)
    return result


def instrument_profile(dot: Dot) -> ResolvedPhysicalLimits:
    descriptor = " ".join((dot.instrument, dot.section, dot.equipment)).lower()
    if any(name in descriptor for name in ("tuba", "sousaphone")):
        return ResolvedPhysicalLimits(1.2, 0.75, 0.75, 55.0, profile_name="Tuba / sousaphone")
    if "bass drum" in descriptor:
        return ResolvedPhysicalLimits(1.15, 0.65, 0.6, 45.0, profile_name="Bass drum")
    if any(name in descriptor for name in ("tenor", "quads")):
        return ResolvedPhysicalLimits(1.25, 0.75, 0.7, 55.0, profile_name="Tenors")
    if any(name in descriptor for name in ("trombone", "euphonium", "baritone")):
        return ResolvedPhysicalLimits(1.35, 0.85, 0.9, 65.0, profile_name="Low brass")
    if any(name in descriptor for name in ("rifle", "sabre", "saber", "flag", "guard")):
        return ResolvedPhysicalLimits(1.75, 1.25, 1.4, 180.0, 7.0, 1.0, 0.8, "Color guard")
    return ResolvedPhysicalLimits()


def physical_limits_for_dot(project: DrillProject, dot_id: str) -> ResolvedPhysicalLimits:
    dot = project.dot_by_id(dot_id)
    resolved = instrument_profile(dot) if dot else ResolvedPhysicalLimits()
    override = next((item for item in project.physical_limits if item.dot_id == dot_id), None)
    if not override:
        return resolved
    values = {
        field_name: getattr(override, field_name)
        if getattr(override, field_name) is not None
        else getattr(resolved, field_name)
        for field_name in (
            "max_yards_per_count",
            "max_backward_yards_per_count",
            "max_lateral_yards_per_count",
            "max_rotation_degrees_per_count",
            "max_toss_revolutions",
            "minimum_recovery_counts",
            "carry_speed_multiplier",
        )
    }
    return ResolvedPhysicalLimits(**values, profile_name=f"{resolved.profile_name} + performer override")


def set_physical_limits(project: DrillProject, limits: PerformerPhysicalLimits) -> None:
    project.physical_limits = [item for item in project.physical_limits if item.dot_id != limits.dot_id]
    project.physical_limits.append(limits)


def performer_is_attached_to_prop(project: DrillProject, dot_id: str, count: float) -> bool:
    return any(dot_id in attachment.dot_ids for attachment in active_prop_attachments(project, count))


def analyze_specialized_safety(
    project: DrillProject,
    set_index: int,
    samples: int = 24,
    dot_ids: list[str] | None = None,
) -> list[SpecializedWarning]:
    from drill_writer.core.animation import interpolate_dot_facings, interpolate_project

    if not 0 <= set_index < len(project.sets):
        return []
    drill_set = project.sets[set_index]
    selected = set(dot_ids or [dot.id for dot in project.dots])
    counts = [
        drill_set.start_count + (drill_set.end_count - drill_set.start_count) * index / max(1, samples - 1)
        for index in range(max(2, samples))
    ]
    positions = [interpolate_project(project, set_index, count) for count in counts]
    facings = [interpolate_dot_facings(project, set_index, count) for count in counts]
    warnings: list[SpecializedWarning] = []
    worst_by_rule: dict[tuple[str, str], tuple[float, float, float]] = {}
    spatial_by_rule: dict[tuple[str, str], tuple[float, float]] = {}
    for sample_index in range(1, len(counts)):
        span = max(0.0001, counts[sample_index] - counts[sample_index - 1])
        for dot_id in selected:
            if dot_id not in positions[sample_index] or dot_id not in positions[sample_index - 1]:
                continue
            limits = physical_limits_for_dot(project, dot_id)
            current_point = positions[sample_index][dot_id]
            if not surface_contains_point(project.surface, current_point):
                overflow = hypot(
                    max(0.0, abs(current_point[0]) - project.surface.half_width),
                    max(0.0, abs(current_point[1]) - project.surface.half_height),
                )
                if overflow > spatial_by_rule.get((dot_id, "surface"), (0.0, 0.0))[0]:
                    spatial_by_rule[(dot_id, "surface")] = (overflow, counts[sample_index])
            if project.surface.surface_type == "parade" and len(project.surface.route_points) >= 2:
                _station, route_offset, _nearest = closest_route_position(project.surface, current_point)
                excess = abs(route_offset) - project.surface.route_width_yards / 2.0
                if excess > spatial_by_rule.get((dot_id, "route"), (0.0, 0.0))[0]:
                    spatial_by_rule[(dot_id, "route")] = (excess, counts[sample_index])
            dx = (positions[sample_index][dot_id][0] - positions[sample_index - 1][dot_id][0]) / span
            dy = (positions[sample_index][dot_id][1] - positions[sample_index - 1][dot_id][1]) / span
            speed = hypot(dx, dy)
            multiplier = limits.carry_speed_multiplier if performer_is_attached_to_prop(project, dot_id, counts[sample_index]) else 1.0
            facing = radians(facings[sample_index - 1].get(dot_id, 0.0))
            forward_x, forward_y = sin(facing), -cos(facing)
            forward = dx * forward_x + dy * forward_y
            lateral = abs(dx * forward_y - dy * forward_x)
            checks = (
                ("speed", speed, limits.max_yards_per_count * multiplier),
                ("backward", max(0.0, -forward), limits.max_backward_yards_per_count * multiplier),
                ("lateral", lateral, limits.max_lateral_yards_per_count * multiplier),
            )
            for rule, value, limit in checks:
                if value > limit and value > worst_by_rule.get((dot_id, rule), (0.0, 0.0, 0.0))[0]:
                    worst_by_rule[(dot_id, rule)] = (value, limit, counts[sample_index])
            start_facing = facings[sample_index - 1].get(dot_id, 0.0)
            end_facing = facings[sample_index].get(dot_id, start_facing)
            rotation = abs((end_facing - start_facing + 180.0) % 360.0 - 180.0) / span
            if rotation > limits.max_rotation_degrees_per_count and rotation > worst_by_rule.get((dot_id, "rotation"), (0.0, 0.0, 0.0))[0]:
                worst_by_rule[(dot_id, "rotation")] = (rotation, limits.max_rotation_degrees_per_count, counts[sample_index])
    labels = {
        "speed": ("travel speed", "Lengthen the move, use jazz run, or reassign the destination."),
        "backward": ("backward travel", "Reduce backward distance or change body/path direction."),
        "lateral": ("lateral travel", "Reduce slide/crab distance or add transition counts."),
        "rotation": ("facing rotation", "Spread the turn over more counts or lower the angle change."),
    }
    for (dot_id, rule), (value, limit, count) in sorted(worst_by_rule.items()):
        profile = physical_limits_for_dot(project, dot_id).profile_name
        label, suggestion = labels[rule]
        unit = "deg/count" if rule == "rotation" else "yd/count"
        warnings.append(SpecializedWarning("warning", rule, dot_id, count, f"{dot_id} reaches {value:.2f} {unit} {label}; {profile} limit is {limit:.2f}.", suggestion))
    for (dot_id, rule), (distance_value, count) in sorted(spatial_by_rule.items()):
        if rule == "route":
            warnings.append(SpecializedWarning("warning", rule, dot_id, count, f"{dot_id} leaves the authored parade-route corridor by {distance_value:.2f} yd.", "Move the path inside the route band or widen the authored route."))
        else:
            warnings.append(SpecializedWarning("error", rule, dot_id, count, f"{dot_id} leaves the performance surface by {distance_value:.2f} yd.", "Move the performer inside the surface bounds or resize the surface."))
    for event in project.choreography:
        if event.event_type != "toss":
            continue
        for dot_id in event.dot_ids:
            if dot_id not in selected:
                continue
            limits = physical_limits_for_dot(project, dot_id)
            if event.revolutions > limits.max_toss_revolutions:
                warnings.append(SpecializedWarning("warning", "toss", dot_id, event.start_count, f"{dot_id} is assigned a {event.revolutions:g}-revolution toss; limit is {limits.max_toss_revolutions:g}.", "Lower the toss or add a performer-specific override after rehearsal verification."))
            next_events = [item for item in project.choreography if dot_id in item.dot_ids and item.start_count >= event.end_count and item.id != event.id]
            if next_events:
                recovery = min(item.start_count for item in next_events) - event.end_count
                if recovery < limits.minimum_recovery_counts:
                    warnings.append(SpecializedWarning("warning", "recovery", dot_id, event.end_count, f"{dot_id} has {recovery:g} recovery counts after {event.name}; minimum is {limits.minimum_recovery_counts:g}.", "Move the next choreography event later or shorten the toss."))
    return warnings
