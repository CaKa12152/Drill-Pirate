from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping
from uuid import uuid4


PRINT_LAYOUT_SCHEMA_VERSION = 1
PAGE_SIZES = ("Letter", "Legal", "A4", "A3")
PAGE_ORIENTATIONS = ("portrait", "landscape")
ELEMENT_TYPES = ("text", "image", "field", "table", "rectangle", "line")


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: Any, minimum: float, maximum: float, default: float) -> float:
    return max(minimum, min(maximum, _number(value, default)))


@dataclass(slots=True)
class PrintLayoutElement:
    element_type: str = "text"
    x: float = 0.05
    y: float = 0.05
    width: float = 0.4
    height: float = 0.08
    element_id: str = field(default_factory=lambda: uuid4().hex)
    z_index: int = 0
    rotation_degrees: float = 0.0
    text: str = "Custom text"
    font_family: str = "Arial"
    font_size: float = 14.0
    bold: bool = False
    italic: bool = False
    color: str = "#17202a"
    background: str = "#00000000"
    border_color: str = "#00000000"
    border_width: float = 0.0
    opacity: float = 1.0
    alignment: str = "left"
    image_path: str = ""
    fit_mode: str = "contain"
    corner_radius: float = 0.0
    padding: float = 4.0
    visible: bool = True
    locked: bool = False

    def __post_init__(self) -> None:
        if self.element_type not in ELEMENT_TYPES:
            self.element_type = "text"
        self.x = _clamp(self.x, 0.0, 1.0, 0.05)
        self.y = _clamp(self.y, 0.0, 1.0, 0.05)
        self.width = _clamp(self.width, 0.01, 1.0, 0.4)
        self.height = _clamp(self.height, 0.01, 1.0, 0.08)
        self.x = min(self.x, 1.0 - self.width)
        self.y = min(self.y, 1.0 - self.height)
        self.font_size = _clamp(self.font_size, 4.0, 160.0, 14.0)
        self.rotation_degrees = _clamp(self.rotation_degrees, -360.0, 360.0, 0.0)
        self.border_width = _clamp(self.border_width, 0.0, 20.0, 0.0)
        self.opacity = _clamp(self.opacity, 0.0, 1.0, 1.0)
        self.corner_radius = _clamp(self.corner_radius, 0.0, 100.0, 0.0)
        self.padding = _clamp(self.padding, 0.0, 100.0, 4.0)
        self.alignment = self.alignment if self.alignment in {"left", "center", "right"} else "left"
        self.fit_mode = self.fit_mode if self.fit_mode in {"contain", "cover", "stretch"} else "contain"

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.element_id,
            "type": self.element_type,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "z_index": self.z_index,
            "rotation_degrees": self.rotation_degrees,
            "text": self.text,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "bold": self.bold,
            "italic": self.italic,
            "color": self.color,
            "background": self.background,
            "border_color": self.border_color,
            "border_width": self.border_width,
            "opacity": self.opacity,
            "alignment": self.alignment,
            "image_path": self.image_path,
            "fit_mode": self.fit_mode,
            "corner_radius": self.corner_radius,
            "padding": self.padding,
            "visible": self.visible,
            "locked": self.locked,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any] | None) -> "PrintLayoutElement":
        data = payload if isinstance(payload, Mapping) else {}
        return cls(
            element_id=str(data.get("id") or uuid4().hex),
            element_type=str(data.get("type", "text")),
            x=_number(data.get("x"), 0.05),
            y=_number(data.get("y"), 0.05),
            width=_number(data.get("width"), 0.4),
            height=_number(data.get("height"), 0.08),
            z_index=int(_number(data.get("z_index"), 0)),
            rotation_degrees=_number(data.get("rotation_degrees"), 0.0),
            text=str(data.get("text", "Custom text")),
            font_family=str(data.get("font_family", "Arial")),
            font_size=_number(data.get("font_size"), 14.0),
            bold=bool(data.get("bold", False)),
            italic=bool(data.get("italic", False)),
            color=str(data.get("color", "#17202a")),
            background=str(data.get("background", "#00000000")),
            border_color=str(data.get("border_color", "#00000000")),
            border_width=_number(data.get("border_width"), 0.0),
            opacity=_number(data.get("opacity"), 1.0),
            alignment=str(data.get("alignment", "left")),
            image_path=str(data.get("image_path", "")),
            fit_mode=str(data.get("fit_mode", "contain")),
            corner_radius=_number(data.get("corner_radius"), 0.0),
            padding=_number(data.get("padding"), 4.0),
            visible=bool(data.get("visible", True)),
            locked=bool(data.get("locked", False)),
        )


