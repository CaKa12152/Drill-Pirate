from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Transition(str, Enum):
    LINEAR = "linear"
    EASE_IN_OUT = "ease_in_out"
    CURVED = "curved"


@dataclass(slots=True)
class Dot:
    id: str
    name: str
    x: float
    y: float
    color: str = "#e53935"
    section: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "color": self.color,
            "section": self.section,
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
        )


@dataclass(slots=True)
class DrillSet:
    name: str
    start_count: int
    end_count: int
    tempo: float | None = None
    dot_positions: dict[str, tuple[float, float]] = field(default_factory=dict)
    path_anchors: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
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
            "path_anchors": {
                dot_id: [{"x": point[0], "y": point[1]} for point in anchors]
                for dot_id, anchors in self.path_anchors.items()
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
            path_anchors={
                str(dot_id): [
                    (float(point.get("x", 0)), float(point.get("y", 0)))
                    for point in anchors
                ]
                for dot_id, anchors in payload.get("path_anchors", {}).items()
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
class DrillProject:
    metadata: ProjectMetadata
    dots: list[Dot] = field(default_factory=list)
    sets: list[DrillSet] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)

    def dot_by_id(self, dot_id: str) -> Dot | None:
        return next((dot for dot in self.dots if dot.id == dot_id), None)

    def active_tempo(self, set_index: int) -> float:
        if 0 <= set_index < len(self.sets) and self.sets[set_index].tempo:
            return float(self.sets[set_index].tempo)
        return self.metadata.initial_tempo

    def ensure_set_positions(self) -> None:
        for drill_set in self.sets:
            for dot in self.dots:
                drill_set.dot_positions.setdefault(dot.id, (dot.x, dot.y))
            valid_dot_ids = {dot.id for dot in self.dots}
            for dot_id in list(drill_set.dot_positions):
                if dot_id not in valid_dot_ids:
                    drill_set.dot_positions.pop(dot_id, None)
                    drill_set.path_anchors.pop(dot_id, None)
