from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Transition(str, Enum):
    LINEAR = "linear"
    EASE_IN_OUT = "ease_in_out"
    CURVED = "curved"


class MovementStyle(str, Enum):
    NORMAL = "normal"
    HALF_TIME = "half_time"
    DOUBLE_TIME = "double_time"
    JAZZ_RUN = "jazz_run"
    HALT = "halt"
    VISUAL = "visual"


@dataclass(slots=True)
class Dot:
    id: str
    name: str
    x: float
    y: float
    color: str = "#e53935"
    section: str = ""
    instrument: str = ""
    rank: str = ""
    equipment: str = ""
    layer: str = "Main"

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "color": self.color,
            "section": self.section,
            "instrument": self.instrument,
            "rank": self.rank,
            "equipment": self.equipment,
            "layer": self.layer,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "Dot":
        return cls(
            id=str(payload["id"]),
            name=str(payload.get("name", payload["id"])),
            x=float(payload.get("x", 0)),
            y=float(payload.get("y", 0)),
            color=str(payload.get("color", "#e53935")),
            section=str(payload.get("section", "")),
            instrument=str(payload.get("instrument", "")),
            rank=str(payload.get("rank", "")),
            equipment=str(payload.get("equipment", "")),
            layer=str(payload.get("layer", "Main")),
        )


@dataclass(slots=True)
class Prop:
    id: str
    name: str
    image_file: str
    x: float = 0.0
    y: float = 0.0
    width: float = 8.0
    height: float = 4.0
    rotation: float = 0.0
    layer: str = "Props"

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "image_file": self.image_file,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "rotation": self.rotation,
            "layer": self.layer,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "Prop":
        return cls(
            id=str(payload["id"]),
            name=str(payload.get("name", payload["id"])),
            image_file=str(payload.get("image_file", "")),
            x=float(payload.get("x", 0)),
            y=float(payload.get("y", 0)),
            width=float(payload.get("width", 8)),
            height=float(payload.get("height", 4)),
            rotation=float(payload.get("rotation", 0)),
            layer=str(payload.get("layer", "Props")),
        )


@dataclass(slots=True)
class ContinuityInstruction:
    id: str
    dot_ids: list[str]
    start_count: float
    end_count: float
    step_size: str = "8-to-5"
    direction: str = "forward"
    body_facing: float | None = None
    horn_facing: float | None = None
    text: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "dot_ids": list(self.dot_ids),
            "start_count": float(self.start_count),
            "end_count": float(self.end_count),
            "step_size": self.step_size,
            "direction": self.direction,
            "body_facing": self.body_facing,
            "horn_facing": self.horn_facing,
            "text": self.text,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ContinuityInstruction":
        return cls(
            id=str(payload.get("id", "continuity")),
            dot_ids=[str(dot_id) for dot_id in payload.get("dot_ids", [])],
            start_count=float(payload.get("start_count", 1)),
            end_count=float(payload.get("end_count", payload.get("start_count", 1))),
            step_size=str(payload.get("step_size", "8-to-5")),
            direction=str(payload.get("direction", "forward")),
            body_facing=(
                float(payload["body_facing"])
                if payload.get("body_facing") is not None
                else None
            ),
            horn_facing=(
                float(payload["horn_facing"])
                if payload.get("horn_facing") is not None
                else None
            ),
            text=str(payload.get("text", "")),
        )


@dataclass(slots=True)
class MotionRibbon:
    id: str
    name: str
    dot_ids: list[str]
    nodes: list[dict[str, tuple[float, float]]]
    orient_to_path: bool = True
    face_direction: bool = False
    samples_per_count: int = 4

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "dot_ids": list(self.dot_ids),
            "nodes": [
                {
                    key: {"x": float(point[0]), "y": float(point[1])}
                    for key, point in node.items()
                    if key in {"point", "in", "out"}
                }
                for node in self.nodes
            ],
            "orient_to_path": bool(self.orient_to_path),
            "face_direction": bool(self.face_direction),
            "samples_per_count": int(self.samples_per_count),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "MotionRibbon":
        nodes: list[dict[str, tuple[float, float]]] = []
        for raw_node in payload.get("nodes", []):
            if not isinstance(raw_node, dict):
                continue
            node: dict[str, tuple[float, float]] = {}
            for key in ("point", "in", "out"):
                raw_point = raw_node.get(key)
                if isinstance(raw_point, dict):
                    node[key] = (
                        float(raw_point.get("x", 0)),
                        float(raw_point.get("y", 0)),
                    )
            if "point" in node:
                nodes.append(node)
        return cls(
            id=str(payload.get("id", "ribbon")),
            name=str(payload.get("name", "Motion Ribbon")),
            dot_ids=[str(dot_id) for dot_id in payload.get("dot_ids", [])],
            nodes=nodes,
            orient_to_path=bool(payload.get("orient_to_path", True)),
            face_direction=bool(payload.get("face_direction", False)),
            samples_per_count=max(1, min(16, int(payload.get("samples_per_count", 4)))),
        )


