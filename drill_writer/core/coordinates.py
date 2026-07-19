from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from drill_writer.core.models import SurfaceDefinition


STEPS_PER_YARD = 8 / 5
FIELD_HALF_WIDTH_YARDS = 60.0
FIELD_HALF_HEIGHT_YARDS = 26.6665
FRONT_HASH_YARDS = -FIELD_HALF_HEIGHT_YARDS + 20.0
BACK_HASH_YARDS = FIELD_HALF_HEIGHT_YARDS - 20.0


def format_drill_coordinate(x: float, y: float) -> tuple[str, str]:
    return format_yardline_coordinate(x), format_hash_coordinate(y)


def format_surface_coordinate(surface: "SurfaceDefinition", x: float, y: float) -> tuple[str, str]:
    if surface.surface_type == "football":
        playing_half_width = max(5.0, surface.half_width - surface.endzone_depth_yards)
        return (
            format_yardline_coordinate(x, playing_half_width),
            format_hash_coordinate(y, surface.half_height, surface.front_hash_yards, surface.back_hash_yards),
        )
    if surface.surface_type == "parade" and len(surface.route_points) >= 2:
        from drill_writer.core.specialized_design import closest_route_position

        station, side, _nearest = closest_route_position(surface, (x, y))
        side_text = "left" if side >= 0 else "right"
        return f"Station {station:.2f} yd", f"{abs(side):.2f} yd {side_text} of route"
    return f"X {x:+.2f} yd from center", f"Y {y:+.2f} yd from center"


def format_yardline_coordinate(x: float, playing_half_width: float = 50.0) -> str:
    nearest_line = round(x / 5) * 5
    nearest_line = max(-playing_half_width, min(playing_half_width, nearest_line))
    offset_steps = abs(x - nearest_line) * STEPS_PER_YARD

    if abs(nearest_line) < 0.001:
        if offset_steps < 0.05:
            return "On 50"
        side = "S1" if x < 0 else "S2"
        return f"{format_steps(offset_steps)} {step_word(offset_steps)} {side} of 50"

    yard_number = playing_half_width - abs(nearest_line)
    yard_label = f"{yard_number:g}"
    side = "S1" if nearest_line < 0 else "S2"
    if offset_steps < 0.05:
        return f"On {yard_label} {side}"

    direction = "inside" if abs(x) < abs(nearest_line) else "outside"
    return f"{format_steps(offset_steps)} {step_word(offset_steps)} {direction} {yard_label} {side}"


def format_hash_coordinate(
    y: float,
    half_height: float = FIELD_HALF_HEIGHT_YARDS,
    front_hash: float = FRONT_HASH_YARDS,
    back_hash: float = BACK_HASH_YARDS,
) -> str:
    name, reference = min(
        (
            ("FS", -half_height),
            ("FH", front_hash),
            ("Mid", 0.0),
            ("BH", back_hash),
            ("BS", half_height),
        ),
        key=lambda item: abs(y - item[1]),
    )

    offset_steps = abs(y - reference) * STEPS_PER_YARD
    if offset_steps < 0.05:
        return f"On {name}"
    if name == "FS":
        direction = "behind" if y > reference else "outside"
    elif name == "BS":
        direction = "in front of" if y < reference else "outside"
    elif name == "Mid":
        direction = "in front of" if y < reference else "behind"
    else:
        direction = "in front of" if y < reference else "behind"
    return f"{format_steps(offset_steps)} {step_word(offset_steps)} {direction} {name}"


def format_steps(value: float) -> str:
    rounded = round(value * 4) / 4
    if abs(rounded - round(rounded)) < 0.001:
        return str(int(round(rounded)))
    return f"{rounded:g}"


def step_word(value: float) -> str:
    return "step" if abs((round(value * 4) / 4) - 1.0) < 0.001 else "steps"
