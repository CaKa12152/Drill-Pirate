from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from drill_writer.core.models import Dot, DrillProject, DrillSet, Marker, ProjectMetadata


PROJECTS_DIR = Path.home() / "Documents" / "Drill Pirate Projects"


def create_project_folder(
    root: Path,
    title: str,
    audio_source: Path | None,
    tempo: float,
    counts_per_set: int,
    time_signature: str,
) -> Path:
    project_dir = root / safe_folder_name(title)
    (project_dir / "audio").mkdir(parents=True, exist_ok=True)

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
        dots=default_dots(),
        sets=[
            DrillSet(
                name="Set 1",
                start_count=1,
                end_count=counts_per_set,
                tempo=tempo,
                dot_positions={},
            )
        ],
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
    sets = [DrillSet.from_json(item) for item in read_json(project_dir / "sets.json").get("sets", [])]
    show = read_json(project_dir / "show.json")
    markers = [Marker.from_json(item) for item in show.get("markers", [])]
    project = DrillProject(metadata=metadata, dots=dots, sets=sets, markers=markers)
    project.ensure_set_positions()
    return project


def save_project(project_dir: Path, project: DrillProject) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "audio").mkdir(exist_ok=True)
    write_json(project_dir / "metadata.json", project.metadata.to_json())
    write_json(project_dir / "dots.json", {"dots": [dot.to_json() for dot in project.dots]})
    write_json(project_dir / "sets.json", {"sets": [drill_set.to_json() for drill_set in project.sets]})
    write_json(
        project_dir / "show.json",
        {
            "title": project.metadata.show_title,
            "version": 1,
            "markers": [marker.to_json() for marker in project.markers],
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


def default_dots() -> list[Dot]:
    dots: list[Dot] = []
    for index in range(30):
        section = "winds" if index < 24 else "battery"
        row = index // 10
        col = index % 10
        dots.append(
            Dot(
                id=f"dot{index + 1:03d}",
                name=f"Dot {index + 1}",
                x=-45 + col * 10,
                y=-12 + row * 8,
                color="#e53935",
                section=section,
            )
        )
    return dots