@dataclass(slots=True)
class ConstructionGuide:
    id: str
    name: str
    guide_type: str
    points: list[tuple[float, float]]
    color: str = "#a855f7"
    visible: bool = True
    locked: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "guide_type": self.guide_type,
            "points": [{"x": point[0], "y": point[1]} for point in self.points],
            "color": self.color,
            "visible": self.visible,
            "locked": self.locked,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ConstructionGuide":
        return cls(
            id=str(payload.get("id", "guide")),
            name=str(payload.get("name", "Guide")),
            guide_type=str(payload.get("guide_type", "line")),
            points=[
                (float(point.get("x", 0)), float(point.get("y", 0)))
                for point in payload.get("points", [])
                if isinstance(point, dict)
            ],
            color=str(payload.get("color", "#a855f7")),
            visible=bool(payload.get("visible", True)),
            locked=bool(payload.get("locked", False)),
            metadata=(
                dict(payload.get("metadata", {}))
                if isinstance(payload.get("metadata", {}), dict)
                else {}
            ),
        )


@dataclass(slots=True)
class DrillSet:
    name: str
    start_count: int
    end_count: int
    tempo: float | None = None
    dot_positions: dict[str, tuple[float, float]] = field(default_factory=dict)
    dot_facings: dict[str, float] = field(default_factory=dict)
    prop_positions: dict[str, dict[str, float]] = field(default_factory=dict)
    path_anchors: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    path_controls: dict[str, list[dict[str, tuple[float, float]]]] = field(default_factory=dict)
    count_positions: dict[str, dict[float, tuple[float, float]]] = field(default_factory=dict)
    count_facings: dict[str, dict[float, float]] = field(default_factory=dict)
    move_timings: dict[str, dict[str, float]] = field(default_factory=dict)
    movement_styles: dict[str, MovementStyle] = field(default_factory=dict)
    continuity: list[ContinuityInstruction] = field(default_factory=list)
    motion_ribbons: list[MotionRibbon] = field(default_factory=list)
    transition: Transition = Transition.LINEAR

    @property
    def duration_counts(self) -> int:
        return max(1, self.end_count - self.start_count + 1)

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "start_count": self.start_count,
            "end_count": self.end_count,
            "tempo": self.tempo,
            "dot_positions": {
                dot_id: {"x": position[0], "y": position[1]}
                for dot_id, position in self.dot_positions.items()
            },
            "dot_facings": {
                dot_id: float(facing)
                for dot_id, facing in self.dot_facings.items()
            },
            "prop_positions": {
                prop_id: {
                    "x": state.get("x", 0.0),
                    "y": state.get("y", 0.0),
                    "width": state.get("width", 8.0),
                    "height": state.get("height", 4.0),
                    "rotation": state.get("rotation", 0.0),
                }
                for prop_id, state in self.prop_positions.items()
            },
            "path_anchors": {
                dot_id: [{"x": point[0], "y": point[1]} for point in anchors]
                for dot_id, anchors in self.path_anchors.items()
            },
            "path_controls": {
                dot_id: [
                    {
                        control_name: {"x": point[0], "y": point[1]}
                        for control_name, point in controls.items()
                    }
                    for controls in control_sets
                ]
                for dot_id, control_sets in self.path_controls.items()
                if control_sets
            },
            "count_positions": {
                dot_id: {
                    f"{count:g}": {"x": position[0], "y": position[1]}
                    for count, position in sorted(keyframes.items())
                }
                for dot_id, keyframes in self.count_positions.items()
                if keyframes
            },
            "count_facings": {
                dot_id: {
                    f"{count:g}": float(facing)
                    for count, facing in sorted(keyframes.items())
                }
                for dot_id, keyframes in self.count_facings.items()
                if keyframes
            },
            "move_timings": {
                dot_id: {
                    "start": float(timing.get("start", self.start_count)),
                    "end": float(timing.get("end", self.end_count)),
                }
                for dot_id, timing in self.move_timings.items()
                if timing
            },
            "movement_styles": {
                dot_id: style.value
                for dot_id, style in self.movement_styles.items()
                if style != MovementStyle.NORMAL
            },
            "continuity": [instruction.to_json() for instruction in self.continuity],
            "motion_ribbons": [ribbon.to_json() for ribbon in self.motion_ribbons],
            "transition": self.transition.value,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "DrillSet":
        return cls(
            name=str(payload.get("name", "Set")),
            start_count=int(payload.get("start_count", 1)),
            end_count=int(payload.get("end_count", 16)),
            tempo=float(payload["tempo"]) if payload.get("tempo") is not None else None,
            dot_positions={
                str(dot_id): (float(pos.get("x", 0)), float(pos.get("y", 0)))
                for dot_id, pos in payload.get("dot_positions", {}).items()
            },
            dot_facings={
                str(dot_id): float(facing)
                for dot_id, facing in payload.get("dot_facings", {}).items()
            },
            prop_positions={
                str(prop_id): {
                    "x": float(state.get("x", 0)),
                    "y": float(state.get("y", 0)),
                    "width": float(state.get("width", 8)),
                    "height": float(state.get("height", 4)),
                    "rotation": float(state.get("rotation", 0)),
                }
                for prop_id, state in payload.get("prop_positions", {}).items()
                if isinstance(state, dict)
            },
            path_anchors={
                str(dot_id): [
                    (float(point.get("x", 0)), float(point.get("y", 0)))
                    for point in anchors
                ]
                for dot_id, anchors in payload.get("path_anchors", {}).items()
            },
            path_controls={
                str(dot_id): [
                    {
                        control_name: (
                            float(point.get("x", 0)),
                            float(point.get("y", 0)),
                        )
                        for control_name, point in controls.items()
                        if isinstance(point, dict)
                    }
                    for controls in control_sets
                    if isinstance(controls, dict)
                ]
                for dot_id, control_sets in payload.get("path_controls", {}).items()
            },
            count_positions={
                str(dot_id): {
                    float(count): (float(pos.get("x", 0)), float(pos.get("y", 0)))
                    for count, pos in keyframes.items()
                }
                for dot_id, keyframes in payload.get("count_positions", {}).items()
            },
            count_facings={
                str(dot_id): {
                    float(count): float(facing)
                    for count, facing in keyframes.items()
                }
                for dot_id, keyframes in payload.get("count_facings", {}).items()
                if isinstance(keyframes, dict)
            },
            move_timings={
                str(dot_id): {
                    "start": float(timing.get("start", payload.get("start_count", 1))),
                    "end": float(timing.get("end", payload.get("end_count", 16))),
                }
                for dot_id, timing in payload.get("move_timings", {}).items()
                if isinstance(timing, dict)
            },
            movement_styles={
                str(dot_id): MovementStyle(str(style))
                for dot_id, style in payload.get("movement_styles", {}).items()
                if str(style) in MovementStyle._value2member_map_
            },
            continuity=[
                ContinuityInstruction.from_json(item)
                for item in payload.get("continuity", [])
                if isinstance(item, dict)
            ],
            motion_ribbons=[
                MotionRibbon.from_json(item)
                for item in payload.get("motion_ribbons", [])
                if isinstance(item, dict)
            ],
            transition=Transition(payload.get("transition", Transition.LINEAR.value)),
        )


