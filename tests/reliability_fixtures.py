from __future__ import annotations

from math import cos, pi, sin

from drill_writer.core.models import (
    ChoreographyEvent,
    ContinuityInstruction,
    Dot,
    DrillProject,
    DrillSet,
    Marker,
    MotionRibbon,
    MovementStyle,
    ProjectMetadata,
    Prop,
    PropAttachment,
    SurfaceDefinition,
    TimingEvent,
    Transition,
)


def grid_positions(count: int, *, spacing: float = 1.6) -> list[tuple[float, float]]:
    columns = max(1, int(count**0.5 + 0.999))
    rows = max(1, (count + columns - 1) // columns)
    return [
        (
            (index % columns - (columns - 1) / 2) * spacing,
            (index // columns - (rows - 1) / 2) * spacing,
        )
        for index in range(count)
    ]


def performer_dots(count: int, *, guard_count: int = 0) -> list[Dot]:
    positions = grid_positions(count)
    dots: list[Dot] = []
    for index, (x, y) in enumerate(positions):
        is_guard = index >= count - guard_count
        prefix = "G" if is_guard else "T"
        number = index - (count - guard_count) + 1 if is_guard else index + 1
        dots.append(
            Dot(
                id=f"{prefix}{number}",
                name=f"{'Guard' if is_guard else 'Trumpet'} {number}",
                x=x,
                y=y,
                color="#7c3aed" if is_guard else "#e53935",
                section="Guard" if is_guard else "Trumpets",
                instrument="Flag" if is_guard else "Trumpet",
                equipment="Flag" if is_guard else "",
                layer="Guard" if is_guard else "Winds",
            )
        )
    return dots


def project_from_positions(
    title: str,
    dots: list[Dot],
    set_positions: list[dict[str, tuple[float, float]]],
    *,
    counts_per_set: int = 16,
) -> DrillProject:
    sets: list[DrillSet] = []
    for index, positions in enumerate(set_positions):
        start = 1 + index * counts_per_set
        sets.append(
            DrillSet(
                name=f"Set {index + 1}",
                start_count=start,
                end_count=start + counts_per_set - 1,
                dot_positions=positions,
                transition=Transition.LINEAR,
            )
        )
    project = DrillProject(
        metadata=ProjectMetadata(title, 152, counts_per_set, "4/4"),
        dots=dots,
        sets=sets,
    )
    project.ensure_set_positions()
    return project


def playback_project(count: int) -> DrillProject:
    dots = performer_dots(count, guard_count=max(0, count // 10))
    start = {dot.id: (dot.x, dot.y) for dot in dots}
    wave = {
        dot.id: (
            dot.x * 1.18,
            dot.y + sin((index / max(1, count - 1)) * pi * 4.0) * 5.0,
        )
        for index, dot in enumerate(dots)
    }
    arc = {
        dot.id: (
            -44.0 + 88.0 * index / max(1, count - 1),
            -2.0 + 12.0 * sin(pi * index / max(1, count - 1)),
        )
        for index, dot in enumerate(dots)
    }
    project = project_from_positions(f"Playback Soak {count}", dots, [start, wave, arc])
    project.timing_events = [
        TimingEvent("anchor", 1, milliseconds=0, label="Start"),
        TimingEvent("tempo", 17, tempo=168, label="Push"),
        TimingEvent("ritardando", 33, tempo=168, end_count=48, end_tempo=132, label="Release"),
    ]
    project.markers = [Marker(17, "Phrase 2"), Marker(33, "Impact")]
    for index, dot in enumerate(dots):
        if index % 11 == 0:
            project.sets[1].path_anchors[dot.id] = [
                ((start[dot.id][0] + wave[dot.id][0]) / 2, start[dot.id][1] + 3.0)
            ]
        if index % 7 == 0:
            project.sets[2].move_timings[dot.id] = {"start": 37.0, "end": 48.0}
        if index % 5 == 0:
            project.sets[2].movement_styles[dot.id] = MovementStyle.JAZZ_RUN
    return project


def large_svg_project() -> DrillProject:
    count = 320
    dots = performer_dots(count)
    start = {dot.id: (dot.x, dot.y) for dot in dots}
    infinity: dict[str, tuple[float, float]] = {}
    for index, dot in enumerate(dots):
        angle = 2.0 * pi * index / count
        denominator = 1.0 + sin(angle) ** 2
        infinity[dot.id] = (
            38.0 * cos(angle) / denominator,
            20.0 * sin(angle) * cos(angle) / denominator + (0.38 if angle < pi else -0.38),
        )
    project = project_from_positions("Fixture - Large SVG Infinity", dots, [start, infinity])
    project.workflow["regression_fixture"] = "large_svg"
    project.workflow["source_svg"] = "infinity.svg"
    return project


def follow_leader_project() -> DrillProject:
    dots = performer_dots(48)
    start = {dot.id: (dot.x - 18.0, -12.0) for dot in dots}
    end = {
        dot.id: (
            -42.0 + 84.0 * index / max(1, len(dots) - 1),
            8.0 * sin(index / max(1, len(dots) - 1) * pi * 3.0),
        )
        for index, dot in enumerate(dots)
    }
    project = project_from_positions("Fixture - Follow the Leader", dots, [start, end])
    dot_ids = [dot.id for dot in dots]
    project.sets[1].motion_ribbons = [
        MotionRibbon(
            id="leader-ribbon",
            name="Three-Turn Ribbon",
            dot_ids=dot_ids,
            nodes=[
                {"point": (-42.0, 0.0), "out": (-30.0, -12.0)},
                {"point": (-10.0, 8.0), "in": (-20.0, 16.0), "out": (0.0, 0.0)},
                {"point": (15.0, -7.0), "in": (5.0, -14.0), "out": (26.0, 0.0)},
                {"point": (42.0, 4.0), "in": (34.0, 12.0)},
            ],
            orient_to_path=True,
            face_direction=True,
        )
    ]
    project.sets[1].continuity = [
        ContinuityInstruction(
            id="follow-continuity",
            dot_ids=dot_ids,
            start_count=17,
            end_count=32,
            step_size="8-to-5",
            direction="follow_the_leader",
            text="Follow the ribbon and face direction of travel.",
        )
    ]
    project.workflow["regression_fixture"] = "follow_leader"
    return project


def props_project() -> DrillProject:
    dots = performer_dots(24)
    start = {dot.id: (dot.x, dot.y) for dot in dots}
    end = {dot.id: (dot.x + 10.0, dot.y + sin(index) * 2.0) for index, dot in enumerate(dots)}
    project = project_from_positions("Fixture - Moving Props", dots, [start, end])
    project.props = [Prop("window", "Window Wall", "", -12.0, -8.0, 20.0, 6.0, 0.0)]
    project.ensure_set_positions()
    project.sets[0].prop_positions["window"] = {"x": -12.0, "y": -8.0, "width": 20.0, "height": 6.0, "rotation": 0.0}
    project.sets[1].prop_positions["window"] = {"x": 14.0, "y": 6.0, "width": 20.0, "height": 6.0, "rotation": 90.0}
    project.prop_attachments = [
        PropAttachment(
            id="window-carry",
            name="Window Carry",
            prop_id="window",
            dot_ids=[dots[0].id, dots[1].id],
            start_count=17,
            end_count=32,
            mode="carry",
            leader_dot_id=dots[0].id,
            offset_y=-2.0,
            rotation_behavior="direction_of_travel",
        )
    ]
    project.workflow["regression_fixture"] = "props"
    return project


def choreography_project() -> DrillProject:
    dots = performer_dots(40, guard_count=16)
    positions = {dot.id: (dot.x, dot.y) for dot in dots}
    project = project_from_positions("Fixture - Guard Choreography", dots, [positions, positions])
    guard_ids = [dot.id for dot in dots if dot.section == "Guard"]
    project.choreography = [
        ChoreographyEvent("flag-change", "Flag to Rifle", "equipment_change", guard_ids, 17, 20, "Flag", "Rifle"),
        ChoreographyEvent("rifle-toss", "Five Toss", "toss", guard_ids[::2], 25, 28, "Rifle", "Rifle", 5.0, 4.5),
        ChoreographyEvent("dance", "Body Phrase", "visual", guard_ids[1::2], 29, 32, notes="Low release into turn."),
    ]
    project.workflow["regression_fixture"] = "choreography"
    return project


def tempo_map_project() -> DrillProject:
    dots = performer_dots(12)
    positions = {dot.id: (dot.x, dot.y) for dot in dots}
    project = project_from_positions("Fixture - Tempo Map", dots, [positions, positions, positions], counts_per_set=8)
    project.timing_events = [
        TimingEvent("anchor", 1, milliseconds=500, label="Pickup"),
        TimingEvent("tempo", 1, tempo=144, label="Opening"),
        TimingEvent("ritardando", 9, tempo=144, end_count=16, end_tempo=96, label="Ritard"),
        TimingEvent("fermata", 17, milliseconds=1500, label="Hold"),
        TimingEvent("tempo", 18, tempo=172, label="New Tempo"),
    ]
    project.workflow["pickup_counts"] = 1
    project.workflow["regression_fixture"] = "tempo_map"
    return project


def custom_surface_project() -> DrillProject:
    dots = performer_dots(30)
    positions = {dot.id: (dot.x * 0.6, dot.y * 0.6) for dot in dots}
    project = project_from_positions("Fixture - Indoor Floor", dots, [positions, positions])
    project.surface = SurfaceDefinition(
        name="WGI Floor 90 x 60",
        surface_type="indoor",
        width_yards=30.0,
        height_yards=20.0,
        hash_style="none",
        front_hash_yards=-4.0,
        back_hash_yards=4.0,
        endzone_depth_yards=0.0,
        grid_spacing_yards=0.5,
        background_color="#1b1c2a",
        line_color="#d5d7ff",
        show_yard_numbers=False,
        show_end_zones=False,
    )
    project.workflow["regression_fixture"] = "custom_surface"
    return project


def regression_projects() -> dict[str, DrillProject]:
    return {
        "large_svg": large_svg_project(),
        "follow_leader": follow_leader_project(),
        "props": props_project(),
        "choreography": choreography_project(),
        "tempo_map": tempo_map_project(),
        "custom_surface": custom_surface_project(),
    }


def export_project() -> DrillProject:
    dots = performer_dots(6, guard_count=2)
    start = {dot.id: (dot.x, dot.y) for dot in dots}
    end = {dot.id: (dot.x + 4.0, dot.y + index * 0.35) for index, dot in enumerate(dots)}
    project = project_from_positions("Fixture - Deterministic Exports", dots, [start, end], counts_per_set=8)
    project.markers = [Marker(9, "Impact")]
    return project
