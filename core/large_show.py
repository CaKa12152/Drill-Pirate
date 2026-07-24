from __future__ import annotations

import csv
import re
from copy import deepcopy
from dataclasses import dataclass, field
from math import atan2, cos, hypot, pi, sin
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from drill_writer.core.models import Dot, DrillProject, DrillSet, Prop, TimingEvent


Point = tuple[float, float]

ROSTER_COLUMN_ALIASES = {
    "id": {"id", "dot", "dot id", "drill number", "number"},
    "name": {"name", "performer", "performer name", "student", "student name"},
    "instrument": {"instrument", "horn", "equipment type"},
    "section": {"section", "subsection", "part"},
    "rank": {"rank", "rank/file", "rank file", "file"},
    "color": {"color", "colour", "dot color"},
    "layer": {"layer", "group", "ensemble"},
    "equipment": {"equipment", "guard equipment", "prop"},
    "prefix": {"prefix", "id prefix", "instrument prefix"},
}

INSTRUMENT_PREFIXES = {
    "flute": "F",
    "piccolo": "P",
    "clarinet": "C",
    "bass clarinet": "BC",
    "alto sax": "AS",
    "alto saxophone": "AS",
    "tenor sax": "TS",
    "tenor saxophone": "TS",
    "baritone sax": "BS",
    "baritone saxophone": "BS",
    "trumpet": "T",
    "mellophone": "M",
    "horn": "H",
    "trombone": "TR",
    "baritone": "B",
    "euphonium": "E",
    "tuba": "TU",
    "sousaphone": "SU",
    "snare": "S",
    "tenor": "TN",
    "quads": "Q",
    "bass drum": "BD",
    "cymbal": "CY",
    "marimba": "MA",
    "vibraphone": "VI",
    "guard": "G",
    "color guard": "CG",
    "rifle": "R",
    "sabre": "SB",
    "saber": "SB",
    "flag": "FL",
}

FAMILY_COLORS = {
    "Brass": "#f2b134",
    "Woodwinds": "#4aa3df",
    "Percussion": "#e24a4a",
    "Guard": "#a66ee8",
    "Front Ensemble": "#5cbf88",
    "Other": "#e53935",
}


@dataclass(slots=True)
class RosterImportResult:
    dots: list[Dot]
    warnings: list[str] = field(default_factory=list)
    column_map: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class CleanupOptions:
    minimum_spacing: float = 1.25
    normalize_intervals: bool = True
    smooth_curvature: bool = True
    remove_overlaps: bool = True
    repair_corners: bool = True
    strength: float = 0.65
    iterations: int = 8


@dataclass(slots=True)
class CleanupReport:
    moved: int = 0
    overlaps_before: int = 0
    overlaps_after: int = 0
    average_interval_before: float = 0.0
    average_interval_after: float = 0.0


@dataclass(slots=True)
class SetDifference:
    dot_id: str
    start: Point
    end: Point
    distance: float
    angle_degrees: float


def normalized_header(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower().replace("_", " ").replace("-", " "))


def roster_column_map(fieldnames: Iterable[str]) -> dict[str, str]:
    normalized = {normalized_header(name): name for name in fieldnames if name}
    mapping: dict[str, str] = {}
    for canonical, aliases in ROSTER_COLUMN_ALIASES.items():
        for alias in aliases:
            if normalized_header(alias) in normalized:
                mapping[canonical] = normalized[normalized_header(alias)]
                break
    return mapping


def performer_family(instrument: str, section: str = "", layer: str = "") -> str:
    value = " ".join((instrument, section, layer)).strip().lower()
    if any(token in value for token in ("guard", "flag", "rifle", "sabre", "saber", "dance")):
        return "Guard"
    if any(token in value for token in ("front ensemble", "pit", "marimba", "vibraphone", "xylophone", "synth")):
        return "Front Ensemble"
    if any(token in value for token in ("snare", "tenor", "quad", "bass drum", "cymbal", "percussion", "battery")):
        return "Percussion"
    if any(token in value for token in ("flute", "piccolo", "clarinet", "sax", "woodwind")):
        return "Woodwinds"
    if any(token in value for token in ("trumpet", "mellophone", "horn", "trombone", "baritone", "euphonium", "tuba", "sousaphone", "brass")):
        return "Brass"
    return "Other"


