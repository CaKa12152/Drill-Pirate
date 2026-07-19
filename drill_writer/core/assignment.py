from __future__ import annotations

from dataclasses import dataclass
from heapq import nsmallest
from math import atan2, cos, pi, sin

from drill_writer.core.animation import distance
from drill_writer.core.analysis import segments_intersect


Point = tuple[float, float]
MotionWindow = tuple[float, float]
ObstacleTransition = tuple[Point, Point, MotionWindow]


@dataclass(slots=True)
class AssignmentQuality:
    total_distance: float = 0.0
    maximum_distance: float = 0.0
    collisions: int = 0
    crossings: int = 0
    speed_violations: int = 0
    spacing_deficit: float = 0.0
    speed_excess: float = 0.0
    minimum_spacing: float = float("inf")

    @property
    def weighted_score(self) -> float:
        return (
            self.collisions * 10_000_000.0
            + self.spacing_deficit * 1_000_000.0
            + self.speed_violations * 500_000.0
            + self.speed_excess * 80_000.0
            + self.crossings * 20_000.0
            + self.maximum_distance * self.maximum_distance * 8.0
            + self.total_distance
        )


def collision_aware_target_assignment(
    starts: list[Point],
    targets: list[Point],
    *,
    min_spacing: float = 1.25,
    motion_windows: list[MotionWindow] | None = None,
    move_durations: list[float] | None = None,
    max_yards_per_count: float = 4.0,
    transition: str = "linear",
    obstacles: list[ObstacleTransition] | None = None,
    initial_assignments: list[list[int]] | None = None,
) -> list[int]:
    if len(starts) != len(targets):
        raise ValueError("collision_aware_target_assignment requires the same number of starts and targets.")
    count = len(starts)
    if count <= 1:
        return list(range(count))

    windows = normalize_motion_windows(motion_windows, count)
    durations = normalize_move_durations(move_durations, count)
    obstacle_values = normalize_obstacles(obstacles)
    seeds: list[list[int]] = []

    def add_seed(seed: list[int]) -> None:
        if not valid_assignment(seed, count):
            return
        if seed not in seeds:
            seeds.append(list(seed))

    for seed in initial_assignments or []:
        add_seed(seed)
    if count <= 160:
        distance_seed = minimum_cost_target_assignment(starts, targets)
    elif count <= 700:
        distance_seed = epsilon_scaling_auction_assignment(starts, targets)
    else:
        distance_seed = greedy_nearest_assignment(starts, targets)
    add_seed(distance_seed)
    distance_quality = evaluate_assignment_quality(
        starts,
        targets,
        distance_seed,
        min_spacing=min_spacing,
        motion_windows=windows,
        move_durations=durations,
        max_yards_per_count=max_yards_per_count,
        obstacles=obstacle_values,
        transition=transition,
    )
    if distance_quality.collisions == 0 and distance_quality.speed_violations == 0:
        return distance_seed
    if count <= 80:
        add_seed(list(range(count)))
        add_seed(list(reversed(range(count))))
    projection_seeds = projection_assignment_seeds(starts, targets)
    if projection_seeds:
        if count <= 80:
            for seed in projection_seeds:
                add_seed(seed)
        else:
            add_seed(min(projection_seeds, key=lambda seed: assignment_travel_cost(starts, targets, seed)))
    for seed in angular_assignment_seeds(starts, targets):
        add_seed(seed)

    best = min(
        seeds,
        key=lambda assignment: evaluate_assignment_quality(
            starts,
            targets,
            assignment,
            min_spacing=min_spacing,
            motion_windows=windows,
            move_durations=durations,
            max_yards_per_count=max_yards_per_count,
            obstacles=obstacle_values,
            transition=transition,
        ).weighted_score,
    )
    return improve_collision_assignment(
        starts,
        targets,
        best,
        min_spacing=min_spacing,
        motion_windows=windows,
        move_durations=durations,
        max_yards_per_count=max_yards_per_count,
        obstacles=obstacle_values,
        transition=transition,
    )


