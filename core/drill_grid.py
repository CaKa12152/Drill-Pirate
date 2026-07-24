from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor, sqrt
from typing import Any, Iterable, Mapping


MIN_STEPS_PER_FIVE = 1.0
MAX_STEPS_PER_FIVE = 32.0


def _clamp_steps(value: Any, default: float = 8.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(MIN_STEPS_PER_FIVE, min(MAX_STEPS_PER_FIVE, number))


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class DrillGridSettings:
    enabled: bool = False
    steps_per_five_x: float = 8.0
    steps_per_five_y: float = 8.0
    origin_x: float = 0.0
    origin_y: float = 0.0
    show_overlay: bool = True
    display_style: str = "points"

    def __post_init__(self) -> None:
        self.enabled = bool(self.enabled)
        self.steps_per_five_x = _clamp_steps(self.steps_per_five_x)
        self.steps_per_five_y = _clamp_steps(self.steps_per_five_y)
        self.origin_x = float(self.origin_x)
        self.origin_y = float(self.origin_y)
        self.show_overlay = bool(self.show_overlay)
        self.display_style = self.display_style if self.display_style in {"points", "lines"} else "points"

    @property
    def spacing_x(self) -> float:
        return 5.0 / self.steps_per_five_x

    @property
    def spacing_y(self) -> float:
        return 5.0 / self.steps_per_five_y

    @property
    def preset_label(self) -> str:
        if abs(self.steps_per_five_x - self.steps_per_five_y) < 1e-9:
            steps = f"{self.steps_per_five_x:g}"
            return f"{steps}:5"
        return f"{self.steps_per_five_x:g}x / {self.steps_per_five_y:g}y"

    @property
    def description(self) -> str:
        if abs(self.spacing_x - self.spacing_y) < 1e-9:
            return f"{self.preset_label}  •  {self.spacing_x:.3f} yd per step"
        return (
            f"{self.preset_label}  •  X {self.spacing_x:.3f} yd  •  "
            f"Y {self.spacing_y:.3f} yd"
        )

    def snap_point(
        self,
        point: tuple[float, float],
        *,
        reference_y: Iterable[float] = (),
    ) -> tuple[float, float]:
        index_x = round((point[0] - self.origin_x) / self.spacing_x)
        index_y = round((point[1] - self.origin_y) / self.spacing_y)
        snapped = (
            self.origin_x + index_x * self.spacing_x,
            self.origin_y + index_y * self.spacing_y,
        )
        references = tuple(float(value) for value in reference_y)
        if not references:
            return snapped
        nearest_reference = min(references, key=lambda value: abs(point[1] - value))
        if abs(point[1] - nearest_reference) <= abs(point[1] - snapped[1]) + 1e-9:
            return snapped[0], nearest_reference
        return snapped

    def to_json(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "steps_per_five_x": self.steps_per_five_x,
            "steps_per_five_y": self.steps_per_five_y,
            "origin_x": self.origin_x,
            "origin_y": self.origin_y,
            "show_overlay": self.show_overlay,
            "display_style": self.display_style,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any] | None) -> "DrillGridSettings":
        data = payload if isinstance(payload, Mapping) else {}
        return cls(
            enabled=bool(data.get("enabled", False)),
            steps_per_five_x=_clamp_steps(data.get("steps_per_five_x", 8.0)),
            steps_per_five_y=_clamp_steps(data.get("steps_per_five_y", 8.0)),
            origin_x=_number(data.get("origin_x", 0.0)),
            origin_y=_number(data.get("origin_y", 0.0)),
            show_overlay=bool(data.get("show_overlay", True)),
            display_style=str(data.get("display_style", "points")),
        )


def grid_axis_values(
    minimum: float,
    maximum: float,
    origin: float,
    spacing: float,
) -> list[float]:
    if spacing <= 0 or maximum < minimum:
        return []
    first = ceil((minimum - origin) / spacing - 1e-9)
    last = floor((maximum - origin) / spacing + 1e-9)
    return [origin + index * spacing for index in range(first, last + 1)]


def _nearest_grid_index(
    point: tuple[float, float],
    settings: DrillGridSettings,
) -> tuple[int, int]:
    return (
        round((point[0] - settings.origin_x) / settings.spacing_x),
        round((point[1] - settings.origin_y) / settings.spacing_y),
    )


def _grid_point(index: tuple[int, int], settings: DrillGridSettings) -> tuple[float, float]:
    return (
        settings.origin_x + index[0] * settings.spacing_x,
        settings.origin_y + index[1] * settings.spacing_y,
    )


