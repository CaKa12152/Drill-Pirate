from __future__ import annotations

import json
import shutil
from math import ceil, sqrt
from pathlib import Path
from typing import Any

from drill_writer.core.models import (
    AudioVersion,
    Dot,
    DotConstraint,
    DrillProject,
    DrillSet,
    Marker,
    ProjectMetadata,
    Prop,
    TimingEvent,
)


PROJECTS_DIR = Path.home() / "Documents" / "Drill Pirate Projects"


def create_project_folder(
    root: Path,
    title: str,
    audio_source: Path | None,
    tempo: float,
    counts_per_set: int,
    time_signature: str,
    marcher_count: int = 30,
) -> Path:
    project_dir = root / safe_folder_name(title)
    (project_dir / "audio").mkdir(parents=True, exist_ok=True)
    (project_dir / "props").mkdir(parents=True, exist_ok=True)

    audio_file = ""
    if audio_source and audio_source.exists():
        destination = project_dir / "audio" / audio_source.name
        if audio_source.resolve() != destination.resolve():
            shutil.copy2(audio_source, destination)
        audio_file = str(destination.relative_to(project_dir))

    metadata = ProjectMetadata(
        show_title=title,
        initial_tempo=tempo,
        default_counts_per_set=counts_per_set,
        time_signature=time_signature,
        audio_file=audio_file,
    )
    project = DrillProject(
        metadata=metadata,
        dots=default_dots(marcher_count),
        sets=[
            DrillSet(
                name="Set 1",
                start_count=1,
                end_count=counts_per_set,
                tempo=None,
                dot_positions={},
            )
        ],
        audio_versions=[
            AudioVersion(name="Main Audio", audio_file=audio_file, active=True)
        ]
        if audio_file
        else [],
    )
    project.ensure_set_positions()
    save_project(project_dir, project)
    return project_dir


def project_library_dir() -> Path:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    return PROJECTS_DIR


def discover_projects(root: Path | None = None) -> list[Path]:
    library = root or project_library_dir()
    if not library.exists():
        return []
    projects = [
        path
        for path in library.iterdir()
        if path.is_dir()
        and (path / "metadata.json").exists()
        and (path / "sets.json").exists()
        and (path / "dots.json").exists()
    ]
    return sorted(projects, key=lambda path: path.stat().st_mtime, reverse=True)


def load_project(project_dir: Path) -> DrillProject:
    metadata = ProjectMetadata.from_json(read_json(project_dir / "metadata.json"))
    dots = [Dot.from_json(item) for item in read_json(project_dir / "dots.json").get("dots", [])]
    props = [Prop.from_json(item) for item in read_json(project_dir / "props.json").get("props", [])]
    sets = [DrillSet.from_json(item) for item in read_json(project_dir / "sets.json").get("sets", [])]
    show = read_json(project_dir / "show.json")
    markers = [Marker.from_json(item) for item in show.get("markers", [])]
    constraints = [DotConstraint.from_json(item) for item in show.get("constraints", [])]
    audio_versions = [
        AudioVersion.from_json(item)
        for item in show.get("audio_versions", [])
    ]
    if not audio_versions and metadata.audio_file:
        audio_versions = [AudioVersion(name="Main Audio", audio_file=metadata.audio_file, active=True)]
    timing_events = [
        TimingEvent.from_json(item)
        for item in show.get("timing_events", [])
    ]
    project = DrillProject(
        metadata=metadata,
        dots=dots,
        props=props,
        sets=sets,
        markers=markers,
        constraints=constraints,
        audio_versions=audio_versions,
        timing_events=timing_events,
    )
    project.ensure_set_positions()
    return project


def save_project(project_dir: Path, project: DrillProject) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "audio").mkdir(exist_ok=True)
    (project_dir / "props").mkdir(exist_ok=True)
    write_json(project_dir / "metadata.json", project.metadata.to_json())
    write_json(project_dir / "dots.json", {"dots": [dot.to_json() for dot in project.dots]})
    write_json(project_dir / "props.json", {"props": [prop.to_json() for prop in project.props]})
    write_json(project_dir / "sets.json", {"sets": [drill_set.to_json() for drill_set in project.sets]})
    write_json(
        project_dir / "show.json",
        {
            "title": project.metadata.show_title,
            "version": 1,
            "markers": [marker.to_json() for marker in project.markers],
            "constraints": [constraint.to_json() for constraint in project.constraints],
            "audio_versions": [audio.to_json() for audio in project.audio_versions],
            "timing_events": [event.to_json() for event in project.timing_events],
        },
    )


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def safe_folder_name(title: str) -> str:
    safe = "".join(char for char in title.strip() if char.isalnum() or char in (" ", "-", "_"))
    return safe.strip().replace(" ", "_") or "Untitled_Show"


def default_dots(count: int = 30) -> list[Dot]:
    positions = optimized_starting_block(count)
    dots: list[Dot] = []
    for index, (x, y) in enumerate(positions):
        section = "winds"
        dots.append(
            Dot(
                id=f"dot{index + 1:03d}",
                name=f"Dot {index + 1}",
                x=x,
                y=y,
                color="#e53935",
                section=section,
                layer="Main",
            )
        )
    return dots


def optimized_starting_block(count: int) -> list[tuple[float, float]]:
    count = max(1, int(count))
    field_width = 112.0
    field_height = 48.0
    preferred_spacing = 2.0
    min_spacing = 0.9
    best_columns = 1
    best_rows = count
    best_spacing = min_spacing
    best_score = float("inf")

    for columns in range(1, count + 1):
        rows = ceil(count / columns)
        horizontal_spacing = field_width / max(1, columns - 1) if columns > 1 else preferred_spacing
        vertical_spacing = field_height / max(1, rows - 1) if rows > 1 else preferred_spacing
        spacing = min(preferred_spacing, horizontal_spacing, vertical_spacing)
        if spacing < min_spacing:
            continue
        aspect_score = abs((columns / rows) - 2.0)
        spacing_score = abs(preferred_spacing - spacing)
        score = spacing_score * 5 + aspect_score
        if score < best_score:
            best_columns = columns
            best_rows = rows
            best_spacing = spacing
            best_score = score

    if best_score == float("inf"):
        best_columns = min(count, max(1, int(sqrt(count * field_width / field_height))))
        best_rows = ceil(count / best_columns)
        best_spacing = min(field_width / max(1, best_columns - 1), field_height / max(1, best_rows - 1))

    block_width = (best_columns - 1) * best_spacing
    block_height = (best_rows - 1) * best_spacing
    start_x = -block_width / 2
    start_y = block_height / 2
    positions: list[tuple[float, float]] = []
    for row in range(best_rows):
        row_count = min(best_columns, count - len(positions))
        row_width = (row_count - 1) * best_spacing
        row_start_x = -row_width / 2
        for column in range(row_count):
            positions.append((row_start_x + column * best_spacing, start_y - row * best_spacing))
            if len(positions) >= count:
                return positions
    return positions
