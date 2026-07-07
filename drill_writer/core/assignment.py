from __future__ import annotations

from drill_writer.core.animation import distance
from drill_writer.core.analysis import segments_intersect


def ordered_targets(
    starts: list[tuple[float, float]],
    targets: list[tuple[float, float]],
    *,
    allow_reverse: bool = True,
    allow_rotation: bool = False,
) -> list[tuple[float, float]]:
    if len(starts) != len(targets) or len(starts) <= 1:
        return list(targets)

    candidates: list[list[tuple[float, float]]] = []
    base = list(targets)
    if allow_rotation and len(base) > 2:
        for offset in range(len(base)):
            rotated = base[offset:] + base[:offset]
            candidates.append(rotated)
            if allow_reverse:
                candidates.append(list(reversed(rotated)))
    else:
        candidates.append(base)
        if allow_reverse:
            candidates.append(list(reversed(base)))

    return min(candidates, key=lambda candidate: ordered_assignment_cost(starts, candidate))


def ordered_assignment_cost(
    starts: list[tuple[float, float]],
    targets: list[tuple[float, float]],
) -> float:
    total = 0.0
    distances = [distance(start, target) for start, target in zip(starts, targets)]
    if not distances:
        return 0.0
    median = sorted(distances)[len(distances) // 2]
    outlier_threshold = max(8.0, median * 1.75)
    for move_distance in distances:
        total += move_distance * move_distance
        if move_distance > outlier_threshold:
            total += (move_distance - outlier_threshold) ** 2 * 8.0
    if len(starts) <= 220:
        for first in range(len(starts) - 1):
            for second in range(first + 1, len(starts)):
                if segments_intersect(starts[first], targets[first], starts[second], targets[second]):
                    total += 120.0
    return total


def greedy_nearest_assignment(
    starts: list[tuple[float, float]],
    targets: list[tuple[float, float]],
) -> list[int]:
    pairs: list[tuple[float, int, int]] = []
    for marcher_index, start in enumerate(starts):
        for target_index, target in enumerate(targets):
            move_distance = distance(start, target)
            pairs.append((move_distance * move_distance, marcher_index, target_index))
    pairs.sort(key=lambda item: item[0])

    assignment: list[int | None] = [None] * len(starts)
    used_marchers: set[int] = set()
    used_targets: set[int] = set()
    for _cost, marcher_index, target_index in pairs:
        if marcher_index in used_marchers or target_index in used_targets:
            continue
        assignment[marcher_index] = target_index
        used_marchers.add(marcher_index)
        used_targets.add(target_index)
        if len(used_marchers) == len(starts):
            break

    remaining_targets = [index for index in range(len(targets)) if index not in used_targets]
    for marcher_index, target_index in enumerate(assignment):
        if target_index is not None:
            continue
        best_target = min(
            remaining_targets,
            key=lambda index: distance(starts[marcher_index], targets[index]),
        )
        assignment[marcher_index] = best_target
        remaining_targets.remove(best_target)
    return [int(target_index) for target_index in assignment]
