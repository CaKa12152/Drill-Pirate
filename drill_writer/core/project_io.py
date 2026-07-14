from __future__ import annotations

import json
import shutil
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil, cos, sin, sqrt
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
    Transition,
)


PROJECTS_DIR = Path.home() / "Documents" / "Drill Pirate Projects"
PROJECT_SCHEMA_VERSION = 2
PROJECT_JSON_FILES = ("metadata.json", "dots.json", "props.json", "sets.json", "show.json")
REQUIRED_PROJECT_FILES = ("metadata.json", "dots.json", "sets.json")
BACKUP_DIR_NAME = ".drill_pirate_backups"
MAX_PROJECT_BACKUPS = 40
COMMON_INSTRUMENT_PREFIXES = {
    "flute": "F",
    "piccolo": "P",
    "clarinet": "C",
    "bass clarinet": "BC",
    "alto sax": "AS",
    "alto saxophone": "AS",
    "tenor sax": "TS",
    "tenor saxophone": "TS",
    "baritone sax": "BS",
    "baritone saxophone": "BS",
    "saxophone": "S",
    "trumpet": "T",
    "mellophone": "M",
    "french horn": "FH",
    "horn": "H",
    "trombone": "TR",
    "baritone": "B",
    "euphonium": "E",
    "tuba": "TU",
    "sousaphone": "SU",
    "snare": "S",
    "tenor": "TN",
    "quads": "Q",
    "bass drum": "BD",
    "cymbal": "CY",
    "guard": "G",
    "color guard": "CG",
    "rifle": "R",
    "sabre": "SB",
    "saber": "SB",
    "flag": "FL",
}

InstrumentationEntry = tuple[str, int] | tuple[str, str, int]


