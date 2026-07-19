from __future__ import annotations

import struct
import zipfile
from copy import deepcopy
from dataclasses import dataclass
from math import atan2, cos, hypot, radians, sin
from pathlib import Path
from xml.etree import ElementTree

from drill_writer.core.animation import interpolate_project, interpolate_props
from drill_writer.core.models import (
    DrillProject,
    DrillSet,
    ImportedScore,
    Marker,
    MusicPhrase,
    ScoreMeasure,
    ScoreTempoChange,
    StoryboardScene,
    TimingEvent,
    Transition,
)
from drill_writer.core.timing import set_index_for_count


Point = tuple[float, float]


class ScoreImportError(ValueError):
    pass


@dataclass(slots=True)
class PlannedSet:
    name: str
    start_count: int
    end_count: int
    phrase_id: str
    tempo: float
    intensity: float
    suggested_motion: str


@dataclass(slots=True)
class ShowDesignSuggestion:
    phrase_id: str
    phrase_name: str
    start_count: int
    end_count: int
    set_count: int
    motion: str
    confidence: float
    existing_motion_yards: float
    rationale: str


def import_score(path: Path) -> ImportedScore:
    source = Path(path)
    if not source.is_file():
        raise ScoreImportError(f"Score file does not exist: {source}")
    suffix = source.suffix.lower()
    try:
        if suffix in {".mid", ".midi"}:
            score = parse_midi_score(source.read_bytes(), source.stem)
        elif suffix in {".xml", ".musicxml", ".mxl"}:
            score = parse_musicxml_score(read_musicxml_bytes(source), source.stem)
        else:
            raise ScoreImportError("Choose a MusicXML (.musicxml/.xml/.mxl) or MIDI (.mid/.midi) score.")
    except ScoreImportError:
        raise
    except Exception as exc:
        raise ScoreImportError(f"Could not import '{source.name}': {exc}") from exc
    score.source_file = str(source)
    return score


def read_musicxml_bytes(path: Path) -> bytes:
    if path.suffix.lower() != ".mxl":
        return path.read_bytes()
    try:
        with zipfile.ZipFile(path) as archive:
            root_file = ""
            if "META-INF/container.xml" in archive.namelist():
                container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
                root_node = next((node for node in container.iter() if local_name(node.tag) == "rootfile"), None)
                if root_node is not None:
                    root_file = str(root_node.attrib.get("full-path", ""))
            if not root_file:
                root_file = next(
                    (name for name in archive.namelist() if name.lower().endswith((".musicxml", ".xml")) and not name.startswith("META-INF/")),
                    "",
                )
            if not root_file:
                raise ScoreImportError("The compressed MusicXML file does not contain a score document.")
            return archive.read(root_file)
    except zipfile.BadZipFile as exc:
        raise ScoreImportError("The .mxl file is not a valid compressed MusicXML document.") from exc