def evaluate_assignment_quality(
    starts: list[Point],
    targets: list[Point],
    assignment: list[int],
    *,
    min_spacing: float = 1.25,
    motion_windows: list[MotionWindow] | None = None,
    move_durations: list[float] | None = None,
    max_yards_per_count: float = 4.0,
    obstacles: list[ObstacleTransition] | None = None,
    transition: str = "linear",
) -> AssignmentQuality:
    count = len(starts)
    if len(targets) != count or not valid_assignment(assignment, count):
        raise ValueError("Cannot score an invalid target assignment.")
    windows = normalize_motion_windows(motion_windows, count)
    durations = normalize_move_durations(move_durations, count)
    obstacle_values = normalize_obstacles(obstacles)
    quality = AssignmentQuality()
    assigned_targets = [targets[target_index] for target_index in assignment]

    for marcher_index, (start, target) in enumerate(zip(starts, assigned_targets)):
        move_distance = distance(start, target)
        quality.total_distance += move_distance
        quality.maximum_distance = max(quality.maximum_distance, move_distance)
        duration = max(0.0001, durations[marcher_index])
        speed = move_distance / duration
        if speed > max_yards_per_count:
            quality.speed_violations += 1
            quality.speed_excess += speed - max_yards_per_count

    for first in range(count - 1):
        for second in range(first + 1, count):
            closest, crossing = transition_pair_metrics(
                starts[first],
                assigned_targets[first],
                windows[first],
                starts[second],
                assigned_targets[second],
                windows[second],
                transition,
            )
            quality.minimum_spacing = min(quality.minimum_spacing, closest)
            if closest < min_spacing:
                quality.collisions += 1
                quality.spacing_deficit += min_spacing - closest
            if crossing:
                quality.crossings += 1

    for marcher_index, (start, target) in enumerate(zip(starts, assigned_targets)):
        for obstacle_start, obstacle_target, obstacle_window in obstacle_values:
            closest, crossing = transition_pair_metrics(
                start,
                target,
                windows[marcher_index],
                obstacle_start,
                obstacle_target,
                obstacle_window,
                transition,
            )
            quality.minimum_spacing = min(quality.minimum_spacing, closest)
            if closest < min_spacing:
                quality.collisions += 1
                quality.spacing_deficit += min_spacing - closest
            if crossing:
                quality.crossings += 1

    if quality.minimum_spacing == float("inf"):
        quality.minimum_spacing = 999.0
    return quality


def improve_collision_assignment(
    starts: list[Point],
    targets: list[Point],
    assignment: list[int],
    *,
    min_spacing: float,
    motion_windows: list[MotionWindow],
    move_durations: list[float],
    max_yards_per_count: float,
    obstacles: list[ObstacleTransition],
    transition: str,
) -> list[int]:
    improved = list(assignment)
    count = len(improved)
    starting_quality = evaluate_assignment_quality(
        starts,
        targets,
        improved,
        min_spacing=min_spacing,
        motion_windows=motion_windows,
        move_durations=move_durations,
        max_yards_per_count=max_yards_per_count,
        obstacles=obstacles,
        transition=transition,
    )
    if starting_quality.collisions == 0 and starting_quality.speed_violations == 0:
        return improved
    max_passes = 5 if count <= 100 else 3 if count <= 260 else 2
    for _pass in range(max_passes):
        candidates = assignment_swap_candidates(
            starts,
            targets,
            improved,
            motion_windows,
            min_spacing,
            transition,
        )
        changed = False
        for first, second in candidates:
            delta = assignment_swap_delta(
                starts,
                targets,
                improved,
                first,
                second,
                min_spacing,
                motion_windows,
                move_durations,
                max_yards_per_count,
                obstacles,
                transition,
            )
            if delta < -0.001:
                improved[first], improved[second] = improved[second], improved[first]
                changed = True
        if not changed:
            break
    return improved


