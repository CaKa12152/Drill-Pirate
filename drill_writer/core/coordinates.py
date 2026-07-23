from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from math import floor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from drill_writer.core.models import SurfaceDefinition


STEPS_PER_YARD = 8 / 5
FIELD_HALF_WIDTH_YARDS = 60.0
FIELD_HALF_HEIGHT_YARDS = 80 / 3
FRONT_HASH_YARDS = -20 / 3
BACK_HASH_YARDS = 20 / 3


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
        return f"Station {format_yards(station)} yd", f"{format_yards(abs(side))} yd {side_text} of route center"
    return format_centered_surface_coordinate(x, y)


def format_yardline_coordinate(x: float, playing_half_width: float = 50.0) -> str:
    playing_half_width = max(5.0, float(playing_half_width))
    if abs(x) > playing_half_width + 0.0001:
        side = "S1" if x < 0 else "S2"
        endzone_steps = (abs(x) - playing_half_width) * STEPS_PER_YARD
        if rounded_increment(endzone_steps, 0.25) < 0.001:
            return f"On G {side}"
        return f"{format_steps(endzone_steps)} {step_word(endzone_steps)} into end zone {side}"

    magnitude = min(abs(float(x)), playing_half_width)
    lower_line = floor(magnitude / 5.0) * 5.0
    remainder = magnitude - lower_line
    nearest_magnitude = lower_line + (5.0 if remainder > 2.5 else 0.0)
    nearest_magnitude = min(playing_half_width, nearest_magnitude)
    nearest_line = -nearest_magnitude if x < 0 else nearest_magnitude
    offset_steps = abs(x - nearest_line) * STEPS_PER_YARD

    if abs(nearest_line) < 0.001:
        if rounded_increment(offset_steps, 0.25) < 0.001:
            return "On 50"
        side = "S1" if x < 0 else "S2"
        return f"{format_steps(offset_steps)} {step_word(offset_steps)} {side} of 50"

    yard_number = playing_half_width - abs(nearest_line)
    yard_label = "G" if abs(yard_number) < 0.001 else f"{yard_number:g}"
    side = "S1" if nearest_line < 0 else "S2"
    if rounded_increment(offset_steps, 0.25) < 0.001:
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
            ("FH", front_hash),
            ("BH", back_hash),
        ),
        key=lambda item: abs(y - item[1]),
    )

    offset_steps = abs(y - reference) * STEPS_PER_YARD
    if rounded_increment(offset_steps, 0.25) < 0.001:
        return f"On {name}"
    direction = "in front of" if y < reference else "behind"
    return f"{format_steps(offset_steps)} {step_word(offset_steps)} {direction} {name}"


def format_steps(value: float) -> str:
    rounded = rounded_increment(value, 0.25)
    if abs(rounded - round(rounded)) < 0.001:
        return str(int(round(rounded)))
    return f"{rounded:g}"


def step_word(value: float) -> str:
    return "step" if abs(rounded_increment(value, 0.25) - 1.0) < 0.001 else "steps"


def format_centered_surface_coordinate(x: float, y: float) -> tuple[str, str]:
    if abs(x) < 0.005:
        horizontal = "On Center Line"
    else:
        side = "Side 1" if x < 0 else "Side 2"
        horizontal = f"{format_yards(abs(x))} yd {side} of Center Line"
    if abs(y) < 0.005:
        vertical = "On Center"
    else:
        direction = "in front of" if y < 0 else "behind"
        vertical = f"{format_yards(abs(y))} yd {direction} Center"
    return horizontal, vertical


def format_yards(value: float) -> str:
    rounded = rounded_increment(value, 0.01)
    return f"{rounded:.2f}"


def rounded_increment(value: float, increment: float) -> float:
    decimal_value = Decimal(str(float(value)))
    decimal_increment = Decimal(str(float(increment)))
    if decimal_increment <= 0:
        return float(decimal_value)
    units = (decimal_value / decimal_increment).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    result = units * decimal_increment
    return 0.0 if result == 0 else float(result)