def parse_musicxml_score(data: bytes, fallback_title: str = "Imported Score") -> ImportedScore:
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise ScoreImportError(f"MusicXML is malformed: {exc}") from exc
    root_type = local_name(root.tag)
    if root_type not in {"score-partwise", "score-timewise"}:
        raise ScoreImportError("This XML file is not a MusicXML score-partwise or score-timewise document.")

    title = first_descendant_text(root, "work-title") or first_descendant_text(root, "movement-title") or fallback_title
    composer = ""
    for node in root.iter():
        if local_name(node.tag) == "creator" and str(node.attrib.get("type", "")).lower() == "composer":
            composer = clean_text(node.text)
            if composer:
                break
    if root_type == "score-timewise":
        timewise_measures = [node for node in root if local_name(node.tag) == "measure"]
        part_counts: dict[str, int] = {}
        for measure in timewise_measures:
            for part_node in measure:
                if local_name(part_node.tag) == "part":
                    part_id = str(part_node.attrib.get("id", ""))
                    part_counts[part_id] = part_counts.get(part_id, 0) + 1
        if not part_counts:
            raise ScoreImportError("MusicXML contains no score parts.")
        selected_part = max(part_counts, key=part_counts.get)
        measure_nodes = []
        for measure in timewise_measures:
            part_node = next(
                (
                    child
                    for child in measure
                    if local_name(child.tag) == "part" and str(child.attrib.get("id", "")) == selected_part
                ),
                None,
            )
            if part_node is None:
                continue
            converted = ElementTree.Element("measure", dict(measure.attrib))
            converted.extend(deepcopy(list(part_node)))
            measure_nodes.append(converted)
    else:
        parts = [node for node in root if local_name(node.tag) == "part"]
        if not parts:
            raise ScoreImportError("MusicXML contains no score parts.")
        part = max(parts, key=lambda node: sum(1 for child in node if local_name(child.tag) == "measure"))
        measure_nodes = [child for child in part if local_name(child.tag) == "measure"]
    if not measure_nodes:
        raise ScoreImportError("MusicXML contains no measures.")

    divisions = 1.0
    beats = 4.0
    beat_type = 4.0
    current_tempo = 0.0
    count_cursor = 1.0
    pending_boundary = False
    measures: list[ScoreMeasure] = []
    tempo_changes: list[ScoreTempoChange] = []
    warnings: list[str] = []

    for measure_index, measure_node in enumerate(measure_nodes):
        cursor = 0.0
        maximum_cursor = 0.0
        rehearsal_mark = ""
        measure_boundary = pending_boundary
        pending_boundary = False
        measure_tempo = current_tempo
        for child in measure_node:
            tag = local_name(child.tag)
            if tag == "attributes":
                divisions_text = first_descendant_text(child, "divisions")
                if divisions_text:
                    divisions = max(0.001, number(divisions_text, divisions))
                time_node = first_descendant(child, "time")
                if time_node is not None:
                    beats_text = first_descendant_text(time_node, "beats")
                    beat_type_text = first_descendant_text(time_node, "beat-type")
                    beats = parse_beats(beats_text, beats)
                    beat_type = max(1.0, number(beat_type_text, beat_type))
            elif tag == "direction":
                rehearsal = first_descendant_text(child, "rehearsal")
                if rehearsal:
                    rehearsal_mark = rehearsal
                    measure_boundary = True
                tempo = direction_tempo(child)
                if tempo > 0:
                    offset = number(first_descendant_text(child, "offset"), 0.0)
                    tempo_count = count_cursor + max(0.0, cursor + offset) / divisions
                    tempo_changes.append(ScoreTempoChange(tempo_count, tempo, rehearsal or f"Tempo {tempo:g}"))
                    current_tempo = tempo
                    if measure_tempo <= 0 or abs(tempo_count - count_cursor) < 0.001:
                        measure_tempo = tempo
            elif tag == "note":
                duration = number(first_descendant_text(child, "duration"), 0.0)
                if first_descendant(child, "chord") is None:
                    cursor += duration
                    maximum_cursor = max(maximum_cursor, cursor)
            elif tag == "backup":
                cursor = max(0.0, cursor - number(first_descendant_text(child, "duration"), 0.0))
            elif tag == "forward":
                cursor += number(first_descendant_text(child, "duration"), 0.0)
                maximum_cursor = max(maximum_cursor, cursor)
            elif tag == "barline":
                bar_style = first_descendant_text(child, "bar-style").lower()
                if bar_style in {"light-light", "light-heavy", "heavy-light", "heavy-heavy"}:
                    pending_boundary = True
                if first_descendant(child, "repeat") is not None and "repeat signs" not in warnings:
                    warnings.append("Repeat signs were imported in written order and were not expanded.")

        expected_counts = beats * 4.0 / beat_type
        actual_counts = maximum_cursor / divisions if maximum_cursor > 0 else expected_counts
        implicit = str(measure_node.attrib.get("implicit", "")).lower() == "yes"
        if not implicit and actual_counts < expected_counts * 0.25:
            actual_counts = expected_counts
        duration_counts = max(0.001, actual_counts)
        measure_number = str(measure_node.attrib.get("number", measure_index + 1))
        measures.append(
            ScoreMeasure(
                number=measure_number,
                start_count=count_cursor,
                duration_counts=duration_counts,
                time_signature=f"{format_number(beats)}/{format_number(beat_type)}",
                tempo=measure_tempo,
                rehearsal_mark=rehearsal_mark,
                phrase_boundary=measure_boundary,
            )
        )
        count_cursor += duration_counts

    tempo_changes = deduplicate_tempos(tempo_changes)
    if not tempo_changes:
        warnings.append("No tempo markings were found; the project tempo will remain unchanged.")
    if not any(measure.rehearsal_mark for measure in measures):
        warnings.append("No rehearsal marks were found; phrase detection will use measure grouping and barlines.")
    return ImportedScore(
        title=title,
        composer=composer,
        source_format="musicxml",
        measures=measures,
        tempo_changes=tempo_changes,
        warnings=warnings,
    )


