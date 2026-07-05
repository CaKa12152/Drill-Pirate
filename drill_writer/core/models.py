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
class DrillSet:
    name: str
    start_count: int
    end_count: int
    tempo: float | None = None
    dot_positions: dict[str, tuple[float, float]] = field(default_factory=dict)
    prop_positions: dict[str, dict[str, float]] = field(default_factory=dict)
    path_anchors: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    path_controls: dict[str, list[dict[str, tuple[float, float]]]] = field(default_factory=dict)
    count_positions: dict[str, dict[float, tuple[float, float]]] = field(default_factory=dict)
    movement_styles: dict[str, MovementStyle] = field(default_factory=dict)
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
            "movement_styles": {
                dot_id: style.value
                for dot_id, style in self.movement_styles.items()
                if style != MovementStyle.NORMAL
            },
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
            movement_styles={
                str(dot_id): MovementStyle(str(style))
                for dot_id, style in payload.get("movement_styles", {}).items()
                if str(style) in MovementStyle._value2member_map_
            },
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
class DotConstraint:
    name: str
    constraint_type: str
    dot_ids: list[str]
    spacing: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "constraint_type": self.constraint_type,
            "dot_ids": list(self.dot_ids),
            "spacing": self.spacing,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "DotConstraint":
        return cls(
            name=str(payload.get("name", "Constraint")),
            constraint_type=str(payload.get("constraint_type", "line")),
            dot_ids=[str(dot_id) for dot_id in payload.get("dot_ids", [])],
            spacing=float(payload.get("spacing", 0)),
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
class DrillProject:
    metadata: ProjectMetadata
    dots: list[Dot] = field(default_factory=list)
    props: list[Prop] = field(default_factory=list)
    sets: list[DrillSet] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)
    constraints: list[DotConstraint] = field(default_factory=list)
    audio_versions: list[AudioVersion] = field(default_factory=list)
    timing_events: list[TimingEvent] = field(default_factory=list)

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
                    drill_set.path_anchors.pop(dot_id, None)
                    drill_set.path_controls.pop(dot_id, None)
                    drill_set.count_positions.pop(dot_id, None)
            for dot_id in list(drill_set.count_positions):
                if dot_id not in valid_dot_ids:
                    drill_set.count_positions.pop(dot_id, None)
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
            for prop_id in list(drill_set.prop_positions):
                if prop_id not in valid_prop_ids:
                    drill_set.prop_positions.pop(prop_id, None)
        for constraint in self.constraints:
            constraint.dot_ids = [dot_id for dot_id in constraint.dot_ids if dot_id in valid_dot_ids]
        self.constraints = [constraint for constraint in self.constraints if constraint.dot_ids]


def prop_default_state(prop: Prop) -> dict[str, float]:
    return {
        "x": prop.x,
        "y": prop.y,
        "width": prop.width,
        "height": prop.height,
        "rotation": prop.rotation,
    }