def assignment_swap_candidates(
    starts: list[Point],
    targets: list[Point],
    assignment: list[int],
    motion_windows: list[MotionWindow],
    min_spacing: float,
    transition: str,
) -> list[tuple[int, int]]:
    count = len(assignment)
    if count <= 80:
        return [(first, second) for first in range(count - 1) for second in range(first + 1, count)]

    prioritized: list[tuple[float, int, int]] = []
    for first in range(count - 1):
        first_target = targets[assignment[first]]
        for second in range(first + 1, count):
            closest, crossing = transition_pair_metrics(
                starts[first],
                first_target,
                motion_windows[first],
                starts[second],
                targets[assignment[second]],
                motion_windows[second],
                transition,
            )
            if closest < min_spacing or crossing:
                priority = (min_spacing - min(closest, min_spacing)) * 10.0 + (1.0 if crossing else 0.0)
                prioritized.append((priority, first, second))
    prioritized.sort(reverse=True)
    candidate_pairs = {
        (min(first, second), max(first, second))
        for _priority, first, second in prioritized[: count * 2]
    }

    owner_by_target = {target_index: marcher_index for marcher_index, target_index in enumerate(assignment)}
    neighbor_count = 5 if count <= 260 else 3
    for marcher_index, start in enumerate(starts):
        nearest_targets = nsmallest(
            neighbor_count + 1,
            range(count),
            key=lambda target_index: assignment_distance_cost(start, targets[target_index]),
        )
        for target_index in nearest_targets:
            other = owner_by_target[target_index]
            if other != marcher_index:
                candidate_pairs.add((min(marcher_index, other), max(marcher_index, other)))

    return sorted(candidate_pairs)


def assignment_swap_delta(
    starts: list[Point],
    targets: list[Point],
    assignment: list[int],
    first: int,
    second: int,
    min_spacing: float,
    motion_windows: list[MotionWindow],
    move_durations: list[float],
    max_yards_per_count: float,
    obstacles: list[ObstacleTransition],
    transition: str,
) -> float:
    first_target = targets[assignment[first]]
    second_target = targets[assignment[second]]

    def pair_penalty(
        first_start: Point,
        first_end: Point,
        first_window: MotionWindow,
        second_start: Point,
        second_end: Point,
        second_window: MotionWindow,
    ) -> float:
        return pair_transition_penalty(
            first_start,
            first_end,
            first_window,
            second_start,
            second_end,
            second_window,
            min_spacing,
            transition,
        )

    delta = (
        marcher_transition_penalty(starts[first], second_target, move_durations[first], max_yards_per_count)
        + marcher_transition_penalty(starts[second], first_target, move_durations[second], max_yards_per_count)
        - marcher_transition_penalty(starts[first], first_target, move_durations[first], max_yards_per_count)
        - marcher_transition_penalty(starts[second], second_target, move_durations[second], max_yards_per_count)
    )
    delta += pair_penalty(
        starts[first], second_target, motion_windows[first], starts[second], first_target, motion_windows[second]
    ) - pair_penalty(
        starts[first], first_target, motion_windows[first], starts[second], second_target, motion_windows[second]
    )

    for other in range(len(assignment)):
        if other in {first, second}:
            continue
        other_target = targets[assignment[other]]
        delta += pair_penalty(
            starts[first], second_target, motion_windows[first], starts[other], other_target, motion_windows[other]
        ) - pair_penalty(
            starts[first], first_target, motion_windows[first], starts[other], other_target, motion_windows[other]
        )
        delta += pair_penalty(
            starts[second], first_target, motion_windows[second], starts[other], other_target, motion_windows[other]
        ) - pair_penalty(
            starts[second], second_target, motion_windows[second], starts[other], other_target, motion_windows[other]
        )

    for obstacle_start, obstacle_target, obstacle_window in obstacles:
        delta += pair_penalty(
            starts[first], second_target, motion_windows[first], obstacle_start, obstacle_target, obstacle_window
        ) - pair_penalty(
            starts[first], first_target, motion_windows[first], obstacle_start, obstacle_target, obstacle_window
        )
        delta += pair_penalty(
            starts[second], first_target, motion_windows[second], obstacle_start, obstacle_target, obstacle_window
        ) - pair_penalty(
            starts[second], second_target, motion_windows[second], obstacle_start, obstacle_target, obstacle_window
        )
    return delta