def parse_midi_score(data: bytes, fallback_title: str = "Imported MIDI") -> ImportedScore:
    if len(data) < 14 or data[:4] != b"MThd":
        raise ScoreImportError("MIDI header is missing or invalid.")
    header_length = struct.unpack(">I", data[4:8])[0]
    if header_length < 6 or len(data) < 8 + header_length:
        raise ScoreImportError("MIDI header is truncated.")
    midi_format, track_count, division = struct.unpack(">HHH", data[8:14])
    if midi_format not in {0, 1}:
        raise ScoreImportError(f"MIDI format {midi_format} is not supported; use format 0 or 1.")
    if division & 0x8000:
        raise ScoreImportError("SMPTE-timed MIDI is not supported; export using pulses per quarter note.")
    if division <= 0:
        raise ScoreImportError("MIDI pulses-per-quarter value is invalid.")

    offset = 8 + header_length
    events: list[tuple[int, int, bytes]] = []
    max_tick = 0
    title = fallback_title
    parsed_tracks = 0
    while offset + 8 <= len(data) and parsed_tracks < track_count:
        chunk_type = data[offset : offset + 4]
        chunk_length = struct.unpack(">I", data[offset + 4 : offset + 8])[0]
        chunk = data[offset + 8 : offset + 8 + chunk_length]
        offset += 8 + chunk_length
        if chunk_type != b"MTrk":
            continue
        track_events, track_end = parse_midi_track(chunk)
        parsed_tracks += 1
        max_tick = max(max_tick, track_end)
        events.extend(track_events)
        for tick, meta_type, payload in track_events:
            if meta_type == 0x03 and tick == 0:
                candidate = decode_midi_text(payload)
                if candidate and title == fallback_title:
                    title = candidate
    if parsed_tracks != track_count:
        raise ScoreImportError("MIDI file ended before all declared tracks were read.")

    tempo_events: list[tuple[int, float, str]] = []
    meter_events: list[tuple[int, int, int]] = [(0, 4, 4)]
    markers: list[tuple[int, str]] = []
    for tick, meta_type, payload in events:
        if meta_type == 0x51 and len(payload) == 3:
            microseconds = int.from_bytes(payload, "big")
            if microseconds > 0:
                tempo_events.append((tick, 60_000_000.0 / microseconds, "MIDI tempo"))
        elif meta_type == 0x58 and len(payload) >= 2:
            meter_events.append((tick, max(1, payload[0]), 2 ** min(7, payload[1])))
        elif meta_type in {0x06, 0x07}:
            text = decode_midi_text(payload)
            if text:
                markers.append((tick, text))
    if not any(tick == 0 for tick, _tempo, _label in tempo_events):
        tempo_events.append((0, 120.0, "MIDI tempo"))
    tempo_events.sort(key=lambda item: item[0])
    meter_events = sorted({(tick, numerator, denominator) for tick, numerator, denominator in meter_events})
    max_tick = max(max_tick, max((tick for tick, _label in markers), default=0), division * 4)

    measures: list[ScoreMeasure] = []
    tick = 0
    measure_number = 1
    while tick < max_tick:
        numerator, denominator = active_meter(meter_events, tick)
        expected_ticks = max(1, round(division * 4.0 * numerator / denominator))
        next_meter_tick = next((event_tick for event_tick, _num, _den in meter_events if event_tick > tick), None)
        end_tick = min(max_tick, tick + expected_ticks)
        if next_meter_tick is not None and next_meter_tick < end_tick:
            end_tick = next_meter_tick
        duration_counts = max(0.001, (end_tick - tick) / division)
        rehearsal = next((label for marker_tick, label in markers if tick <= marker_tick < end_tick), "")
        tempo = active_tempo(tempo_events, tick)
        measures.append(
            ScoreMeasure(
                number=str(measure_number),
                start_count=tick / division + 1.0,
                duration_counts=duration_counts,
                time_signature=f"{numerator}/{denominator}",
                tempo=tempo,
                rehearsal_mark=rehearsal,
                phrase_boundary=bool(rehearsal) or any(event_tick == tick for event_tick, _num, _den in meter_events[1:]),
            )
        )
        measure_number += 1
        tick = end_tick

    tempo_changes = [
        ScoreTempoChange(tick / division + 1.0, tempo, label)
        for tick, tempo, label in tempo_events
    ]
    warnings = []
    if not markers:
        warnings.append("No MIDI markers or cue points were found; phrase detection will use measure grouping.")
    return ImportedScore(
        title=title,
        source_format="midi",
        measures=measures,
        tempo_changes=deduplicate_tempos(tempo_changes),
        warnings=warnings,
    )