@dataclass(slots=True)
class ProjectMetadata:
    show_title: str
    initial_tempo: float
    default_counts_per_set: int
    time_signature: str
    audio_file: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "show_title": self.show_title,
            "initial_tempo": self.initial_tempo,
            "default_counts_per_set": self.default_counts_per_set,
            "time_signature": self.time_signature,
            "audio_file": self.audio_file,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ProjectMetadata":
        return cls(
            show_title=str(payload.get("show_title", "Untitled Show")),
            initial_tempo=float(payload.get("initial_tempo", 160)),
            default_counts_per_set=int(payload.get("default_counts_per_set", 16)),
            time_signature=str(payload.get("time_signature", "4/4")),
            audio_file=str(payload.get("audio_file", "")),
        )


@dataclass(slots=True)
class Marker:
    count: float
    label: str

    def to_json(self) -> dict[str, Any]:
        return {"count": self.count, "label": self.label}

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "Marker":
        return cls(count=float(payload.get("count", 1)), label=str(payload.get("label", "Hit")))


@dataclass(slots=True)
class ScoreTempoChange:
    count: float
    tempo: float
    label: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"count": self.count, "tempo": self.tempo, "label": self.label}

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ScoreTempoChange":
        return cls(
            count=float(payload.get("count", 1)),
            tempo=float(payload.get("tempo", 0)),
            label=str(payload.get("label", "")),
        )