class ProjectLoadError(Exception):
    def __init__(self, project_dir: Path, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.project_dir = project_dir
        self.cause = cause


@dataclass(slots=True)
class ProjectBackup:
    path: Path
    created_at: str
    reason: str
    schema_version: int

    @property
    def label(self) -> str:
        reason = self.reason.replace("_", " ").title() or "Backup"
        version = f"schema v{self.schema_version}" if self.schema_version else "unknown schema"
        return f"{self.created_at} - {reason} - {version}"


def create_project_folder(
    root: Path,
    title: str,
    audio_source: Path | None,
    tempo: float,
    counts_per_set: int,
    time_signature: str,
    marcher_count: int = 30,
    instrumentation: list[InstrumentationEntry] | None = None,
    front_ensemble_count: int = 0,
    drum_major_stands: int = 0,
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
    props = default_props(front_ensemble_count, drum_major_stands)
    project = DrillProject(
        metadata=metadata,
        dots=default_dots(marcher_count, instrumentation=instrumentation),
        props=props,
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
    save_project(project_dir, project, backup=False)
    return project_dir


def create_tutorial_project(root: Path | None = None) -> Path:
    library = root or project_library_dir()
    project_dir = unique_project_folder(library, "Drill Pirate Tutorial")
    (project_dir / "audio").mkdir(parents=True, exist_ok=True)
    (project_dir / "props").mkdir(parents=True, exist_ok=True)

    metadata = ProjectMetadata(
        show_title="Drill Pirate Tutorial",
        initial_tempo=120,
        default_counts_per_set=8,
        time_signature="4/4",
        audio_file="",
    )
    dots = []
    line_start_x = -22.0
    for index in range(16):
        dots.append(
            Dot(
                id=f"dot{index + 1:03d}",
                name=f"Tutorial {index + 1}",
                x=line_start_x + index * 3.0,
                y=-8.0,
                color="#e53935",
                section="Tutorial",
                instrument="",
                rank="",
                equipment="",
                layer="Main",
            )
        )

    set_one = DrillSet(
        name="Set 1 - Starting Line",
        start_count=1,
        end_count=8,
        tempo=None,
        dot_positions={dot.id: (dot.x, dot.y) for dot in dots},
        transition=Transition.LINEAR,
    )
    circle_positions_by_id = {}
    radius = 13.0
    for index, dot in enumerate(dots):
        angle = (index / len(dots)) * 6.283185307179586
        circle_positions_by_id[dot.id] = (round(radius * cos(angle), 3), round(radius * sin(angle), 3))
    set_two = DrillSet(
        name="Set 2 - Circle Move",
        start_count=9,
        end_count=16,
        tempo=None,
        dot_positions=circle_positions_by_id,
        transition=Transition.EASE_IN_OUT,
    )
    project = DrillProject(
        metadata=metadata,
        dots=dots,
        sets=[set_one, set_two],
        markers=[
            Marker(count=1, label="Start"),
            Marker(count=9, label="Move"),
        ],
    )
    project.ensure_set_positions()
    save_project(project_dir, project, backup=False)
    return project_dir


def unique_project_folder(root: Path, title: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    base = safe_folder_name(title)
    candidate = root / base
    suffix = 2
    while candidate.exists():
        candidate = root / f"{base}_{suffix}"
        suffix += 1
    return candidate


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
    try:
        migrate_project_files(project_dir)
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
        if not sets:
            raise ProjectLoadError(project_dir, "Project has no sets.")
        project = DrillProject(
            metadata=metadata,
            dots=dots,
            props=props,
            sets=sets,
            markers=markers,
            constraints=constraints,
            audio_versions=audio_versions,
            timing_events=timing_events,
            workflow=dict(show.get("workflow", {})) if isinstance(show.get("workflow", {}), dict) else {},
        )
        project.ensure_set_positions()
        return project
    except ProjectLoadError:
        raise
    except Exception as exc:
        raise ProjectLoadError(project_dir, f"Could not load project '{project_dir.name}': {exc}", exc) from exc


def load_project_preview(project_dir: Path) -> DrillProject:
    try:
        metadata = ProjectMetadata.from_json(read_json(project_dir / "metadata.json"))
        dots = [Dot.from_json(item) for item in read_json(project_dir / "dots.json").get("dots", [])]
        props = [Prop.from_json(item) for item in read_json(project_dir / "props.json").get("props", [])]
        raw_sets = read_json(project_dir / "sets.json").get("sets", [])
        first_set = DrillSet.from_json(raw_sets[0]) if raw_sets else DrillSet("Set 1", 1, 1)
        project = DrillProject(metadata=metadata, dots=dots, props=props, sets=[first_set])
        project.workflow["preview_set_count"] = len(raw_sets)
        project.ensure_set_positions()
        return project
    except Exception as exc:
        raise ProjectLoadError(project_dir, f"Could not preview project '{project_dir.name}': {exc}", exc) from exc


def save_project(
    project_dir: Path,
    project: DrillProject,
    *,
    backup: bool = True,
    backup_reason: str = "manual",
    backup_min_interval_seconds: int = 0,
) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "audio").mkdir(exist_ok=True)
    (project_dir / "props").mkdir(exist_ok=True)
    if backup:
        create_project_backup(
            project_dir,
            reason=backup_reason,
            min_interval_seconds=backup_min_interval_seconds,
        )
    write_json(project_dir / "metadata.json", project.metadata.to_json())
    write_json(project_dir / "dots.json", {"dots": [dot.to_json() for dot in project.dots]})
    write_json(project_dir / "props.json", {"props": [prop.to_json() for prop in project.props]})
    write_json(project_dir / "sets.json", {"sets": [drill_set.to_json() for drill_set in project.sets]})
    write_json(
        project_dir / "show.json",
        {
            "title": project.metadata.show_title,
            "version": PROJECT_SCHEMA_VERSION,
            "schema_version": PROJECT_SCHEMA_VERSION,
            "markers": [marker.to_json() for marker in project.markers],
            "constraints": [constraint.to_json() for constraint in project.constraints],
            "audio_versions": [audio.to_json() for audio in project.audio_versions],
            "timing_events": [event.to_json() for event in project.timing_events],
            "workflow": dict(project.workflow),
        },
    )


def migrate_project_files(project_dir: Path) -> None:
    missing = [name for name in REQUIRED_PROJECT_FILES if not (project_dir / name).exists()]
    if missing:
        raise ProjectLoadError(project_dir, f"Project is missing required file(s): {', '.join(missing)}")

    try:
        metadata = read_json(project_dir / "metadata.json")
        dots = read_json(project_dir / "dots.json")
        sets = read_json(project_dir / "sets.json")
        show_path = project_dir / "show.json"
        show = read_json(show_path) if show_path.exists() else {}
        props_path = project_dir / "props.json"
        props = read_json(props_path) if props_path.exists() else {"props": []}
    except Exception as exc:
        raise ProjectLoadError(project_dir, f"Project file is corrupt or unreadable: {exc}", exc) from exc

    try:
        schema_version = int(show.get("schema_version", show.get("version", 1)) or 1)
    except (TypeError, ValueError) as exc:
        raise ProjectLoadError(project_dir, "Project schema version is invalid.", exc) from exc
    if schema_version > PROJECT_SCHEMA_VERSION:
        raise ProjectLoadError(
            project_dir,
            f"Project schema v{schema_version} is newer than this app supports (v{PROJECT_SCHEMA_VERSION}).",
        )

    changed = False
    if (
        not isinstance(metadata, dict)
        or not isinstance(dots, dict)
        or not isinstance(props, dict)
        or not isinstance(sets, dict)
        or not isinstance(show, dict)
        or not isinstance(dots.get("dots", []), list)
        or not isinstance(props.get("props", []), list)
        or not isinstance(sets.get("sets", []), list)
    ):
        raise ProjectLoadError(project_dir, "Project JSON structure is invalid.")

    if not show_path.exists():
        show = {}
        changed = True
    if not props_path.exists():
        props = {"props": []}
        changed = True

    for key, default in (
        ("title", metadata.get("show_title", project_dir.name)),
        ("markers", []),
        ("constraints", []),
        ("audio_versions", []),
        ("timing_events", []),
    ):
        if key not in show:
            show[key] = default
            changed = True

    if show.get("schema_version") != PROJECT_SCHEMA_VERSION or show.get("version") != PROJECT_SCHEMA_VERSION:
        show["schema_version"] = PROJECT_SCHEMA_VERSION
        show["version"] = PROJECT_SCHEMA_VERSION
        changed = True

    for drill_set in sets.get("sets", []):
        if not isinstance(drill_set, dict):
            raise ProjectLoadError(project_dir, "Project sets file contains an invalid set entry.")
        for key, default in (
            ("dot_facings", {}),
            ("prop_positions", {}),
            ("path_anchors", {}),
            ("path_controls", {}),
            ("count_positions", {}),
            ("move_timings", {}),
            ("movement_styles", {}),
        ):
            if key not in drill_set:
                drill_set[key] = default
                changed = True
        if "transition" not in drill_set:
            drill_set["transition"] = "linear"
            changed = True

    if not sets.get("sets"):
        raise ProjectLoadError(project_dir, "Project has no sets.")

    if changed:
        create_project_backup(project_dir, reason="migration", min_interval_seconds=0)
        write_json(show_path, show)
        write_json(props_path, props if isinstance(props, dict) else {"props": []})
        write_json(project_dir / "sets.json", sets)


def create_project_backup(
    project_dir: Path,
    *,
    reason: str = "manual",
    min_interval_seconds: int = 0,
) -> Path | None:
    existing_files = [project_dir / name for name in PROJECT_JSON_FILES if (project_dir / name).exists()]
    if not existing_files:
        return None

    backups_dir = project_backup_dir(project_dir)
    backups_dir.mkdir(parents=True, exist_ok=True)
    if min_interval_seconds > 0:
        newest = newest_backup_mtime(backups_dir)
        if newest and time.time() - newest < min_interval_seconds:
            return None

    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    safe_reason = "".join(char for char in reason.lower().replace(" ", "_") if char.isalnum() or char in ("_", "-"))
    backup_path = backups_dir / f"{created_at}_{safe_reason or 'backup'}.zip"
    manifest = {
        "created_at": created_at,
        "reason": safe_reason or "backup",
        "schema_version": project_schema_version(project_dir),
        "project": project_dir.name,
        "files": [path.name for path in existing_files],
    }
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("backup_manifest.json", json.dumps(manifest, indent=2))
        for path in existing_files:
            archive.write(path, path.name)
    prune_project_backups(project_dir)
    return backup_path


def list_project_backups(project_dir: Path) -> list[ProjectBackup]:
    backups: list[ProjectBackup] = []
    backups_dir = project_backup_dir(project_dir)
    if not backups_dir.exists():
        return backups
    for path in sorted(backups_dir.glob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True):
        created_at = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        reason = "backup"
        schema_version = 0
        try:
            with zipfile.ZipFile(path) as archive:
                payload = json.loads(archive.read("backup_manifest.json").decode("utf-8"))
                created_at = str(payload.get("created_at", created_at)).replace("T", " ").replace("-0000", "")
                reason = str(payload.get("reason", reason))
                schema_version = int(payload.get("schema_version", 0) or 0)
        except Exception:
            pass
        backups.append(ProjectBackup(path=path, created_at=created_at, reason=reason, schema_version=schema_version))
    return backups


def restore_project_backup(project_dir: Path, backup_path: Path) -> None:
    if not backup_path.exists():
        raise ProjectLoadError(project_dir, "Selected backup file does not exist.")
    create_project_backup(project_dir, reason="pre_restore", min_interval_seconds=0)
    current_files = {
        file_name: (
            (project_dir / file_name).exists(),
            (project_dir / file_name).read_bytes() if (project_dir / file_name).exists() else b"",
        )
        for file_name in PROJECT_JSON_FILES
    }
    restored_files: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(backup_path) as archive:
            names = set(archive.namelist())
            missing = [file_name for file_name in REQUIRED_PROJECT_FILES if file_name not in names]
            if missing:
                raise ProjectLoadError(
                    project_dir,
                    f"Selected backup is missing required file(s): {', '.join(missing)}",
                )
            for file_name in PROJECT_JSON_FILES:
                if file_name in names:
                    data = archive.read(file_name)
                    validate_backup_json(project_dir, file_name, data)
                    restored_files[file_name] = data
        for file_name, data in restored_files.items():
            write_bytes_atomic(project_dir / file_name, data)
        migrate_project_files(project_dir)
    except Exception as exc:
        for file_name, (existed, data) in current_files.items():
            destination = project_dir / file_name
            try:
                if existed:
                    write_bytes_atomic(destination, data)
                elif destination.exists():
                    destination.unlink()
            except OSError:
                pass
        raise ProjectLoadError(project_dir, f"Could not restore backup: {exc}", exc) from exc


def validate_backup_json(project_dir: Path, file_name: str, data: bytes) -> None:
    try:
        payload = json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise ProjectLoadError(project_dir, f"Backup file '{file_name}' contains invalid JSON.", exc) from exc
    if not isinstance(payload, dict):
        raise ProjectLoadError(project_dir, f"Backup file '{file_name}' must contain a JSON object.")


def project_backup_dir(project_dir: Path) -> Path:
    return project_dir / BACKUP_DIR_NAME


def newest_backup_mtime(backups_dir: Path) -> float | None:
    newest = 0.0
    for path in backups_dir.glob("*.zip"):
        newest = max(newest, path.stat().st_mtime)
    return newest or None


def prune_project_backups(project_dir: Path, max_backups: int = MAX_PROJECT_BACKUPS) -> None:
    backups = sorted(project_backup_dir(project_dir).glob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True)
    for path in backups[max_backups:]:
        try:
            path.unlink()
        except OSError:
            pass


def project_schema_version(project_dir: Path) -> int:
    try:
        show = read_json(project_dir / "show.json")
    except Exception:
        return 0
    return int(show.get("schema_version", show.get("version", 1)) or 1)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp_path.replace(path)


def write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_bytes(data)
    temp_path.replace(path)


def safe_folder_name(title: str) -> str:
    safe = "".join(char for char in title.strip() if char.isalnum() or char in (" ", "-", "_"))
    return safe.strip().replace(" ", "_") or "Untitled_Show"


def parse_instrumentation_roster(text: str) -> list[InstrumentationEntry]:
    roster: list[InstrumentationEntry] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            name, count_text = line.split("=", 1)
        elif ":" in line:
            name, count_text = line.split(":", 1)
        else:
            parts = line.rsplit(maxsplit=1)
            if len(parts) != 2:
                continue
            name, count_text = parts
        try:
            count = int(count_text.strip())
        except ValueError:
            continue
        name = name.strip()
        if not name or count <= 0:
            continue
        if "|" in name:
            instrument, section = (part.strip() for part in name.split("|", 1))
            if instrument:
                roster.append((instrument, section, count))
        else:
            roster.append((name, count))
    return roster


def roster_count(instrumentation: list[InstrumentationEntry] | None) -> int:
    return sum(max(0, int(entry[-1])) for entry in instrumentation or [])


def default_dots(count: int = 30, instrumentation: list[InstrumentationEntry] | None = None) -> list[Dot]:
    roster: list[tuple[str, str, int]] = []
    for entry in instrumentation or []:
        if len(entry) == 2:
            instrument, amount = entry
            section = default_section_for_instrument(instrument)
        else:
            instrument, section, amount = entry
        if int(amount) > 0:
            roster.append((str(instrument).strip(), str(section).strip(), int(amount)))
    total_count = roster_count(roster) or count
    positions = optimized_starting_block(total_count)
    dots: list[Dot] = []
    if not roster:
        roster = [("Dot", "", total_count)]
    prefixes = unique_instrument_prefixes([name for name, _section, _amount in roster])
    instrument_numbers: dict[str, int] = {}
    dot_index = 0
    for instrument, section, amount in roster:
        prefix = prefixes[instrument]
        start_number = instrument_numbers.get(instrument, 0)
        for offset in range(1, amount + 1):
            if dot_index >= len(positions):
                break
            x, y = positions[dot_index]
            number = start_number + offset
            compact_name = f"{prefix}{number}"
            dots.append(
                Dot(
                    id=f"dot{dot_index + 1:03d}",
                    name=compact_name,
                    x=x,
                    y=y,
                    color="#e53935",
                    section=section,
                    instrument="" if instrument == "Dot" else instrument,
                    rank=compact_name,
                    layer="Main",
                )
            )
            dot_index += 1
        instrument_numbers[instrument] = start_number + amount
    return dots


def unique_instrument_prefixes(instruments: list[str]) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    used: set[str] = set()
    for instrument in instruments:
        base = preferred_instrument_prefix(instrument)
        prefix = base
        if prefix in used:
            compact = "".join(char for char in instrument.upper() if char.isalpha())
            for length in range(2, min(len(compact), 5) + 1):
                candidate = compact[:length]
                if candidate not in used:
                    prefix = candidate
                    break
            else:
                suffix = 2
                while f"{base}{suffix}" in used:
                    suffix += 1
                prefix = f"{base}{suffix}"
        prefixes[instrument] = prefix
        used.add(prefix)
    return prefixes


def preferred_instrument_prefix(instrument: str) -> str:
    normalized = " ".join(instrument.lower().replace("/", " ").replace("-", " ").split())
    if normalized in COMMON_INSTRUMENT_PREFIXES:
        return COMMON_INSTRUMENT_PREFIXES[normalized]
    words = [word for word in normalized.split() if word]
    if len(words) > 1:
        return "".join(word[0] for word in words[:3]).upper()
    compact = "".join(char for char in instrument.upper() if char.isalpha())
    if not compact:
        return "D"
    if compact == "DOT":
        return "D"
    return compact[:2] if len(compact) > 1 else compact[0]


def default_section_for_instrument(instrument: str) -> str:
    normalized = instrument.strip().lower()
    if not normalized or normalized == "dot":
        return ""
    if any(token in normalized for token in ("front ensemble", "pit", "marimba", "vibraphone", "xylophone", "synth")):
        return "Front Ensemble"
    if any(token in normalized for token in ("snare", "tenor", "quad", "bass drum", "cymbal")):
        return "Battery"
    if any(token in normalized for token in ("guard", "flag", "rifle", "sabre", "saber")):
        return "Guard"
    if any(token in normalized for token in ("trumpet", "mello", "horn", "trombone", "baritone", "euphonium", "tuba", "sousaphone")):
        return "Brass"
    if any(token in normalized for token in ("flute", "piccolo", "clarinet", "sax")):
        return "Woodwinds"
    return "Other"


def default_props(front_ensemble_count: int = 0, drum_major_stands: int = 0) -> list[Prop]:
    props: list[Prop] = []
    for index, x_position in enumerate(spread_positions(max(0, int(front_ensemble_count)), center_y=-31.5, spacing=7.0), start=1):
        props.append(
            Prop(
                id=f"prop_fe_{index:03d}",
                name=f"FE{index}",
                image_file="",
                x=x_position[0],
                y=x_position[1],
                width=5.0,
                height=2.4,
                layer="Front Ensemble",
            )
        )
    for index, x_position in enumerate(spread_positions(max(0, int(drum_major_stands)), center_y=-37.0, spacing=14.0), start=1):
        props.append(
            Prop(
                id=f"prop_dm_{index:03d}",
                name=f"DM Stand {index}",
                image_file="",
                x=x_position[0],
                y=x_position[1],
                width=3.0,
                height=3.0,
                layer="Drum Major",
            )
        )
    return props


def spread_positions(count: int, center_y: float, spacing: float) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    total_width = (count - 1) * spacing
    start_x = -total_width / 2
    return [(start_x + index * spacing, center_y) for index in range(count)]


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