def marcher_transition_penalty(
    start: Point,
    target: Point,
    move_duration: float,
    max_yards_per_count: float,
) -> float:
    move_distance = distance(start, target)
    penalty = move_distance * move_distance + move_distance * 0.05
    speed = move_distance / max(0.0001, move_duration)
    if speed > max_yards_per_count:
        excess = speed - max_yards_per_count
        penalty += 500_000.0 + excess * 80_000.0 + excess * excess * 10_000.0
    return penalty


def pair_transition_penalty(
    first_start: Point,
    first_target: Point,
    first_window: MotionWindow,
    second_start: Point,
    second_target: Point,
    second_window: MotionWindow,
    min_spacing: float,
    transition: str,
) -> float:
    closest, crossing = transition_pair_metrics(
        first_start,
        first_target,
        first_window,
        second_start,
        second_target,
        second_window,
        transition,
    )
    penalty = 20_000.0 if crossing else 0.0
    if closest < min_spacing:
        deficit = min_spacing - closest
        penalty += 10_000_000.0 + deficit * 1_000_000.0
    return penalty


def transition_pair_metrics(
    first_start: Point,
    first_target: Point,
    first_window: MotionWindow,
    second_start: Point,
    second_target: Point,
    second_window: MotionWindow,
    transition: str = "linear",
) -> tuple[float, bool]:
    closest = minimum_synchronous_distance(
        first_start,
        first_target,
        first_window,
        second_start,
        second_target,
        second_window,
        transition,
    )
    crossing = segments_intersect(first_start, first_target, second_start, second_target)
    return closest, crossing


def minimum_synchronous_distance(
    first_start: Point,
    first_target: Point,
    first_window: MotionWindow,
    second_start: Point,
    second_target: Point,
    second_window: MotionWindow,
    transition: str = "linear",
) -> float:
    if transition != "linear" and first_window != second_window:
        return sampled_synchronous_distance(
            first_start,
            first_target,
            first_window,
            second_start,
            second_target,
            second_window,
            transition,
        )
    margin = 0.01
    breakpoints = {margin, 1.0 - margin}
    for value in (*first_window, *second_window):
        if margin < value < 1.0 - margin:
            breakpoints.add(value)
    ordered = sorted(breakpoints)
    closest = float("inf")
    for index in range(len(ordered) - 1):
        interval_start = ordered[index]
        interval_end = ordered[index + 1]
        first_at_start = transition_position(first_start, first_target, first_window, interval_start)
        first_at_end = transition_position(first_start, first_target, first_window, interval_end)
        second_at_start = transition_position(second_start, second_target, second_window, interval_start)
        second_at_end = transition_position(second_start, second_target, second_window, interval_end)
        relative_start = (
            first_at_start[0] - second_at_start[0],
            first_at_start[1] - second_at_start[1],
        )
        relative_delta = (
            (first_at_end[0] - second_at_end[0]) - relative_start[0],
            (first_at_end[1] - second_at_end[1]) - relative_start[1],
        )
        denominator = relative_delta[0] * relative_delta[0] + relative_delta[1] * relative_delta[1]
        local_progress = 0.0
        if denominator > 1e-12:
            local_progress = max(
                0.0,
                min(
                    1.0,
                    -(relative_start[0] * relative_delta[0] + relative_start[1] * relative_delta[1]) / denominator,
                ),
            )
        closest = min(
            closest,
            (
                (relative_start[0] + relative_delta[0] * local_progress) ** 2
                + (relative_start[1] + relative_delta[1] * local_progress) ** 2
            )
            ** 0.5,
        )
    return closest