def automatic_layer(instrument: str, section: str = "") -> str:
    family = performer_family(instrument, section)
    return "Winds" if family in {"Brass", "Woodwinds"} else family


def automatic_section(instrument: str) -> str:
    if not instrument.strip():
        return ""
    family = performer_family(instrument)
    return family if family != "Other" else "Other"


def automatic_prefix(instrument: str, section: str = "") -> str:
    value = normalized_header(instrument or section)
    if value in INSTRUMENT_PREFIXES:
        return INSTRUMENT_PREFIXES[value]
    for name, prefix in sorted(INSTRUMENT_PREFIXES.items(), key=lambda item: len(item[0]), reverse=True):
        if name in value:
            return prefix
    letters = re.findall(r"[a-z0-9]+", value)
    if not letters:
        return "D"
    return "".join(word[0] for word in letters[:2]).upper()


def unique_roster_id(preferred: str, prefix: str, used_ids: set[str], counters: dict[str, int]) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", preferred.strip()).upper()
    if cleaned and cleaned.casefold() not in used_ids:
        used_ids.add(cleaned.casefold())
        return cleaned
    normalized_prefix = re.sub(r"[^A-Za-z0-9]", "", prefix).upper() or "D"
    counter = counters.get(normalized_prefix, 0)
    while True:
        counter += 1
        candidate = f"{normalized_prefix}{counter}"
        if candidate.casefold() not in used_ids:
            counters[normalized_prefix] = counter
            used_ids.add(candidate.casefold())
            return candidate