@dataclass(slots=True)
class PrintLayout:
    name: str = "Custom Layout"
    profile: str = "drill_sheet"
    page_size: str = "Letter"
    orientation: str = "landscape"
    background: str = "#ffffff"
    elements: list[PrintLayoutElement] = field(default_factory=list)
    schema_version: int = PRINT_LAYOUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.page_size = self.page_size if self.page_size in PAGE_SIZES else "Letter"
        self.orientation = self.orientation if self.orientation in PAGE_ORIENTATIONS else "landscape"
        self.elements = [
            element if isinstance(element, PrintLayoutElement) else PrintLayoutElement.from_json(element)
            for element in self.elements
        ]

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": PRINT_LAYOUT_SCHEMA_VERSION,
            "name": self.name,
            "profile": self.profile,
            "page_size": self.page_size,
            "orientation": self.orientation,
            "background": self.background,
            "elements": [element.to_json() for element in self.elements],
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any] | None, profile: str = "drill_sheet") -> "PrintLayout":
        data = payload if isinstance(payload, Mapping) else {}
        return cls(
            name=str(data.get("name", "Custom Layout")),
            profile=str(data.get("profile", profile)),
            page_size=str(data.get("page_size", "Letter")),
            orientation=str(data.get("orientation", "landscape")),
            background=str(data.get("background", "#ffffff")),
            elements=[
                PrintLayoutElement.from_json(element)
                for element in data.get("elements", [])
                if isinstance(element, Mapping)
            ],
            schema_version=int(_number(data.get("schema_version"), PRINT_LAYOUT_SCHEMA_VERSION)),
        )


def default_print_layout(profile: str) -> PrintLayout:
    normalized = profile if profile in {"drill_sheet", "dot_book", "staff_packet", "section_packet", "coordinate_summary"} else "drill_sheet"
    portrait = normalized == "dot_book"
    elements = [
        PrintLayoutElement(
            element_type="text",
            x=0.04,
            y=0.035,
            width=0.92,
            height=0.065,
            text="{page_title}",
            font_size=22,
            bold=True,
            color="#17202a",
        ),
        PrintLayoutElement(
            element_type="text",
            x=0.04,
            y=0.105,
            width=0.92,
            height=0.04,
            text="{page_subtitle}",
            font_size=10,
            color="#596575",
        ),
        PrintLayoutElement(
            element_type="field",
            x=0.04,
            y=0.17,
            width=0.92,
            height=0.74,
            border_color="#d8dee8",
            border_width=1,
            background="#f5f7fb",
        ),
        PrintLayoutElement(
            element_type="table",
            x=0.04,
            y=0.17,
            width=0.92,
            height=0.74,
            font_size=9,
            border_color="#d8dee8",
            border_width=1,
        ),
        PrintLayoutElement(
            element_type="text",
            x=0.04,
            y=0.935,
            width=0.92,
            height=0.025,
            text="{footer}",
            font_size=8,
            color="#596575",
            alignment="right",
        ),
    ]
    if normalized == "dot_book":
        elements[1].text = "{performer}  •  {section}  •  {instrument}"
        elements[3].y = 0.16
        elements[3].height = 0.77
        elements = [elements[0], elements[1], elements[3], elements[4]]
    elif normalized == "coordinate_summary":
        elements = [elements[0], elements[1], elements[3], elements[4]]
    elif normalized == "drill_sheet":
        elements = [elements[0], elements[1], elements[2], elements[4]]
    return PrintLayout(
        name=f"{normalized.replace('_', ' ').title()} Default",
        profile=normalized,
        orientation="portrait" if portrait else "landscape",
        elements=elements,
    )


def expand_layout_text(text: str, context: Mapping[str, Any]) -> str:
    result = str(text)
    for key, value in context.items():
        result = result.replace("{" + str(key) + "}", str(value))
    return result