def transition_position(start: Point, target: Point, window: MotionWindow, progress: float) -> Point:
    window_start, window_end = window
    if progress <= window_start:
        return start
    if progress >= window_end:
        return target
    local_progress = (progress - window_start) / max(0.0001, window_end - window_start)
    return (
        start[0] + (target[0] - start[0]) * local_progress,
        start[1] + (target[1] - start[1]) * local_progress,
    )


def sampled_synchronous_distance(
    first_start: Point,
    first_target: Point,
    first_window: MotionWindow,
    second_start: Point,
    second_target: Point,
    second_window: MotionWindow,
    transition: str,
) -> float:
    margin = 0.01
    sample_count = 48
    progress_values = {
        margin + (1.0 - margin * 2.0) * index / sample_count
        for index in range(sample_count + 1)
    }
    progress_values.update(
        value
        for value in (*first_window, *second_window)
        if margin <= value <= 1.0 - margin
    )
    closest = float("inf")
    for progress in sorted(progress_values):
        first_position = eased_transition_position(
            first_start,
            first_target,
            first_window,
            progress,
            transition,
        )
        second_position = eased_transition_position(
            second_start,
            second_target,
            second_window,
            progress,
            transition,
        )
        closest = min(closest, distance(first_position, second_position))
    return closest


def eased_transition_position(
    start: Point,
    target: Point,
    window: MotionWindow,
    progress: float,
    transition: str,
) -> Point:
    window_start, window_end = window
    if progress <= window_start:
        return start
    if progress >= window_end:
        return target
    local_progress = (progress - window_start) / max(0.0001, window_end - window_start)
    if transition == "ease_in_out":
        local_progress = 0.5 - 0.5 * cos(pi * local_progress)
    elif transition == "curved":
        local_progress = local_progress * local_progress * (3.0 - 2.0 * local_progress)
    return (
        start[0] + (target[0] - start[0]) * local_progress,
        start[1] + (target[1] - start[1]) * local_progress,
    )


def projection_assignment_seeds(starts: list[Point], targets: list[Point]) -> list[list[int]]:
    start_axis = principal_axis_angle(starts)
    target_axis = principal_axis_angle(targets)
    seeds: list[list[int]] = []
    for start_angle, target_angle in (
        (0.0, 0.0),
        (pi / 2, pi / 2),
        (pi / 4, pi / 4),
        (-pi / 4, -pi / 4),
        (start_axis, target_axis),
        (start_axis, target_axis + pi),
        (start_axis + pi, target_axis),
    ):
        start_order = projection_order(starts, start_angle)
        target_order = projection_order(targets, target_angle)
        assignment = [-1] * len(starts)
        for marcher_index, target_index in zip(start_order, target_order):
            assignment[marcher_index] = target_index
        seeds.append(assignment)
    return seeds


def angular_assignment_seeds(starts: list[Point], targets: list[Point]) -> list[list[int]]:
    if len(starts) < 3:
        return []
    start_center = center_of_points(starts)
    target_center = center_of_points(targets)
    start_order = sorted(
        range(len(starts)),
        key=lambda index: atan2(starts[index][1] - start_center[1], starts[index][0] - start_center[0]),
    )
    target_order = sorted(
        range(len(targets)),
        key=lambda index: atan2(targets[index][1] - target_center[1], targets[index][0] - target_center[0]),
    )
    seeds: list[list[int]] = []
    for ordered_targets in (target_order, list(reversed(target_order))):
        best_offset = min(
            range(len(targets)),
            key=lambda offset: sum(
                assignment_distance_cost(starts[marcher_index], targets[ordered_targets[(rank + offset) % len(targets)]])
                for rank, marcher_index in enumerate(start_order)
            ),
        )
        assignment = [-1] * len(starts)
        for rank, marcher_index in enumerate(start_order):
            assignment[marcher_index] = ordered_targets[(rank + best_offset) % len(targets)]
        seeds.append(assignment)
    return seeds


