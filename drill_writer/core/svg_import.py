from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from drill_writer.core.tools import arc_positions, line_positions, positions_along_path


NUMBER_PATTERN = r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
TOKEN_PATTERN = rf"[MmLlHhVvCcQqSsTtAaZz]|{NUMBER_PATTERN}"


def load_svg_points(path: Path) -> list[tuple[float, float]]:
    return [
        point
        for contour in load_svg_contours(path)
        for point in contour
    ]


def load_svg_contours(path: Path) -> list[list[tuple[float, float]]]:
    root = ET.parse(path).getroot()
    contours: list[list[tuple[float, float]]] = []
    for element in root.iter():
        tag = element.tag.split("}")[-1].lower()
        if tag in {"polyline", "polygon"} and element.get("points"):
            shape_points = parse_points(element.get("points", ""))
            if tag == "polygon" and shape_points and shape_points[0] != shape_points[-1]:
                shape_points.append(shape_points[0])
            if len(shape_points) > 1:
                contours.append(shape_points)
        elif tag == "line":
            segment = line_positions(
                16,
                (svg_float(element.get("x1", "0")), svg_float(element.get("y1", "0"))),
                (svg_float(element.get("x2", "0")), svg_float(element.get("y2", "0"))),
            )
            contours.append(segment)
        elif tag == "rect":
            x = svg_float(element.get("x", "0"))
            y = svg_float(element.get("y", "0"))
            width = svg_float(element.get("width", "0"))
            height = svg_float(element.get("height", "0"))
            rect_points = [(x, y), (x + width, y), (x + width, y + height), (x, y + height), (x, y)]
            sampled = positions_along_path(rect_points, 64)
            contours.append(sampled)
        elif tag in {"circle", "ellipse"}:
            cx = svg_float(element.get("cx", "0"))
            cy = svg_float(element.get("cy", "0"))
            rx = svg_float(element.get("rx", element.get("r", "0")))
            ry = svg_float(element.get("ry", element.get("r", str(rx))))
            circle = [
                (cx + (x - cx) * (rx / max(rx, ry, 0.0001)), cy + (y - cy) * (ry / max(rx, ry, 0.0001)))
                for x, y in arc_positions(96, (cx, cy), max(rx, ry), 0, 360)
            ]
            contours.append(circle)
        elif tag == "path" and element.get("d"):
            path_points = parse_path(element.get("d", ""))
            if len(path_points) > 1:
                contours.append(path_points)

    normalized = normalize_contours(contours)
    if not normalized:
        raise ValueError("No usable SVG paths, lines, polygons, circles, or rectangles were found.")
    return normalized


def parse_points(value: str) -> list[tuple[float, float]]:
    numbers = [float(item) for item in re.findall(NUMBER_PATTERN, value)]
    return list(zip(numbers[0::2], numbers[1::2]))


