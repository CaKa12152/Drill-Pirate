from __future__ import annotations

from bisect import bisect_left

from drill_writer.core.models import AudioVersion, DrillProject, TimingEvent


def active_audio_version(project: DrillProject) -> AudioVersion | None:
    for audio in project.audio_versions:
        if audio.active and audio.audio_file:
            return audio
    return next((audio for audio in project.audio_versions if audio.audio_file), None)


def set_active_audio_version(project: DrillProject, audio_file: str) -> None:
    for audio in project.audio_versions:
        audio.active = audio.audio_file == audio_file
    project.metadata.audio_file = audio_file


def show_start_count(project: DrillProject) -> float:
    return float(project.sets[0].start_count) if project.sets else 1.0


def show_end_count(project: DrillProject) -> float:
    return float(project.sets[-1].end_count) if project.sets else 1.0


def playback_bounds_for_set(project: DrillProject, set_index: int) -> tuple[float, float]:
    if not project.sets:
        return (1.0, 1.0)
    index = max(0, min(set_index, len(project.sets) - 1))
    drill_set = project.sets[index]
    start = float(drill_set.start_count)
    end = float(drill_set.end_count)
    if index + 1 < len(project.sets):
        next_start = float(project.sets[index + 1].start_count)
        if next_start > start:
            end = max(end, next_start)
    return start, end


def set_index_for_count(project: DrillProject, count: float) -> int:
    if not project.sets:
        return 0
    for index, drill_set in enumerate(project.sets[:-1]):
        next_start = float(project.sets[index + 1].start_count)
        if count < next_start:
            return index
    for index, drill_set in enumerate(project.sets):
        if drill_set.start_count <= count <= drill_set.end_count:
            return index
    return max(0, len(project.sets) - 1)


def set_count_for_audio_ms(project: DrillProject, milliseconds: int) -> tuple[int, float]:
    count = audio_ms_to_count(project, float(milliseconds))
    set_index = set_index_for_count(project, count)
    start, end = playback_bounds_for_set(project, set_index)
    return set_index, max(start, min(count, end))


def audio_ms_for_set_count(project: DrillProject, set_index: int, count: float) -> int:
    if not project.sets:
        return 0
    start, end = playback_bounds_for_set(project, set_index)
    clamped_count = max(start, min(count, end))
    return int(count_to_audio_ms(project, clamped_count))


def timing_anchors(project: DrillProject) -> list[tuple[float, float]]:
    anchors = [
        (event.count, event.milliseconds)
        for event in project.timing_events
        if event.event_type == "anchor"
    ]
    return sorted(anchors)


def count_to_audio_ms(project: DrillProject, count: float) -> float:
    anchors = timing_anchors(project)
    if len(anchors) >= 2:
        return anchored_count_to_ms(project, count, anchors)
    if len(anchors) == 1:
        anchor_count, anchor_ms = anchors[0]
        return fallback_count_to_ms(project, count) + anchor_ms - fallback_count_to_ms(project, anchor_count)
    return fallback_count_to_ms(project, count)


def audio_ms_to_count(project: DrillProject, milliseconds: float) -> float:
    anchors = timing_anchors(project)
    if len(anchors) >= 2:
        return anchored_ms_to_count(project, milliseconds, anchors)
    start = show_start_count(project)
    end = show_end_count(project)
    low = min(start, end)
    high = max(start, end)
    for _ in range(40):
        midpoint = (low + high) / 2
        if count_to_audio_ms(project, midpoint) < milliseconds:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2


def anchored_count_to_ms(
    project: DrillProject,
    count: float,
    anchors: list[tuple[float, float]],
) -> float:
    counts = [anchor[0] for anchor in anchors]
    index = bisect_left(counts, count)
    if index <= 0:
        count_a, ms_a = anchors[0]
        slope = local_ms_per_count(project, count_a)
        return ms_a + (count - count_a) * slope
    if index >= len(anchors):
        count_a, ms_a = anchors[-1]
        slope = local_ms_per_count(project, count_a)
        return ms_a + (count - count_a) * slope

    count_a, ms_a = anchors[index - 1]
    count_b, ms_b = anchors[index]
    progress = (count - count_a) / max(0.0001, count_b - count_a)
    return ms_a + (ms_b - ms_a) * progress