def parse_midi_track(data: bytes) -> tuple[list[tuple[int, int, bytes]], int]:
    events: list[tuple[int, int, bytes]] = []
    position = 0
    absolute_tick = 0
    running_status: int | None = None
    while position < len(data):
        delta, position = read_variable_length(data, position)
        absolute_tick += delta
        if position >= len(data):
            break
        status = data[position]
        if status & 0x80:
            position += 1
            if status < 0xF0:
                running_status = status
        elif running_status is not None:
            status = running_status
        else:
            raise ScoreImportError("MIDI running status appears before a channel status byte.")

        if status == 0xFF:
            running_status = None
            if position >= len(data):
                raise ScoreImportError("MIDI meta event is truncated.")
            meta_type = data[position]
            position += 1
            length, position = read_variable_length(data, position)
            payload = data[position : position + length]
            if len(payload) != length:
                raise ScoreImportError("MIDI meta event payload is truncated.")
            position += length
            events.append((absolute_tick, meta_type, payload))
            if meta_type == 0x2F:
                break
        elif status in {0xF0, 0xF7}:
            running_status = None
            length, position = read_variable_length(data, position)
            position += length
            if position > len(data):
                raise ScoreImportError("MIDI system-exclusive event is truncated.")
        else:
            message = status & 0xF0
            length = 1 if message in {0xC0, 0xD0} else 2
            position += length
            if position > len(data):
                raise ScoreImportError("MIDI channel event is truncated.")
    return events, absolute_tick


def read_variable_length(data: bytes, position: int) -> tuple[int, int]:
    value = 0
    for _index in range(4):
        if position >= len(data):
            raise ScoreImportError("MIDI variable-length value is truncated.")
        byte = data[position]
        position += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, position
    raise ScoreImportError("MIDI variable-length value exceeds four bytes.")


def detect_music_phrases(score: ImportedScore, measures_per_phrase: int = 4) -> list[MusicPhrase]:
    measures = score.measures
    if not measures:
        return []
    group_size = max(1, int(measures_per_phrase))
    natural_boundaries = {0}
    for index, measure in enumerate(measures):
        if index and (measure.phrase_boundary or measure.rehearsal_mark):
            natural_boundaries.add(index)
        if index and measure.time_signature != measures[index - 1].time_signature:
            natural_boundaries.add(index)
    boundaries = set(natural_boundaries)
    ordered_natural = sorted([*natural_boundaries, len(measures)])
    for start, end in zip(ordered_natural, ordered_natural[1:]):
        index = start + group_size
        while index < end:
            boundaries.add(index)
            index += group_size
    ordered = sorted([*boundaries, len(measures)])
    phrases: list[MusicPhrase] = []
    for phrase_index, (start_index, end_index) in enumerate(zip(ordered, ordered[1:]), start=1):
        if start_index >= end_index:
            continue
        first = measures[start_index]
        last = measures[end_index - 1]
        mark = first.rehearsal_mark.strip()
        name = mark or f"Phrase {phrase_index}"
        average_tempo = sum(measure.tempo for measure in measures[start_index:end_index] if measure.tempo > 0)
        tempo_count = sum(1 for measure in measures[start_index:end_index] if measure.tempo > 0)
        average_tempo = average_tempo / tempo_count if tempo_count else 120.0
        intensity = max(0.05, min(1.0, 0.2 + (average_tempo - 60.0) / 180.0 + (0.12 if mark else 0.0)))
        phrases.append(
            MusicPhrase(
                id=f"phrase-{start_index + 1}-{end_index}",
                name=name,
                start_count=first.start_count,
                end_count=last.end_count,
                start_measure=first.number,
                end_measure=last.number,
                rehearsal_mark=mark,
                intensity=intensity,
            )
        )
    return phrases