def parse_path(value: str) -> list[tuple[float, float]]:
    tokens = re.findall(TOKEN_PATTERN, value.replace(",", " "))
    points: list[tuple[float, float]] = []
    cursor = (0.0, 0.0)
    start = (0.0, 0.0)
    previous_control = cursor
    index = 0
    command = ""
    while index < len(tokens):
        if re.match(r"[A-Za-z]", tokens[index]):
            command = tokens[index]
            index += 1
            if command.upper() == "Z":
                points.extend(line_positions(12, cursor, start)[1:])
                cursor = start
                command = ""
                continue
        if not command:
            continue
        if index >= len(tokens):
            command = ""
            continue
        absolute = command.isupper()
        cmd = command.upper()
        remaining = len(tokens) - index
        try:
            if cmd == "M" and remaining >= 2:
                cursor = read_point(tokens, index, cursor, absolute)
                start = cursor
                points.append(cursor)
                index += 2
                command = "L" if absolute else "l"
            elif cmd == "L" and remaining >= 2:
                next_point = read_point(tokens, index, cursor, absolute)
                points.extend(line_positions(12, cursor, next_point)[1:])
                cursor = next_point
                index += 2
            elif cmd == "H" and remaining >= 1:
                x = float(tokens[index]) + (0 if absolute else cursor[0])
                next_point = (x, cursor[1])
                points.extend(line_positions(12, cursor, next_point)[1:])
                cursor = next_point
                index += 1
            elif cmd == "V" and remaining >= 1:
                y = float(tokens[index]) + (0 if absolute else cursor[1])
                next_point = (cursor[0], y)
                points.extend(line_positions(12, cursor, next_point)[1:])
                cursor = next_point
                index += 1
            elif cmd == "C" and remaining >= 6:
                p1 = read_point(tokens, index, cursor, absolute)
                p2 = read_point(tokens, index + 2, cursor, absolute)
                end = read_point(tokens, index + 4, cursor, absolute)
                points.extend(sample_cubic(cursor, p1, p2, end, 20)[1:])
                previous_control = p2
                cursor = end
                index += 6
            elif cmd == "S" and remaining >= 4:
                p1 = (cursor[0] * 2 - previous_control[0], cursor[1] * 2 - previous_control[1])
                p2 = read_point(tokens, index, cursor, absolute)
                end = read_point(tokens, index + 2, cursor, absolute)
                points.extend(sample_cubic(cursor, p1, p2, end, 20)[1:])
                previous_control = p2
                cursor = end
                index += 4
            elif cmd == "Q" and remaining >= 4:
                p1 = read_point(tokens, index, cursor, absolute)
                end = read_point(tokens, index + 2, cursor, absolute)
                points.extend(sample_quadratic(cursor, p1, end, 20)[1:])
                previous_control = p1
                cursor = end
                index += 4
            elif cmd == "T" and remaining >= 2:
                p1 = (cursor[0] * 2 - previous_control[0], cursor[1] * 2 - previous_control[1])
                end = read_point(tokens, index, cursor, absolute)
                points.extend(sample_quadratic(cursor, p1, end, 20)[1:])
                previous_control = p1
                cursor = end
                index += 2
            elif cmd == "A" and remaining >= 7:
                end = read_point(tokens, index + 5, cursor, absolute)
                points.extend(line_positions(16, cursor, end)[1:])
                cursor = end
                index += 7
            elif cmd == "Z":
                points.extend(line_positions(12, cursor, start)[1:])
                cursor = start
                index += 1
                command = ""
            else:
                index += max(1, command_parameter_count(cmd))
        except (ValueError, IndexError):
            index += 1
    return points


def command_parameter_count(command: str) -> int:
    return {
        "M": 2,
        "L": 2,
        "H": 1,
        "V": 1,
        "C": 6,
        "S": 4,
        "Q": 4,
        "T": 2,
        "A": 7,
        "Z": 0,
    }.get(command, 1)


def svg_float(value: str | None) -> float:
    match = re.search(NUMBER_PATTERN, value or "0")
    return float(match.group(0)) if match else 0.0


def read_point(
    tokens: list[str],
    index: int,
    cursor: tuple[float, float],
    absolute: bool,
) -> tuple[float, float]:
    x = float(tokens[index])
    y = float(tokens[index + 1])
    if absolute:
        return (x, y)
    return (cursor[0] + x, cursor[1] + y)


def sample_cubic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    samples: int,
) -> list[tuple[float, float]]:
    return [
        (
            (1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * p1[0] + 3 * (1 - t) * t**2 * p2[0] + t**3 * p3[0],
            (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * p1[1] + 3 * (1 - t) * t**2 * p2[1] + t**3 * p3[1],
        )
        for t in (index / samples for index in range(samples + 1))
    ]


def sample_quadratic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    samples: int,
) -> list[tuple[float, float]]:
    return [
        (
            (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0],
            (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1],
        )
        for t in (index / samples for index in range(samples + 1))
    ]


def normalize_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    contours = normalize_contours([points])
    return contours[0] if contours else []


def normalize_contours(contours: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    usable_contours = [contour for contour in contours if contour]
    if not usable_contours:
        return []
    points = [point for contour in usable_contours for point in contour]
    min_x = min(x for x, _y in points)
    max_x = max(x for x, _y in points)
    min_y = min(y for _x, y in points)
    max_y = max(y for _x, y in points)
    width = max(0.0001, max_x - min_x)
    height = max(0.0001, max_y - min_y)
    scale = max(width, height)
    return [
        [
            ((x - (min_x + width / 2)) / scale, -((y - (min_y + height / 2)) / scale))
            for x, y in contour
        ]
        for contour in usable_contours
    ]