def anchored_ms_to_count(
    project: DrillProject,
    milliseconds: float,
    anchors: list[tuple[float, float]],
) -> float:
    anchors_by_time = sorted(anchors, key=lambda item: item[1])
    times = [anchor[1] for anchor in anchors_by_time]
    index = bisect_left(times, milliseconds)
    if index <= 0:
        count_a, ms_a = anchors_by_time[0]
        return count_a + (milliseconds - ms_a) / local_ms_per_count(project, count_a)
    if index >= len(anchors_by_time):
        count_a, ms_a = anchors_by_time[-1]
        return count_a + (milliseconds - ms_a) / local_ms_per_count(project, count_a)

    count_a, ms_a = anchors_by_time[index - 1]
    count_b, ms_b = anchors_by_time[index]
    progress = (milliseconds - ms_a) / max(0.0001, ms_b - ms_a)
    return count_a + (count_b - count_a) * progress


def fallback_count_to_ms(project: DrillProject, count: float) -> float:
    start = show_start_count(project)
    target = max(start, min(count, show_end_count(project)))
    milliseconds = pickup_offset_ms(project)
    current = start
    boundaries = sorted(
        {
            start,
            target,
            *[float(drill_set.start_count) for drill_set in project.sets],
            *[float(drill_set.end_count) for drill_set in project.sets],
            *[event.count for event in project.timing_events if event.count >= start],
            *[
                event.end_count
                for event in project.timing_events
                if event.event_type == "ritard" and event.end_count > event.count
            ],
        }
    )
    for boundary in boundaries:
        if boundary <= current:
            continue
        segment_end = min(boundary, target)
        if segment_end <= current:
            continue
        midpoint = (current + segment_end) / 2
        milliseconds += (segment_end - current) * local_ms_per_count(project, midpoint)
        current = segment_end
        if current >= target:
            break

    for event in project.timing_events:
        if event.event_type == "fermata" and start < event.count <= target:
            milliseconds += max(0, event.milliseconds)
    return milliseconds


def local_ms_per_count(project: DrillProject, count: float) -> float:
    tempo = local_tempo(project, count)
    return 60000 / max(1.0, tempo)


def local_tempo(project: DrillProject, count: float) -> float:
    set_index = set_index_for_count(project, count)
    tempo = project.active_tempo(set_index)
    for event in sorted(project.timing_events, key=lambda item: item.count):
        if event.event_type == "tempo" and event.count <= count and event.tempo > 0:
            tempo = event.tempo
        elif (
            event.event_type == "ritard"
            and event.count <= count <= event.end_count
            and event.tempo > 0
            and event.end_tempo > 0
        ):
            progress = (count - event.count) / max(0.0001, event.end_count - event.count)
            tempo = event.tempo + (event.end_tempo - event.tempo) * progress
    return tempo


def pickup_offset_ms(project: DrillProject) -> float:
    return sum(
        event.milliseconds
        for event in project.timing_events
        if event.event_type == "pickup"
    )


def describe_timing_event(event: TimingEvent) -> str:
    if event.event_type == "anchor":
        return f"Anchor count {event.count:g} -> {event.milliseconds / 1000:.2f}s"
    if event.event_type == "tempo":
        return f"Tempo {event.tempo:g} BPM at count {event.count:g}"
    if event.event_type == "ritard":
        return (
            f"Ritard {event.tempo:g}->{event.end_tempo:g} BPM, "
            f"counts {event.count:g}-{event.end_count:g}"
        )
    if event.event_type == "fermata":
        return f"Fermata {event.milliseconds / 1000:.2f}s at count {event.count:g}"
    if event.event_type == "pickup":
        return f"Pickup offset {event.milliseconds / 1000:.2f}s"
    return f"{event.event_type} at count {event.count:g}"
