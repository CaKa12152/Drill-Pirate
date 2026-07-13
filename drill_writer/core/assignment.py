from __future__ import annotations

from drill_writer.core.animation import distance
from drill_writer.core.analysis import segments_intersect


def minimum_cost_target_assignment(
    starts: list[tuple[float, float]],
    targets: list[tuple[float, float]],
) -> list[int]:
    if len(starts) != len(targets):
        raise ValueError("minimum_cost_target_assignment requires the same number of starts and targets.")
    count = len(starts)
    if count == 0:
        return []
    if count == 1:
        return [0]

    costs = [
        [assignment_distance_cost(start, target) for target in targets]
        for start in starts
    ]
    return hungarian_minimum_assignment(costs)


def assignment_distance_cost(start: tuple[float, float], target: tuple[float, float]) -> float:
    move_distance = distance(start, target)
    return move_distance * move_distance + move_distance * 0.05


def hungarian_minimum_assignment(costs: list[list[float]]) -> list[int]:
    rows = len(costs)
    columns = len(costs[0]) if costs else 0
    if rows == 0:
        return []
    if any(len(row) != columns for row in costs):
        raise ValueError("Cost matrix rows must have the same length.")
    if rows > columns:
        raise ValueError("Hungarian assignment requires rows <= columns.")

    potentials_rows = [0.0] * (rows + 1)
    potentials_columns = [0.0] * (columns + 1)
    matching = [0] * (columns + 1)
    previous_column = [0] * (columns + 1)

    for row in range(1, rows + 1):
        matching[0] = row
        column = 0
        min_values = [float("inf")] * (columns + 1)
        used = [False] * (columns + 1)
        while True:
            used[column] = True
            matched_row = matching[column]
            delta = float("inf")
            next_column = 0
            for candidate_column in range(1, columns + 1):
                if used[candidate_column]:
                    continue
                current = (
                    costs[matched_row - 1][candidate_column - 1]
                    - potentials_rows[matched_row]
                    - potentials_columns[candidate_column]
                )
                if current < min_values[candidate_column]:
                    min_values[candidate_column] = current
                    previous_column[candidate_column] = column
                if min_values[candidate_column] < delta:
                    delta = min_values[candidate_column]
                    next_column = candidate_column
            for candidate_column in range(columns + 1):
                if used[candidate_column]:
                    potentials_rows[matching[candidate_column]] += delta
                    potentials_columns[candidate_column] -= delta
                else:
                    min_values[candidate_column] -= delta
            column = next_column
            if matching[column] == 0:
                break
        while True:
            next_column = previous_column[column]
            matching[column] = matching[next_column]
            column = next_column
            if column == 0:
                break

    assignment = [-1] * rows
    for column in range(1, columns + 1):
        row = matching[column]
        if row:
            assignment[row - 1] = column - 1
    return assignment


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