def storyboard_from_phrases(phrases: list[MusicPhrase]) -> list[StoryboardScene]:
    colors = ("#7c3aed", "#2563eb", "#0891b2", "#059669", "#d97706", "#dc2626")
    scenes = []
    for index, phrase in enumerate(sorted(phrases, key=lambda item: item.start_count)):
        pacing = "Driving" if phrase.intensity >= 0.72 else "Spacious" if phrase.intensity <= 0.32 else "Moderate"
        scenes.append(
            StoryboardScene(
                id=f"scene-{phrase.id}",
                name=phrase.name,
                start_count=phrase.start_count,
                end_count=phrase.end_count,
                movement=f"Movement {index + 1}",
                visual_pacing=pacing,
                production_notes=phrase.notes,
                color=colors[index % len(colors)],
            )
        )
    return scenes


def synchronize_score_timing(project: DrillProject) -> None:
    score = project.imported_score
    if score is None:
        return
    project.timing_events = [event for event in project.timing_events if not event.label.startswith("[Score]")]
    project.markers = [marker for marker in project.markers if not marker.label.startswith("[Score]")]
    for change in score.tempo_changes:
        project.timing_events.append(
            TimingEvent("tempo", change.count, tempo=change.tempo, label=f"[Score] {change.label or f'Tempo {change.tempo:g}'}")
        )
    previous_meter = ""
    for measure in score.measures:
        if measure.time_signature != previous_meter:
            project.timing_events.append(
                TimingEvent("meter", measure.start_count, label=f"[Score] Meter {measure.time_signature}")
            )
            previous_meter = measure.time_signature
        if measure.rehearsal_mark:
            project.markers.append(Marker(measure.start_count, f"[Score] {measure.rehearsal_mark}"))
    project.timing_events.sort(key=lambda item: (item.count, item.event_type))
    project.markers.sort(key=lambda item: (item.count, item.label))
    if score.tempo_changes and score.tempo_changes[0].count <= 1.001:
        project.metadata.initial_tempo = score.tempo_changes[0].tempo
    if score.measures:
        project.metadata.time_signature = score.measures[0].time_signature


def plan_phrase_sets(
    score: ImportedScore,
    phrases: list[MusicPhrase],
    target_counts: int = 8,
) -> list[PlannedSet]:
    target = max(1, int(target_counts))
    measure_ends = sorted({max(1, int(round(measure.end_count))) for measure in score.measures})
    plans: list[PlannedSet] = []
    for phrase in sorted(phrases, key=lambda item: item.start_count):
        start = max(1, int(round(phrase.start_count)))
        final = max(start, int(round(phrase.end_count)))
        part = 1
        while start <= final:
            ideal_end = min(final, start + target - 1)
            candidates = [end for end in measure_ends if start <= end <= final]
            if candidates and ideal_end < final:
                end = min(candidates, key=lambda value: (abs(value - ideal_end), value < ideal_end, value))
                if end < start:
                    end = ideal_end
            else:
                end = ideal_end
            name = phrase.name if start == int(round(phrase.start_count)) and end == final else f"{phrase.name} {part}"
            tempo = score_tempo_at_count(score, start)
            motion = default_motion_for_phrase(phrase, part - 1)
            plans.append(PlannedSet(name, start, end, phrase.id, tempo, phrase.intensity, motion))
            start = end + 1
            part += 1
    return normalize_planned_sets(plans)