def snap_positions_to_grid(
    positions: Iterable[tuple[float, float]],
    settings: DrillGridSettings,
    *,
    unique: bool = True,
    reference_y: Iterable[float] = (),
) -> list[tuple[float, float]]:
    points = [(float(x), float(y)) for x, y in positions]
    if not points:
        return []
    references = tuple(float(value) for value in reference_y)
    if references:
        return _snap_positions_with_reference_rows(points, settings, references, unique=unique)
    if not unique:
        return [settings.snap_point(point) for point in points]

    groups: dict[tuple[int, int], list[int]] = {}
    for point_index, point in enumerate(points):
        groups.setdefault(_nearest_grid_index(point, settings), []).append(point_index)

    snapped: list[tuple[float, float] | None] = [None] * len(points)
    used: set[tuple[int, int]] = set()
    pending: list[int] = []
    for grid_index, point_indices in groups.items():
        grid_point = _grid_point(grid_index, settings)
        point_indices.sort(
            key=lambda index: (
                (points[index][0] - grid_point[0]) ** 2 + (points[index][1] - grid_point[1]) ** 2,
                index,
            )
        )
        keeper = point_indices[0]
        snapped[keeper] = grid_point
        used.add(grid_index)
        pending.extend(point_indices[1:])

    pending.sort(key=lambda index: (_nearest_grid_index(points[index], settings), index))
    maximum_ring = max(8, int(ceil(sqrt(len(points)))) + 4)
    for point_index in pending:
        base_x, base_y = _nearest_grid_index(points[point_index], settings)
        chosen_index: tuple[int, int] | None = None
        chosen_score: tuple[float, int, int] | None = None
        ring = 1
        while chosen_index is None:
            for delta_x in range(-ring, ring + 1):
                for delta_y in range(-ring, ring + 1):
                    if max(abs(delta_x), abs(delta_y)) != ring:
                        continue
                    candidate = (base_x + delta_x, base_y + delta_y)
                    if candidate in used:
                        continue
                    candidate_point = _grid_point(candidate, settings)
                    score = (
                        (points[point_index][0] - candidate_point[0]) ** 2
                        + (points[point_index][1] - candidate_point[1]) ** 2,
                        candidate[0],
                        candidate[1],
                    )
                    if chosen_score is None or score < chosen_score:
                        chosen_index = candidate
                        chosen_score = score
            ring += 1
            if ring > maximum_ring and chosen_index is None:
                maximum_ring += max(4, int(ceil(sqrt(len(points)))))
        used.add(chosen_index)
        snapped[point_index] = _grid_point(chosen_index, settings)

    return [point if point is not None else settings.snap_point(points[index]) for index, point in enumerate(snapped)]


def _snap_positions_with_reference_rows(
    points: list[tuple[float, float]],
    settings: DrillGridSettings,
    reference_y: tuple[float, ...],
    *,
    unique: bool,
) -> list[tuple[float, float]]:
    desired = [settings.snap_point(point, reference_y=reference_y) for point in points]
    if not unique:
        return desired

    preferred = [
        abs(target[1] - settings.snap_point(point)[1]) > 1e-9
        for point, target in zip(points, desired)
    ]
    order = sorted(
        range(len(points)),
        key=lambda index: (
            not preferred[index],
            (points[index][0] - desired[index][0]) ** 2 + (points[index][1] - desired[index][1]) ** 2,
            index,
        ),
    )
    snapped: list[tuple[float, float] | None] = [None] * len(points)
    used: set[tuple[float, float]] = set()
    for point_index in order:
        target = desired[point_index]
        target_key = (round(target[0], 9), round(target[1], 9))
        if target_key not in used:
            snapped[point_index] = target
            used.add(target_key)
            continue

        base_x, base_y = _nearest_grid_index(points[point_index], settings)
        chosen: tuple[float, float] | None = None
        chosen_score: tuple[float, float, float] | None = None
        ring = 1
        while chosen is None:
            y_candidates = [
                settings.origin_y + (base_y + delta_y) * settings.spacing_y
                for delta_y in range(-ring, ring + 1)
            ]
            y_candidates.extend(reference_y)
            for delta_x in range(-ring, ring + 1):
                candidate_x = settings.origin_x + (base_x + delta_x) * settings.spacing_x
                for candidate_y in y_candidates:
                    if max(abs(delta_x), abs(round((candidate_y - settings.origin_y) / settings.spacing_y) - base_y)) > ring and candidate_y not in reference_y:
                        continue
                    candidate_key = (round(candidate_x, 9), round(candidate_y, 9))
                    if candidate_key in used:
                        continue
                    score = (
                        (points[point_index][0] - candidate_x) ** 2 + (points[point_index][1] - candidate_y) ** 2,
                        candidate_x,
                        candidate_y,
                    )
                    if chosen_score is None or score < chosen_score:
                        chosen = (candidate_x, candidate_y)
                        chosen_score = score
            ring += 1
        snapped[point_index] = chosen
        used.add((round(chosen[0], 9), round(chosen[1], 9)))
    return [point if point is not None else desired[index] for index, point in enumerate(snapped)]


def snap_position_mapping(
    positions: Mapping[str, tuple[float, float]],
    settings: DrillGridSettings,
    *,
    reference_y: Iterable[float] = (),
) -> dict[str, tuple[float, float]]:
    identifiers = list(positions)
    snapped = snap_positions_to_grid(
        (positions[identifier] for identifier in identifiers),
        settings,
        reference_y=reference_y,
    )
    return dict(zip(identifiers, snapped))