def projection_order(points: list[Point], angle: float) -> list[int]:
    axis_x, axis_y = cos(angle), sin(angle)
    perpendicular_x, perpendicular_y = -axis_y, axis_x
    return sorted(
        range(len(points)),
        key=lambda index: (
            points[index][0] * axis_x + points[index][1] * axis_y,
            points[index][0] * perpendicular_x + points[index][1] * perpendicular_y,
            index,
        ),
    )


def principal_axis_angle(points: list[Point]) -> float:
    center_x, center_y = center_of_points(points)
    covariance_xx = sum((x - center_x) ** 2 for x, _y in points)
    covariance_yy = sum((y - center_y) ** 2 for _x, y in points)
    covariance_xy = sum((x - center_x) * (y - center_y) for x, y in points)
    return 0.5 * atan2(2.0 * covariance_xy, covariance_xx - covariance_yy)


def center_of_points(points: list[Point]) -> Point:
    return (
        sum(point[0] for point in points) / max(1, len(points)),
        sum(point[1] for point in points) / max(1, len(points)),
    )


def normalize_motion_windows(values: list[MotionWindow] | None, count: int) -> list[MotionWindow]:
    if values is None or len(values) != count:
        return [(0.0, 1.0)] * count
    return [
        (max(0.0, min(float(start), 1.0)), max(max(0.0, min(float(start), 1.0)), min(float(end), 1.0)))
        for start, end in values
    ]


def normalize_move_durations(values: list[float] | None, count: int) -> list[float]:
    if values is None or len(values) != count:
        return [float("inf")] * count
    return [max(0.0001, float(value)) for value in values]


def normalize_obstacles(values: list[ObstacleTransition] | None) -> list[ObstacleTransition]:
    return [
        (start, target, normalize_motion_windows([window], 1)[0])
        for start, target, window in (values or [])
    ]


def valid_assignment(assignment: list[int], count: int) -> bool:
    return len(assignment) == count and sorted(assignment) == list(range(count))


def assignment_travel_cost(starts: list[Point], targets: list[Point], assignment: list[int]) -> float:
    return sum(
        assignment_distance_cost(start, targets[assignment[index]])
        for index, start in enumerate(starts)
    )


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


def epsilon_scaling_auction_assignment(
    starts: list[Point],
    targets: list[Point],
) -> list[int]:
    if len(starts) != len(targets):
        raise ValueError("epsilon_scaling_auction_assignment requires equal start and target counts.")
    count = len(starts)
    if count <= 1:
        return list(range(count))
    costs = [
        [assignment_distance_cost(start, target) for target in targets]
        for start in starts
    ]
    maximum_cost = max(max(row) for row in costs)
    epsilon = max(1.0, maximum_cost / 4.0)
    final_epsilon = 1.0 / (count + 1)
    prices = [0.0] * count
    assignment: list[int | None] = [None] * count

    while epsilon > final_epsilon:
        owners: list[int | None] = [None] * count
        assignment = [None] * count
        unassigned = list(range(count))
        iterations = 0
        max_iterations = max(10_000, count * count * 20)
        while unassigned and iterations < max_iterations:
            iterations += 1
            marcher_index = unassigned.pop()
            best_target = 0
            best_value = float("-inf")
            second_value = float("-inf")
            for target_index, target_cost in enumerate(costs[marcher_index]):
                value = -target_cost - prices[target_index]
                if value > best_value:
                    second_value = best_value
                    best_value = value
                    best_target = target_index
                elif value > second_value:
                    second_value = value
            prices[best_target] += best_value - second_value + epsilon
            previous_owner = owners[best_target]
            owners[best_target] = marcher_index
            assignment[marcher_index] = best_target
            if previous_owner is not None:
                assignment[previous_owner] = None
                unassigned.append(previous_owner)
        if unassigned:
            return greedy_nearest_assignment(starts, targets)
        epsilon /= 5.0

    return [int(target_index) for target_index in assignment if target_index is not None]


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