def block_positions(count: int, *, center: Point = (0.0, 0.0)) -> list[Point]:
    if count <= 0:
        return []
    columns = max(1, min(24, int(round(count ** 0.5 * 1.45))))
    rows = (count + columns - 1) // columns
    spacing_x = min(3.0, 92.0 / max(1, columns - 1))
    spacing_y = min(3.0, 42.0 / max(1, rows - 1))
    start_x = center[0] - (columns - 1) * spacing_x / 2
    start_y = center[1] + (rows - 1) * spacing_y / 2
    return [
        (start_x + (index % columns) * spacing_x, start_y - (index // columns) * spacing_y)
        for index in range(count)
    ]


def parse_roster_csv(path: Path, existing_ids: Iterable[str] = ()) -> RosterImportResult:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError("Roster CSV has no header row.")
        column_map = roster_column_map(reader.fieldnames)
        if not any(key in column_map for key in ("name", "id", "instrument", "section")):
            raise ValueError("Roster CSV needs at least a Name, ID, Instrument, or Section column.")
        rows = list(reader)

    used_ids = {str(value).casefold() for value in existing_ids}
    counters: dict[str, int] = {}
    for value in existing_ids:
        match = re.fullmatch(r"([A-Za-z]+)(\d+)", str(value).strip())
        if match:
            counters[match.group(1).upper()] = max(counters.get(match.group(1).upper(), 0), int(match.group(2)))
    positions = block_positions(len(rows))
    dots: list[Dot] = []
    warnings: list[str] = []
    for row_index, (row, position) in enumerate(zip(rows, positions), start=2):
        value = lambda key: str(row.get(column_map.get(key, ""), "") or "").strip()
        instrument = value("instrument")
        section = value("section") or automatic_section(instrument)
        layer = value("layer") or automatic_layer(instrument, section)
        family = performer_family(instrument, section, layer)
        prefix = value("prefix") or automatic_prefix(instrument, section)
        dot_id = unique_roster_id(value("id"), prefix, used_ids, counters)
        name = value("name") or dot_id
        color = value("color") or FAMILY_COLORS[family]
        if not QColorLike.is_valid(color):
            warnings.append(f"Row {row_index}: invalid color '{color}', using {FAMILY_COLORS[family]}.")
            color = FAMILY_COLORS[family]
        dots.append(
            Dot(
                id=dot_id,
                name=name,
                x=position[0],
                y=position[1],
                color=color,
                section=section,
                instrument=instrument,
                rank=value("rank"),
                equipment=value("equipment"),
                layer=layer,
            )
        )
    return RosterImportResult(dots=dots, warnings=warnings, column_map=column_map)


class QColorLike:
    @staticmethod
    def is_valid(value: str) -> bool:
        return bool(
            re.fullmatch(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", value)
            or re.fullmatch(r"[A-Za-z]+", value)
        )


def merge_roster(project: DrillProject, imported: list[Dot], mode: str = "merge") -> tuple[int, int]:
    normalized_mode = mode.strip().lower()
    by_id = {dot.id.casefold(): dot for dot in project.dots}
    updated = 0
    added = 0
    if normalized_mode == "replace":
        project.dots = deepcopy(imported)
        project.ensure_set_positions()
        return (0, len(imported))
    for imported_dot in imported:
        existing = by_id.get(imported_dot.id.casefold())
        if existing:
            copy_performer_metadata(imported_dot, existing)
            updated += 1
            continue
        project.dots.append(deepcopy(imported_dot))
        by_id[imported_dot.id.casefold()] = project.dots[-1]
        added += 1
    project.ensure_set_positions()
    return updated, added


def copy_performer_metadata(source: Dot, target: Dot) -> None:
    for field_name in ("name", "color", "section", "instrument", "rank", "equipment", "layer"):
        setattr(target, field_name, getattr(source, field_name))


def swap_performers(first: Dot, second: Dot) -> None:
    first_values = {name: getattr(first, name) for name in performer_metadata_fields()}
    second_values = {name: getattr(second, name) for name in performer_metadata_fields()}
    for name in performer_metadata_fields():
        setattr(first, name, second_values[name])
        setattr(second, name, first_values[name])


def performer_metadata_fields() -> tuple[str, ...]:
    return ("name", "color", "section", "instrument", "rank", "equipment", "layer")


def workflow_records(project: DrillProject, key: str) -> list[dict[str, Any]]:
    records = project.workflow.setdefault(key, [])
    if not isinstance(records, list):
        records = []
        project.workflow[key] = records
    return [record for record in records if isinstance(record, dict)]


def new_record_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def create_group(
    project: DrillProject,
    name: str,
    dot_ids: Iterable[str],
    parent_id: str = "",
    *,
    locked: bool = False,
) -> dict[str, Any]:
    valid_ids = {dot.id for dot in project.dots}
    record = {
        "id": new_record_id("group"),
        "name": name.strip() or "Group",
        "parent_id": parent_id,
        "dot_ids": [dot_id for dot_id in dict.fromkeys(dot_ids) if dot_id in valid_ids],
        "locked": bool(locked),
    }
    project.workflow.setdefault("hierarchical_groups", []).append(record)
    return record


def generate_hierarchical_groups(project: DrillProject) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []

    def add(name: str, parent_id: str, dots: list[Dot]) -> dict[str, Any]:
        record = {
            "id": new_record_id("group"),
            "name": name,
            "parent_id": parent_id,
            "dot_ids": [dot.id for dot in dots],
            "locked": False,
        }
        groups.append(record)
        return record

    ensemble = add("Ensemble", "", [])
    families: dict[str, list[Dot]] = {}
    for dot in project.dots:
        families.setdefault(performer_family(dot.instrument, dot.section, dot.layer), []).append(dot)
    for family_name in sorted(families, key=lambda value: (value == "Other", value)):
        family_dots = families[family_name]
        family = add(family_name, ensemble["id"], [])
        sections: dict[str, list[Dot]] = {}
        for dot in family_dots:
            sections.setdefault(dot.section or dot.instrument or "Unassigned", []).append(dot)
        for section_name in sorted(sections):
            section_dots = sections[section_name]
            section = add(section_name, family["id"], [])
            ranks: dict[str, list[Dot]] = {}
            for dot in section_dots:
                ranks.setdefault(dot.rank.strip() or "", []).append(dot)
            if set(ranks) == {""}:
                section["dot_ids"] = [dot.id for dot in section_dots]
                continue
            for rank_name, rank_dots in sorted(ranks.items()):
                if rank_name:
                    add(rank_name, section["id"], rank_dots)
                else:
                    section["dot_ids"].extend(dot.id for dot in rank_dots)
    project.workflow["hierarchical_groups"] = groups
    return groups


def group_by_id(project: DrillProject, group_id: str) -> dict[str, Any] | None:
    return next((group for group in workflow_records(project, "hierarchical_groups") if group.get("id") == group_id), None)


def group_descendant_ids(project: DrillProject, group_id: str) -> set[str]:
    children: dict[str, list[str]] = {}
    for group in workflow_records(project, "hierarchical_groups"):
        children.setdefault(str(group.get("parent_id", "")), []).append(str(group.get("id", "")))
    descendants: set[str] = set()
    stack = list(children.get(group_id, []))
    while stack:
        child_id = stack.pop()
        if child_id in descendants:
            continue
        descendants.add(child_id)
        stack.extend(children.get(child_id, []))
    return descendants


def group_dot_ids(project: DrillProject, group_id: str) -> list[str]:
    group_ids = {group_id, *group_descendant_ids(project, group_id)}
    desired: set[str] = set()
    for group in workflow_records(project, "hierarchical_groups"):
        if str(group.get("id", "")) in group_ids:
            desired.update(str(dot_id) for dot_id in group.get("dot_ids", []))
    return [dot.id for dot in project.dots if dot.id in desired]


def locked_group_dot_ids(project: DrillProject) -> set[str]:
    locked: set[str] = set()
    for group in workflow_records(project, "hierarchical_groups"):
        if bool(group.get("locked", False)):
            locked.update(group_dot_ids(project, str(group.get("id", ""))))
    return locked


def create_linked_formation(
    project: DrillProject,
    name: str,
    master_group_id: str,
    instance_group_ids: Iterable[str],
    mirrored_instance_ids: Iterable[str] = (),
) -> dict[str, Any]:
    master_ids = group_dot_ids(project, master_group_id)
    mirrored = set(mirrored_instance_ids)
    instances: list[dict[str, str]] = []
    for group_id in dict.fromkeys(instance_group_ids):
        if group_id == master_group_id:
            continue
        if len(group_dot_ids(project, group_id)) != len(master_ids):
            raise ValueError("Linked formation groups must contain the same number of marchers.")
        instances.append({"group_id": group_id, "mode": "mirrored" if group_id in mirrored else "repeated"})
    if not master_ids or not instances:
        raise ValueError("Choose a populated master group and at least one matching instance group.")
    record = {
        "id": new_record_id("link"),
        "name": name.strip() or "Linked Formation",
        "master_group_id": master_group_id,
        "instances": instances,
        "attached": True,
    }
    project.workflow.setdefault("linked_formations", []).append(record)
    return record


def linked_group_specs(project: DrillProject, record: dict[str, Any]) -> list[tuple[str, str, list[str]]]:
    specs = [(str(record.get("master_group_id", "")), "repeated", group_dot_ids(project, str(record.get("master_group_id", ""))))]
    for instance in record.get("instances", []):
        if isinstance(instance, dict):
            group_id = str(instance.get("group_id", ""))
            specs.append((group_id, str(instance.get("mode", "repeated")), group_dot_ids(project, group_id)))
    return specs


def expand_linked_position_changes(
    project: DrillProject,
    set_index: int,
    proposed: dict[str, Point],
    locked_ids: Iterable[str] = (),
) -> dict[str, Point]:
    if not 0 <= set_index < len(project.sets) or not proposed:
        return dict(proposed)
    expanded = dict(proposed)
    before = project.sets[set_index].dot_positions
    locked = set(locked_ids)
    explicit_ids = set(proposed)
    for record in workflow_records(project, "linked_formations"):
        if not bool(record.get("attached", True)):
            continue
        specs = linked_group_specs(project, record)
        source_spec = next((spec for spec in specs if explicit_ids.intersection(spec[2])), None)
        if source_spec is None:
            continue
        _source_group_id, source_mode, source_ids = source_spec
        source_lookup = {dot_id: index for index, dot_id in enumerate(source_ids)}
        source_sign = -1.0 if source_mode == "mirrored" else 1.0
        local_deltas: dict[int, Point] = {}
        for dot_id in explicit_ids.intersection(source_lookup):
            if dot_id not in before:
                continue
            old_x, old_y = before[dot_id]
            new_x, new_y = proposed[dot_id]
            local_deltas[source_lookup[dot_id]] = ((new_x - old_x) * source_sign, new_y - old_y)
        for _group_id, target_mode, target_ids in specs:
            target_sign = -1.0 if target_mode == "mirrored" else 1.0
            for index, (delta_x, delta_y) in local_deltas.items():
                if index >= len(target_ids):
                    continue
                target_id = target_ids[index]
                if target_id in explicit_ids or target_id in locked or target_id not in before:
                    continue
                old_x, old_y = before[target_id]
                expanded[target_id] = (old_x + delta_x * target_sign, old_y + delta_y)
    return expanded


def detach_linked_formation(project: DrillProject, link_id: str) -> bool:
    record = next((item for item in workflow_records(project, "linked_formations") if item.get("id") == link_id), None)
    if not record:
        return False
    record["attached"] = False
    return True


def cleanup_formation(positions: dict[str, Point], options: CleanupOptions) -> tuple[dict[str, Point], CleanupReport]:
    if len(positions) < 2:
        return dict(positions), CleanupReport()
    original = dict(positions)
    values = dict(positions)
    report = CleanupReport(
        overlaps_before=count_overlaps(values.values(), options.minimum_spacing),
        average_interval_before=average_nearest_interval(values.values()),
    )
    strength = max(0.0, min(1.0, options.strength))
    iterations = max(1, min(30, options.iterations))
    for _iteration in range(iterations):
        if options.remove_overlaps or options.normalize_intervals:
            values = relax_intervals(values, options.minimum_spacing, strength, options.normalize_intervals)
        if options.smooth_curvature and len(values) >= 4:
            values = smooth_ordered_curve(values, 0.12 * strength, options.repair_corners)
    report.overlaps_after = count_overlaps(values.values(), options.minimum_spacing)
    report.average_interval_after = average_nearest_interval(values.values())
    report.moved = sum(
        1 for dot_id, point in values.items() if point_distance(point, original[dot_id]) > 0.01
    )
    return values, report


def relax_intervals(
    positions: dict[str, Point],
    minimum_spacing: float,
    strength: float,
    normalize: bool,
) -> dict[str, Point]:
    ids = list(positions)
    points = [positions[dot_id] for dot_id in ids]
    target = max(minimum_spacing, average_nearest_interval(points) if normalize else minimum_spacing)
    deltas = [[0.0, 0.0] for _ in points]
    for first in range(len(points) - 1):
        for second in range(first + 1, len(points)):
            first_point, second_point = points[first], points[second]
            delta_x = second_point[0] - first_point[0]
            delta_y = second_point[1] - first_point[1]
            current = hypot(delta_x, delta_y)
            threshold = target * (0.92 if normalize else 1.0)
            if current >= threshold:
                continue
            if current < 0.0001:
                angle = (first * 0.754877666 + second * 0.569840291) * 2 * pi
                unit_x, unit_y = cos(angle), sin(angle)
                current = 0.0001
            else:
                unit_x, unit_y = delta_x / current, delta_y / current
            push = (threshold - current) * 0.5 * max(0.2, strength)
            deltas[first][0] -= unit_x * push
            deltas[first][1] -= unit_y * push
            deltas[second][0] += unit_x * push
            deltas[second][1] += unit_y * push
    return {
        dot_id: (points[index][0] + deltas[index][0], points[index][1] + deltas[index][1])
        for index, dot_id in enumerate(ids)
    }


def smooth_ordered_curve(positions: dict[str, Point], strength: float, preserve_corners: bool) -> dict[str, Point]:
    ids = nearest_neighbor_ids(positions)
    if len(ids) < 4:
        return positions
    points = [positions[dot_id] for dot_id in ids]
    intervals = [point_distance(points[index], points[index + 1]) for index in range(len(points) - 1)]
    median_interval = sorted(intervals)[len(intervals) // 2] if intervals else 0.0
    closed = point_distance(points[0], points[-1]) <= max(1.0, median_interval * 1.7)
    result = dict(positions)
    for index, dot_id in enumerate(ids):
        if not closed and index in {0, len(ids) - 1}:
            continue
        previous = points[(index - 1) % len(points)]
        current = points[index]
        following = points[(index + 1) % len(points)]
        if preserve_corners and corner_angle(previous, current, following) < 105.0:
            continue
        target = ((previous[0] + following[0]) / 2, (previous[1] + following[1]) / 2)
        result[dot_id] = (
            current[0] + (target[0] - current[0]) * strength,
            current[1] + (target[1] - current[1]) * strength,
        )
    return result


def nearest_neighbor_ids(positions: dict[str, Point]) -> list[str]:
    if not positions:
        return []
    remaining = set(positions)
    start = min(remaining, key=lambda dot_id: (positions[dot_id][0], positions[dot_id][1]))
    order = [start]
    remaining.remove(start)
    while remaining:
        current = order[-1]
        next_id = min(remaining, key=lambda dot_id: point_distance(positions[current], positions[dot_id]))
        order.append(next_id)
        remaining.remove(next_id)
    return order


def corner_angle(first: Point, center: Point, last: Point) -> float:
    first_angle = atan2(first[1] - center[1], first[0] - center[0])
    second_angle = atan2(last[1] - center[1], last[0] - center[0])
    difference = abs((second_angle - first_angle + pi) % (2 * pi) - pi)
    return difference * 180.0 / pi


def point_distance(first: Point, second: Point) -> float:
    return hypot(second[0] - first[0], second[1] - first[1])


def count_overlaps(points: Iterable[Point], minimum_spacing: float) -> int:
    values = list(points)
    return sum(
        point_distance(values[first], values[second]) < minimum_spacing
        for first in range(len(values) - 1)
        for second in range(first + 1, len(values))
    )


def average_nearest_interval(points: Iterable[Point]) -> float:
    values = list(points)
    if len(values) < 2:
        return 0.0
    nearest = [
        min(point_distance(point, other) for other_index, other in enumerate(values) if other_index != index)
        for index, point in enumerate(values)
    ]
    return sum(nearest) / len(nearest)


def compare_sets(project: DrillProject, first_index: int, second_index: int) -> list[SetDifference]:
    if not (0 <= first_index < len(project.sets) and 0 <= second_index < len(project.sets)):
        return []
    first = project.sets[first_index].dot_positions
    second = project.sets[second_index].dot_positions
    differences: list[SetDifference] = []
    for dot in project.dots:
        if dot.id not in first or dot.id not in second:
            continue
        start, end = first[dot.id], second[dot.id]
        differences.append(
            SetDifference(
                dot_id=dot.id,
                start=start,
                end=end,
                distance=point_distance(start, end),
                angle_degrees=(atan2(end[1] - start[1], end[0] - start[0]) * 180.0 / pi) % 360.0,
            )
        )
    return sorted(differences, key=lambda item: item.distance, reverse=True)


def save_formation_variation(
    project: DrillProject,
    name: str,
    set_index: int,
    dot_ids: Iterable[str] = (),
) -> dict[str, Any]:
    if not 0 <= set_index < len(project.sets):
        raise ValueError("Variation set is out of range.")
    drill_set = project.sets[set_index]
    selected = set(dot_ids) or set(drill_set.dot_positions)
    record = {
        "id": new_record_id("variation"),
        "name": name.strip() or f"Variation {len(workflow_records(project, 'formation_variations')) + 1}",
        "set_index": set_index,
        "dot_ids": [dot.id for dot in project.dots if dot.id in selected],
        "dot_positions": {
            dot_id: [drill_set.dot_positions[dot_id][0], drill_set.dot_positions[dot_id][1]]
            for dot_id in selected
            if dot_id in drill_set.dot_positions
        },
        "dot_facings": {dot_id: drill_set.dot_facings[dot_id] for dot_id in selected if dot_id in drill_set.dot_facings},
        "count_facings": deepcopy({dot_id: drill_set.count_facings[dot_id] for dot_id in selected if dot_id in drill_set.count_facings}),
        "count_positions": deepcopy({dot_id: drill_set.count_positions[dot_id] for dot_id in selected if dot_id in drill_set.count_positions}),
        "path_anchors": {
            dot_id: [[point[0], point[1]] for point in drill_set.path_anchors.get(dot_id, [])]
            for dot_id in selected
            if drill_set.path_anchors.get(dot_id)
        },
        "path_controls": deepcopy({dot_id: drill_set.path_controls[dot_id] for dot_id in selected if dot_id in drill_set.path_controls}),
        "move_timings": deepcopy({dot_id: drill_set.move_timings[dot_id] for dot_id in selected if dot_id in drill_set.move_timings}),
        "movement_styles": {
            dot_id: drill_set.movement_styles[dot_id].value
            for dot_id in selected
            if dot_id in drill_set.movement_styles
        },
    }
    project.workflow.setdefault("formation_variations", []).append(record)
    return record


def variation_positions(record: dict[str, Any]) -> dict[str, Point]:
    positions: dict[str, Point] = {}
    for dot_id, value in dict(record.get("dot_positions", {})).items():
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            positions[str(dot_id)] = (float(value[0]), float(value[1]))
        elif isinstance(value, dict):
            positions[str(dot_id)] = (float(value.get("x", 0.0)), float(value.get("y", 0.0)))
    return positions


def transfer_project_content(
    source: DrillProject,
    destination: DrillProject,
    source_set_index: int,
    destination_set_index: int,
    *,
    formation: bool = True,
    timing_map: bool = False,
    props: bool = False,
) -> dict[str, int]:
    if not (0 <= source_set_index < len(source.sets) and 0 <= destination_set_index < len(destination.sets)):
        raise ValueError("Source or destination set is out of range.")
    counts = {"formation": 0, "timing": 0, "props": 0}
    source_set = source.sets[source_set_index]
    destination_set = destination.sets[destination_set_index]
    if formation:
        source_ids = [dot.id for dot in source.dots if dot.id in source_set.dot_positions]
        destination_ids = [dot.id for dot in destination.dots if dot.id in destination_set.dot_positions]
        destination_id_set = set(destination_ids)
        exact = [dot_id for dot_id in source_ids if dot_id in destination_id_set]
        remaining_source = [dot_id for dot_id in source_ids if dot_id not in set(exact)]
        remaining_destination = [dot_id for dot_id in destination_ids if dot_id not in set(exact)]
        pairs = [(dot_id, dot_id) for dot_id in exact] + list(zip(remaining_source, remaining_destination))
        for source_id, destination_id in pairs:
            destination_set.dot_positions[destination_id] = tuple(source_set.dot_positions[source_id])
            if source_id in source_set.dot_facings:
                destination_set.dot_facings[destination_id] = float(source_set.dot_facings[source_id])
            if source_id in source_set.count_facings:
                destination_set.count_facings[destination_id] = deepcopy(source_set.count_facings[source_id])
            if source_id in source_set.path_anchors:
                destination_set.path_anchors[destination_id] = deepcopy(source_set.path_anchors[source_id])
            if source_id in source_set.path_controls:
                destination_set.path_controls[destination_id] = deepcopy(source_set.path_controls[source_id])
            if source_id in source_set.count_positions:
                destination_set.count_positions[destination_id] = deepcopy(source_set.count_positions[source_id])
            if source_id in source_set.move_timings:
                destination_set.move_timings[destination_id] = deepcopy(source_set.move_timings[source_id])
            counts["formation"] += 1
    if timing_map:
        destination.metadata.initial_tempo = source.metadata.initial_tempo
        destination.metadata.time_signature = source.metadata.time_signature
        destination.timing_events = [TimingEvent.from_json(event.to_json()) for event in source.timing_events]
        destination.markers = deepcopy(source.markers)
        counts["timing"] = len(destination.timing_events) + len(destination.markers)
    if props:
        existing_ids = {prop.id for prop in destination.props}
        for source_prop in source.props:
            prop = deepcopy(source_prop)
            base_id = prop.id
            suffix = 2
            while prop.id in existing_ids:
                prop.id = f"{base_id}_{suffix}"
                suffix += 1
            existing_ids.add(prop.id)
            destination.props.append(prop)
            destination_state = deepcopy(source_set.prop_positions.get(source_prop.id, {}))
            for drill_set in destination.sets:
                drill_set.prop_positions[prop.id] = deepcopy(destination_state) if destination_state else {
                    "x": prop.x,
                    "y": prop.y,
                    "width": prop.width,
                    "height": prop.height,
                    "rotation": prop.rotation,
                }
            counts["props"] += 1
    destination.ensure_set_positions()
    return counts