def suggest_show_design(
    project: DrillProject,
    phrases: list[MusicPhrase] | None = None,
    target_counts: int = 8,
) -> list[ShowDesignSuggestion]:
    score = project.imported_score
    if score is None:
        return []
    active_phrases = phrases if phrases is not None else project.music_phrases
    suggestions = []
    for plan in plan_phrase_sets(score, active_phrases, target_counts):
        start_positions = project_positions_at_count(project, plan.start_count)
        end_positions = project_positions_at_count(project, plan.end_count)
        shared = start_positions.keys() & end_positions.keys()
        travel = (
            sum(hypot(end_positions[dot_id][0] - start_positions[dot_id][0], end_positions[dot_id][1] - start_positions[dot_id][1]) for dot_id in shared)
            / len(shared)
            if shared
            else 0.0
        )
        phrase = next((item for item in active_phrases if item.id == plan.phrase_id), None)
        if travel >= 0.75:
            motion = "Preserve authored transition"
            rationale = f"Existing drill already averages {travel:.1f} yd of travel. Keep the authored form change."
            confidence = 0.94
        elif plan.intensity >= 0.76:
            motion = "Expand + rotate"
            rationale = "High musical intensity with a mostly static form supports a controlled expansion and rotation."
            confidence = 0.82
        elif plan.intensity <= 0.30:
            motion = "Hold / breathe"
            rationale = "Low phrase intensity favors visual clarity, sustained form, and restrained travel."
            confidence = 0.86
        elif phrase and phrase.rehearsal_mark:
            motion = "Impact set"
            rationale = f"Rehearsal mark {phrase.rehearsal_mark} is a strong structural boundary for a new picture."
            confidence = 0.80
        else:
            motion = plan.suggested_motion
            rationale = "Moderate phrase energy supports a readable transition without replacing existing authored drill."
            confidence = 0.72
        suggestions.append(
            ShowDesignSuggestion(
                phrase_id=plan.phrase_id,
                phrase_name=plan.name,
                start_count=plan.start_count,
                end_count=plan.end_count,
                set_count=plan.end_count - plan.start_count + 1,
                motion=motion,
                confidence=confidence,
                existing_motion_yards=travel,
                rationale=rationale,
            )
        )
    return suggestions


def generate_sets_from_phrases(
    project: DrillProject,
    phrases: list[MusicPhrase] | None = None,
    target_counts: int = 8,
    motion_profile: str = "preserve",
) -> list[DrillSet]:
    score = project.imported_score
    if score is None:
        return []
    active_phrases = phrases if phrases is not None else project.music_phrases
    plans = plan_phrase_sets(score, active_phrases, target_counts)
    suggestions = suggest_show_design(project, active_phrases, target_counts)
    suggestion_by_range = {(item.start_count, item.end_count): item for item in suggestions}
    generated: list[DrillSet] = []
    previous_positions = opening_positions(project)
    for plan in plans:
        authored_positions = project_positions_at_count(project, plan.end_count)
        positions = dict(authored_positions or previous_positions)
        suggestion = suggestion_by_range.get((plan.start_count, plan.end_count))
        if motion_profile != "preserve" and suggestion and suggestion.existing_motion_yards < 0.75:
            positions = apply_suggested_motion(
                previous_positions or positions,
                suggestion.motion,
                plan.intensity,
                motion_profile,
            )
        prop_positions = project_props_at_count(project, plan.end_count)
        generated.append(
            DrillSet(
                name=plan.name,
                start_count=plan.start_count,
                end_count=plan.end_count,
                tempo=plan.tempo or None,
                dot_positions=positions,
                prop_positions=prop_positions,
                transition=Transition.EASE_IN_OUT if motion_profile != "preserve" else Transition.LINEAR,
            )
        )
        previous_positions = positions
    return generated


def apply_suggested_motion(
    positions: dict[str, Point],
    motion: str,
    intensity: float,
    profile: str,
) -> dict[str, Point]:
    if not positions or motion in {"Hold / breathe", "Preserve authored transition"}:
        return dict(positions)
    center_x = sum(point[0] for point in positions.values()) / len(positions)
    center_y = sum(point[1] for point in positions.values()) / len(positions)
    strength = 0.6 if profile == "gentle" else 1.0 if profile == "dynamic" else 1.3
    scale = 1.0
    angle = 0.0
    offset = (0.0, 0.0)
    normalized = motion.lower()
    if "expand" in normalized or "impact" in normalized:
        scale = 1.0 + (0.05 + intensity * 0.08) * strength
    if "rotate" in normalized:
        angle = radians((4.0 + intensity * 8.0) * strength)
    if "travel" in normalized or "translate" in normalized:
        offset = ((1.0 + intensity * 2.0) * strength, 0.0)
    cosine = cos(angle)
    sine = sin(angle)
    return {
        dot_id: (
            center_x + (point[0] - center_x) * scale * cosine - (point[1] - center_y) * scale * sine + offset[0],
            center_y + (point[0] - center_x) * scale * sine + (point[1] - center_y) * scale * cosine + offset[1],
        )
        for dot_id, point in positions.items()
    }