@dataclass(slots=True)
class ScoreMeasure:
    number: str
    start_count: float
    duration_counts: float
    time_signature: str = "4/4"
    tempo: float = 0.0
    rehearsal_mark: str = ""
    phrase_boundary: bool = False

    @property
    def end_count(self) -> float:
        return self.start_count + max(0.0, self.duration_counts) - 1.0

    def to_json(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "start_count": self.start_count,
            "duration_counts": self.duration_counts,
            "time_signature": self.time_signature,
            "tempo": self.tempo,
            "rehearsal_mark": self.rehearsal_mark,
            "phrase_boundary": self.phrase_boundary,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ScoreMeasure":
        return cls(
            number=str(payload.get("number", "1")),
            start_count=float(payload.get("start_count", 1)),
            duration_counts=max(0.001, float(payload.get("duration_counts", 4))),
            time_signature=str(payload.get("time_signature", "4/4")),
            tempo=float(payload.get("tempo", 0)),
            rehearsal_mark=str(payload.get("rehearsal_mark", "")),
            phrase_boundary=bool(payload.get("phrase_boundary", False)),
        )


@dataclass(slots=True)
class ImportedScore:
    title: str = "Imported Score"
    composer: str = ""
    source_file: str = ""
    source_format: str = "musicxml"
    measures: list[ScoreMeasure] = field(default_factory=list)
    tempo_changes: list[ScoreTempoChange] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_counts(self) -> float:
        if not self.measures:
            return 0.0
        last = self.measures[-1]
        return last.start_count + last.duration_counts - 1.0

    def to_json(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "composer": self.composer,
            "source_file": self.source_file,
            "source_format": self.source_format,
            "measures": [measure.to_json() for measure in self.measures],
            "tempo_changes": [change.to_json() for change in self.tempo_changes],
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ImportedScore":
        return cls(
            title=str(payload.get("title", "Imported Score")),
            composer=str(payload.get("composer", "")),
            source_file=str(payload.get("source_file", "")),
            source_format=str(payload.get("source_format", "musicxml")),
            measures=[ScoreMeasure.from_json(item) for item in payload.get("measures", []) if isinstance(item, dict)],
            tempo_changes=[
                ScoreTempoChange.from_json(item)
                for item in payload.get("tempo_changes", [])
                if isinstance(item, dict)
            ],
            warnings=[str(item) for item in payload.get("warnings", [])],
        )


@dataclass(slots=True)
class MusicPhrase:
    id: str
    name: str
    start_count: float
    end_count: float
    start_measure: str = ""
    end_measure: str = ""
    rehearsal_mark: str = ""
    intensity: float = 0.5
    notes: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "start_count": self.start_count,
            "end_count": self.end_count,
            "start_measure": self.start_measure,
            "end_measure": self.end_measure,
            "rehearsal_mark": self.rehearsal_mark,
            "intensity": self.intensity,
            "notes": self.notes,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "MusicPhrase":
        start = float(payload.get("start_count", 1))
        return cls(
            id=str(payload.get("id", "phrase")),
            name=str(payload.get("name", "Phrase")),
            start_count=start,
            end_count=max(start, float(payload.get("end_count", start))),
            start_measure=str(payload.get("start_measure", "")),
            end_measure=str(payload.get("end_measure", "")),
            rehearsal_mark=str(payload.get("rehearsal_mark", "")),
            intensity=max(0.0, min(1.0, float(payload.get("intensity", 0.5)))),
            notes=str(payload.get("notes", "")),
        )


@dataclass(slots=True)
class StoryboardScene:
    id: str
    name: str
    start_count: float
    end_count: float
    movement: str = ""
    visual_pacing: str = "Moderate"
    production_notes: str = ""
    color: str = "#7c3aed"

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "start_count": self.start_count,
            "end_count": self.end_count,
            "movement": self.movement,
            "visual_pacing": self.visual_pacing,
            "production_notes": self.production_notes,
            "color": self.color,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "StoryboardScene":
        start = float(payload.get("start_count", 1))
        return cls(
            id=str(payload.get("id", "scene")),
            name=str(payload.get("name", "Scene")),
            start_count=start,
            end_count=max(start, float(payload.get("end_count", start))),
            movement=str(payload.get("movement", "")),
            visual_pacing=str(payload.get("visual_pacing", "Moderate")),
            production_notes=str(payload.get("production_notes", "")),
            color=str(payload.get("color", "#7c3aed")),
        )


@dataclass(slots=True)
class DotConstraint:
    name: str
    constraint_type: str
    dot_ids: list[str]
    spacing: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "constraint_type": self.constraint_type,
            "dot_ids": list(self.dot_ids),
            "spacing": self.spacing,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "DotConstraint":
        return cls(
            name=str(payload.get("name", "Constraint")),
            constraint_type=str(payload.get("constraint_type", "line")),
            dot_ids=[str(dot_id) for dot_id in payload.get("dot_ids", [])],
            spacing=float(payload.get("spacing", 0)),
            metadata=dict(payload.get("metadata", {})) if isinstance(payload.get("metadata", {}), dict) else {},
        )


@dataclass(slots=True)
class AudioVersion:
    name: str
    audio_file: str
    active: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "audio_file": self.audio_file,
            "active": self.active,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "AudioVersion":
        return cls(
            name=str(payload.get("name", "Audio")),
            audio_file=str(payload.get("audio_file", "")),
            active=bool(payload.get("active", False)),
        )


@dataclass(slots=True)
class TimingEvent:
    event_type: str
    count: float
    milliseconds: float = 0.0
    tempo: float = 0.0
    end_count: float = 0.0
    end_tempo: float = 0.0
    label: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "count": self.count,
            "milliseconds": self.milliseconds,
            "tempo": self.tempo,
            "end_count": self.end_count,
            "end_tempo": self.end_tempo,
            "label": self.label,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "TimingEvent":
        return cls(
            event_type=str(payload.get("event_type", "anchor")),
            count=float(payload.get("count", 1)),
            milliseconds=float(payload.get("milliseconds", 0)),
            tempo=float(payload.get("tempo", 0)),
            end_count=float(payload.get("end_count", 0)),
            end_tempo=float(payload.get("end_tempo", 0)),
            label=str(payload.get("label", "")),
        )


@dataclass(slots=True)
class SurfaceDefinition:
    name: str = "College Football Field"
    surface_type: str = "football"
    width_yards: float = 120.0
    height_yards: float = 53.333
    hash_style: str = "college"
    front_hash_yards: float = -6.6665
    back_hash_yards: float = 6.6665
    endzone_depth_yards: float = 10.0
    grid_spacing_yards: float = 1.0
    route_points: list[tuple[float, float]] = field(default_factory=list)
    route_width_yards: float = 8.0
    background_color: str = ""
    line_color: str = ""
    show_yard_numbers: bool = True
    show_end_zones: bool = True

    @property
    def half_width(self) -> float:
        return max(1.0, float(self.width_yards) / 2.0)

    @property
    def half_height(self) -> float:
        return max(1.0, float(self.height_yards) / 2.0)

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "surface_type": self.surface_type,
            "width_yards": float(self.width_yards),
            "height_yards": float(self.height_yards),
            "hash_style": self.hash_style,
            "front_hash_yards": float(self.front_hash_yards),
            "back_hash_yards": float(self.back_hash_yards),
            "endzone_depth_yards": float(self.endzone_depth_yards),
            "grid_spacing_yards": float(self.grid_spacing_yards),
            "route_points": [{"x": point[0], "y": point[1]} for point in self.route_points],
            "route_width_yards": float(self.route_width_yards),
            "background_color": self.background_color,
            "line_color": self.line_color,
            "show_yard_numbers": bool(self.show_yard_numbers),
            "show_end_zones": bool(self.show_end_zones),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "SurfaceDefinition":
        return cls(
            name=str(payload.get("name", "College Football Field")),
            surface_type=str(payload.get("surface_type", "football")),
            width_yards=max(2.0, float(payload.get("width_yards", 120))),
            height_yards=max(2.0, float(payload.get("height_yards", 53.333))),
            hash_style=str(payload.get("hash_style", "college")),
            front_hash_yards=float(payload.get("front_hash_yards", -6.6665)),
            back_hash_yards=float(payload.get("back_hash_yards", 6.6665)),
            endzone_depth_yards=max(0.0, float(payload.get("endzone_depth_yards", 10))),
            grid_spacing_yards=max(0.25, float(payload.get("grid_spacing_yards", 1))),
            route_points=[
                (float(point.get("x", 0)), float(point.get("y", 0)))
                for point in payload.get("route_points", [])
                if isinstance(point, dict)
            ],
            route_width_yards=max(0.5, float(payload.get("route_width_yards", 8))),
            background_color=str(payload.get("background_color", "")),
            line_color=str(payload.get("line_color", "")),
            show_yard_numbers=bool(payload.get("show_yard_numbers", True)),
            show_end_zones=bool(payload.get("show_end_zones", True)),
        )


@dataclass(slots=True)
class ChoreographyEvent:
    id: str
    name: str
    event_type: str
    dot_ids: list[str]
    start_count: float
    end_count: float
    equipment_from: str = ""
    equipment_to: str = ""
    revolutions: float = 0.0
    height_yards: float = 0.0
    notes: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "event_type": self.event_type,
            "dot_ids": list(self.dot_ids),
            "start_count": float(self.start_count),
            "end_count": float(self.end_count),
            "equipment_from": self.equipment_from,
            "equipment_to": self.equipment_to,
            "revolutions": float(self.revolutions),
            "height_yards": float(self.height_yards),
            "notes": self.notes,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ChoreographyEvent":
        start = float(payload.get("start_count", 1))
        return cls(
            id=str(payload.get("id", "choreography")),
            name=str(payload.get("name", "Choreography")),
            event_type=str(payload.get("event_type", "choreography")),
            dot_ids=[str(dot_id) for dot_id in payload.get("dot_ids", [])],
            start_count=start,
            end_count=max(start, float(payload.get("end_count", start))),
            equipment_from=str(payload.get("equipment_from", "")),
            equipment_to=str(payload.get("equipment_to", "")),
            revolutions=max(0.0, float(payload.get("revolutions", 0))),
            height_yards=max(0.0, float(payload.get("height_yards", 0))),
            notes=str(payload.get("notes", "")),
        )


@dataclass(slots=True)
class PropAttachment:
    id: str
    name: str
    prop_id: str
    dot_ids: list[str]
    start_count: float
    end_count: float
    mode: str = "carry"
    leader_dot_id: str = ""
    offset_x: float = 0.0
    offset_y: float = 0.0
    rotation_behavior: str = "fixed"
    rotation_offset: float = 0.0
    rotation_rate: float = 0.0
    enabled: bool = True

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "prop_id": self.prop_id,
            "dot_ids": list(self.dot_ids),
            "start_count": float(self.start_count),
            "end_count": float(self.end_count),
            "mode": self.mode,
            "leader_dot_id": self.leader_dot_id,
            "offset_x": float(self.offset_x),
            "offset_y": float(self.offset_y),
            "rotation_behavior": self.rotation_behavior,
            "rotation_offset": float(self.rotation_offset),
            "rotation_rate": float(self.rotation_rate),
            "enabled": bool(self.enabled),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "PropAttachment":
        start = float(payload.get("start_count", 1))
        return cls(
            id=str(payload.get("id", "prop_attachment")),
            name=str(payload.get("name", "Prop Attachment")),
            prop_id=str(payload.get("prop_id", "")),
            dot_ids=[str(dot_id) for dot_id in payload.get("dot_ids", [])],
            start_count=start,
            end_count=max(start, float(payload.get("end_count", start))),
            mode=str(payload.get("mode", "carry")),
            leader_dot_id=str(payload.get("leader_dot_id", "")),
            offset_x=float(payload.get("offset_x", 0)),
            offset_y=float(payload.get("offset_y", 0)),
            rotation_behavior=str(payload.get("rotation_behavior", "fixed")),
            rotation_offset=float(payload.get("rotation_offset", 0)),
            rotation_rate=float(payload.get("rotation_rate", 0)),
            enabled=bool(payload.get("enabled", True)),
        )


@dataclass(slots=True)
class PerformerPhysicalLimits:
    dot_id: str
    max_yards_per_count: float | None = None
    max_backward_yards_per_count: float | None = None
    max_lateral_yards_per_count: float | None = None
    max_rotation_degrees_per_count: float | None = None
    max_toss_revolutions: float | None = None
    minimum_recovery_counts: float | None = None
    carry_speed_multiplier: float | None = None
    notes: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "dot_id": self.dot_id,
            "max_yards_per_count": self.max_yards_per_count,
            "max_backward_yards_per_count": self.max_backward_yards_per_count,
            "max_lateral_yards_per_count": self.max_lateral_yards_per_count,
            "max_rotation_degrees_per_count": self.max_rotation_degrees_per_count,
            "max_toss_revolutions": self.max_toss_revolutions,
            "minimum_recovery_counts": self.minimum_recovery_counts,
            "carry_speed_multiplier": self.carry_speed_multiplier,
            "notes": self.notes,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "PerformerPhysicalLimits":
        def optional_float(key: str) -> float | None:
            value = payload.get(key)
            return float(value) if value is not None else None

        return cls(
            dot_id=str(payload.get("dot_id", "")),
            max_yards_per_count=optional_float("max_yards_per_count"),
            max_backward_yards_per_count=optional_float("max_backward_yards_per_count"),
            max_lateral_yards_per_count=optional_float("max_lateral_yards_per_count"),
            max_rotation_degrees_per_count=optional_float("max_rotation_degrees_per_count"),
            max_toss_revolutions=optional_float("max_toss_revolutions"),
            minimum_recovery_counts=optional_float("minimum_recovery_counts"),
            carry_speed_multiplier=optional_float("carry_speed_multiplier"),
            notes=str(payload.get("notes", "")),
        )


@dataclass(slots=True)
class DrillProject:
    metadata: ProjectMetadata
    dots: list[Dot] = field(default_factory=list)
    props: list[Prop] = field(default_factory=list)
    sets: list[DrillSet] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)
    constraints: list[DotConstraint] = field(default_factory=list)
    audio_versions: list[AudioVersion] = field(default_factory=list)
    timing_events: list[TimingEvent] = field(default_factory=list)
    guides: list[ConstructionGuide] = field(default_factory=list)
    workflow: dict[str, Any] = field(default_factory=dict)
    imported_score: ImportedScore | None = None
    music_phrases: list[MusicPhrase] = field(default_factory=list)
    storyboard: list[StoryboardScene] = field(default_factory=list)
    surface: SurfaceDefinition = field(default_factory=SurfaceDefinition)
    choreography: list[ChoreographyEvent] = field(default_factory=list)
    prop_attachments: list[PropAttachment] = field(default_factory=list)
    physical_limits: list[PerformerPhysicalLimits] = field(default_factory=list)

    def dot_by_id(self, dot_id: str) -> Dot | None:
        return next((dot for dot in self.dots if dot.id == dot_id), None)

    def prop_by_id(self, prop_id: str) -> Prop | None:
        return next((prop for prop in self.props if prop.id == prop_id), None)

    def active_tempo(self, set_index: int) -> float:
        if 0 <= set_index < len(self.sets) and self.sets[set_index].tempo:
            return float(self.sets[set_index].tempo)
        count = self.sets[set_index].start_count if 0 <= set_index < len(self.sets) else 1
        tempo = self.metadata.initial_tempo
        for event in sorted(self.timing_events, key=lambda item: item.count):
            if event.event_type == "tempo" and event.count <= count and event.tempo > 0:
                tempo = event.tempo
        return tempo

    def ensure_set_positions(self) -> None:
        valid_dot_ids = {dot.id for dot in self.dots}
        valid_prop_ids = {prop.id for prop in self.props}
        for drill_set in self.sets:
            for dot in self.dots:
                drill_set.dot_positions.setdefault(dot.id, (dot.x, dot.y))
            for prop in self.props:
                drill_set.prop_positions.setdefault(prop.id, prop_default_state(prop))
            for dot_id in list(drill_set.dot_positions):
                if dot_id not in valid_dot_ids:
                    drill_set.dot_positions.pop(dot_id, None)
                    drill_set.dot_facings.pop(dot_id, None)
                    drill_set.path_anchors.pop(dot_id, None)
                    drill_set.path_controls.pop(dot_id, None)
                    drill_set.count_positions.pop(dot_id, None)
                    drill_set.count_facings.pop(dot_id, None)
            for dot_id in list(drill_set.dot_facings):
                if dot_id not in valid_dot_ids:
                    drill_set.dot_facings.pop(dot_id, None)
                else:
                    drill_set.dot_facings[dot_id] = float(drill_set.dot_facings[dot_id]) % 360.0
            for dot_id in list(drill_set.count_positions):
                if dot_id not in valid_dot_ids:
                    drill_set.count_positions.pop(dot_id, None)
            for dot_id in list(drill_set.count_facings):
                if dot_id not in valid_dot_ids:
                    drill_set.count_facings.pop(dot_id, None)
                    continue
                drill_set.count_facings[dot_id] = {
                    float(count): float(facing) % 360.0
                    for count, facing in drill_set.count_facings[dot_id].items()
                    if float(drill_set.start_count) <= float(count) <= float(drill_set.end_count)
                }
                if not drill_set.count_facings[dot_id]:
                    drill_set.count_facings.pop(dot_id, None)
            for dot_id in list(drill_set.move_timings):
                if dot_id not in valid_dot_ids:
                    drill_set.move_timings.pop(dot_id, None)
                    continue
                timing = drill_set.move_timings[dot_id]
                start = max(float(drill_set.start_count), min(float(timing.get("start", drill_set.start_count)), float(drill_set.end_count)))
                end = max(start, min(float(timing.get("end", drill_set.end_count)), float(drill_set.end_count)))
                if abs(start - float(drill_set.start_count)) < 0.0001 and abs(end - float(drill_set.end_count)) < 0.0001:
                    drill_set.move_timings.pop(dot_id, None)
                else:
                    drill_set.move_timings[dot_id] = {"start": start, "end": end}
            for dot_id in list(drill_set.path_controls):
                if dot_id not in valid_dot_ids:
                    drill_set.path_controls.pop(dot_id, None)
            for dot_id in list(drill_set.movement_styles):
                if dot_id not in valid_dot_ids or drill_set.movement_styles[dot_id] == MovementStyle.NORMAL:
                    drill_set.movement_styles.pop(dot_id, None)
            for dot_id, anchors in list(drill_set.path_anchors.items()):
                controls = drill_set.path_controls.get(dot_id, [])
                if len(controls) > len(anchors):
                    drill_set.path_controls[dot_id] = controls[: len(anchors)]
            for instruction in drill_set.continuity:
                instruction.dot_ids = [dot_id for dot_id in instruction.dot_ids if dot_id in valid_dot_ids]
                instruction.start_count = max(
                    float(drill_set.start_count),
                    min(float(instruction.start_count), float(drill_set.end_count)),
                )
                instruction.end_count = max(
                    instruction.start_count,
                    min(float(instruction.end_count), float(drill_set.end_count)),
                )
                if instruction.body_facing is not None:
                    instruction.body_facing %= 360.0
                if instruction.horn_facing is not None:
                    instruction.horn_facing %= 360.0
            drill_set.continuity = [item for item in drill_set.continuity if item.dot_ids]
            for ribbon in drill_set.motion_ribbons:
                ribbon.dot_ids = [dot_id for dot_id in ribbon.dot_ids if dot_id in valid_dot_ids]
                ribbon.samples_per_count = max(1, min(16, int(ribbon.samples_per_count)))
            drill_set.motion_ribbons = [
                ribbon
                for ribbon in drill_set.motion_ribbons
                if len(ribbon.dot_ids) >= 2 and len(ribbon.nodes) >= 2
            ]
            for prop_id in list(drill_set.prop_positions):
                if prop_id not in valid_prop_ids:
                    drill_set.prop_positions.pop(prop_id, None)
        for constraint in self.constraints:
            constraint.dot_ids = [dot_id for dot_id in constraint.dot_ids if dot_id in valid_dot_ids]
        self.constraints = [constraint for constraint in self.constraints if constraint.dot_ids]
        for event in self.choreography:
            event.dot_ids = [dot_id for dot_id in event.dot_ids if dot_id in valid_dot_ids]
            event.end_count = max(event.start_count, event.end_count)
        self.choreography = [event for event in self.choreography if event.dot_ids]
        for attachment in self.prop_attachments:
            attachment.dot_ids = [dot_id for dot_id in attachment.dot_ids if dot_id in valid_dot_ids]
            if attachment.leader_dot_id not in attachment.dot_ids:
                attachment.leader_dot_id = attachment.dot_ids[0] if attachment.dot_ids else ""
            attachment.end_count = max(attachment.start_count, attachment.end_count)
        self.prop_attachments = [
            attachment
            for attachment in self.prop_attachments
            if attachment.prop_id in valid_prop_ids and attachment.dot_ids
        ]
        self.physical_limits = [
            limits for limits in self.physical_limits if limits.dot_id in valid_dot_ids
        ]


def prop_default_state(prop: Prop) -> dict[str, float]:
    return {
        "x": prop.x,
        "y": prop.y,
        "width": prop.width,
        "height": prop.height,
        "rotation": prop.rotation,
    }
