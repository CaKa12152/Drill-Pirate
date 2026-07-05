from __future__ import annotations


STEPS_PER_YARD = 8 / 5
FIELD_HALF_WIDTH_YARDS = 60.0
FIELD_HALF_HEIGHT_YARDS = 26.6665
FRONT_HASH_YARDS = -20.0
BACK_HASH_YARDS = 20.0


def format_drill_coordinate(x: float, y: float) -> tuple[str, str]:
    return format_yardline_coordinate(x), format_hash_coordinate(y)


def format_yardline_coordinate(x: float) -> str:
    nearest_line = round(x / 5) * 5
    nearest_line = max(-50, min(50, nearest_line))
    offset_steps = abs(x - nearest_line) * STEPS_PER_YARD

    if abs(nearest_line) < 0.001:
        if offset_steps < 0.05:
            return "On 50"
        side = "S1" if x < 0 else "S2"
        return f"{format_steps(offset_steps)} steps {side} of 50"

    yard_number = 50 - abs(nearest_line)
    side = "S1" if nearest_line < 0 else "S2"
    if offset_steps < 0.05:
        return f"On {yard_number} {side}"

    direction = "inside" if abs(x) < abs(nearest_line) else "outside"
    return f"{format_steps(offset_steps)} steps {direction} {yard_number} {side}"


def format_hash_coordinate(y: float) -> str:
    if y < -FIELD_HALF_HEIGHT_YARDS:
        name = "FS"
        reference = -FIELD_HALF_HEIGHT_YARDS
    elif y > FIELD_HALF_HEIGHT_YARDS:
        name = "BS"
        reference = FIELD_HALF_HEIGHT_YARDS
    elif abs(y + FIELD_HALF_HEIGHT_YARDS) * STEPS_PER_YARD < 0.05:
        return "On FS"
    elif abs(y - FIELD_HALF_HEIGHT_YARDS) * STEPS_PER_YARD < 0.05:
        return "On BS"
    elif abs(y) * STEPS_PER_YARD < 0.05:
        return "On Mid"
    elif y < 0:
        name = "FH"
        reference = FRONT_HASH_YARDS
    else:
        name = "BH"
        reference = BACK_HASH_YARDS

    offset_steps = abs(y - reference) * STEPS_PER_YARD
    if offset_steps < 0.05:
        return f"On {name}"
    if name == "FS":
        direction = "behind" if y > reference else "outside"
    elif name == "BS":
        direction = "in front of" if y < reference else "outside"
    else:
        direction = "in front of" if y < reference else "behind"
    return f"{format_steps(offset_steps)} steps {direction} {name}"


def format_steps(value: float) -> str:
    rounded = round(value * 4) / 4
    if abs(rounded - round(rounded)) < 0.001:
        return str(int(round(rounded)))
    return f"{rounded:g}"