def score_tempo_at_count(score: ImportedScore, count: float) -> float:
    tempo = next((measure.tempo for measure in score.measures if measure.tempo > 0), 0.0)
    for change in sorted(score.tempo_changes, key=lambda item: item.count):
        if change.count > count:
            break
        tempo = change.tempo
    return tempo


def project_positions_at_count(project: DrillProject, count: float) -> dict[str, Point]:
    if not project.sets:
        return {dot.id: (dot.x, dot.y) for dot in project.dots}
    if count > project.sets[-1].end_count:
        return dict(project.sets[-1].dot_positions)
    if count < project.sets[0].start_count:
        return opening_positions(project)
    set_index = set_index_for_count(project, count)
    return interpolate_project(project, set_index, count)


def project_props_at_count(project: DrillProject, count: float) -> dict[str, dict[str, float]]:
    if not project.sets:
        return {}
    if count > project.sets[-1].end_count:
        return {prop_id: dict(state) for prop_id, state in project.sets[-1].prop_positions.items()}
    set_index = set_index_for_count(project, count)
    return {prop_id: dict(state) for prop_id, state in interpolate_props(project, set_index, count).items()}


def opening_positions(project: DrillProject) -> dict[str, Point]:
    if project.sets and project.sets[0].count_positions:
        start_count = float(project.sets[0].start_count)
        return {
            dot.id: project.sets[0].count_positions.get(dot.id, {}).get(start_count, (dot.x, dot.y))
            for dot in project.dots
        }
    return {dot.id: (dot.x, dot.y) for dot in project.dots}


def default_motion_for_phrase(phrase: MusicPhrase, index: int) -> str:
    if phrase.intensity >= 0.76:
        return "Expand + rotate"
    if phrase.intensity <= 0.30:
        return "Hold / breathe"
    return "Controlled travel" if index % 2 == 0 else "Shape change"


def normalize_planned_sets(plans: list[PlannedSet]) -> list[PlannedSet]:
    normalized: list[PlannedSet] = []
    next_start = 1
    for plan in sorted(plans, key=lambda item: (item.start_count, item.end_count)):
        start = max(next_start, plan.start_count)
        end = max(start, plan.end_count)
        normalized.append(
            PlannedSet(plan.name, start, end, plan.phrase_id, plan.tempo, plan.intensity, plan.suggested_motion)
        )
        next_start = end + 1
    return normalized


def direction_tempo(direction) -> float:
    for node in direction.iter():
        if local_name(node.tag) == "sound" and node.attrib.get("tempo"):
            tempo = number(str(node.attrib.get("tempo", "")), 0.0)
            if tempo > 0:
                return tempo
    return number(first_descendant_text(direction, "per-minute"), 0.0)


def active_meter(events: list[tuple[int, int, int]], tick: int) -> tuple[int, int]:
    value = (4, 4)
    for event_tick, numerator, denominator in events:
        if event_tick > tick:
            break
        value = (numerator, denominator)
    return value


def active_tempo(events: list[tuple[int, float, str]], tick: int) -> float:
    value = 120.0
    for event_tick, tempo, _label in events:
        if event_tick > tick:
            break
        value = tempo
    return value


def deduplicate_tempos(changes: list[ScoreTempoChange]) -> list[ScoreTempoChange]:
    by_count: dict[float, ScoreTempoChange] = {}
    for change in sorted(changes, key=lambda item: item.count):
        if change.tempo > 0:
            by_count[round(change.count, 6)] = change
    return list(by_count.values())


def decode_midi_text(payload: bytes) -> str:
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return payload.decode(encoding).strip("\x00 \t\r\n")
        except UnicodeDecodeError:
            continue
    return ""


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def first_descendant(node, name: str):
    return next((child for child in node.iter() if local_name(child.tag) == name), None)


def first_descendant_text(node, name: str) -> str:
    child = first_descendant(node, name)
    return clean_text(child.text) if child is not None else ""


def clean_text(value: str | None) -> str:
    return " ".join(str(value or "").split())


def number(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def parse_beats(value: str, default: float) -> float:
    try:
        return sum(float(part.strip()) for part in value.split("+") if part.strip())
    except ValueError:
        return default


def format_number(value: float) -> str:
    return f"{value:g}"
