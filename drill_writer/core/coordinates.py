from __future__ import annotations


STEPS_PER_YARD = 8 / 5
FIELD_HALF_WIDTH_YARDS = 60.0
FIELD_HALF_HEIGHT_YARDS = 26.6665
FRONT_HASH_YARDS = -FIELD_HALF_HEIGHT_YARDS + 20.0
BACK_HASH_YARDS = FIELD_HALF_HEIGHT_YARDS - 20.0


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
        return f"{format_steps(offset_steps)} {step_word(offset_steps)} {side} of 50"

    yard_number = 50 - abs(nearest_line)
    side = "S1" if nearest_line < 0 else "S2"
    if offset_steps < 0.05:
        return f"On {yard_number} {side}"

    direction = "inside" if abs(x) < abs(nearest_line) else "outside"
    return f"{format_steps(offset_steps)} {step_word(offset_steps)} {direction} {yard_number} {side}"


def format_hash_coordinate(y: float) -> str:
    name, reference = min(
        (
            ("FS", -FIELD_HALF_HEIGHT_YARDS),
            ("FH", FRONT_HASH_YARDS),
            ("Mid", 0.0),
            ("BH", BACK_HASH_YARDS),
            ("BS", FIELD_HALF_HEIGHT_YARDS),
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
