from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from drill_writer.core.animation import interpolate_dot_facings
from drill_writer.core.follow_leader import (
    FollowLeaderOptions,
    plan_follow_leader,
    split_follow_leader_groups,
)
from drill_writer.core.models import Dot, DrillProject, DrillSet, ProjectMetadata
from drill_writer.core.project_io import load_project, save_project


class FollowLeaderRouteTests(unittest.TestCase):
    def test_sharp_multi_turn_route_advances_every_marcher_one_spot(self) -> None:
        positions = {
            "a": (0.0, 0.0),
            "b": (4.0, 0.0),
            "c": (4.0, 4.0),
            "d": (8.0, 4.0),
            "e": (8.0, 0.0),
        }
        plan = plan_follow_leader(
            list(positions),
            positions,
            1,
            8,
            FollowLeaderOptions(
                topology="open",
                order_mode="roster",
                curved=False,
                advance_spots=1,
            ),
        )

        self.assertFalse(plan.route_closed)
        self.assertEqual(plan.ordered_ids, list(positions))
        for current_id, next_id in zip(plan.ordered_ids[:-1], plan.ordered_ids[1:]):
            self.assertPointAlmostEqual(plan.end_positions[current_id], positions[next_id])
        self.assertPointAlmostEqual(plan.end_positions["e"], (8.0, -4.0))
        self.assertGreater(len(plan.count_positions["a"]), 20)

    def test_closed_loop_wraps_without_crossing_the_form(self) -> None:
        positions = {
            "a": (0.0, 0.0),
            "b": (8.0, 0.0),
            "c": (8.0, 8.0),
            "d": (0.0, 8.0),
        }
        plan = plan_follow_leader(
            list(positions),
            positions,
            1,
            8,
            FollowLeaderOptions(topology="closed", order_mode="roster", curved=False),
        )

        self.assertTrue(plan.route_closed)
        self.assertPointAlmostEqual(plan.end_positions["a"], positions["b"])
        self.assertPointAlmostEqual(plan.end_positions["b"], positions["c"])
        self.assertPointAlmostEqual(plan.end_positions["c"], positions["d"])
        self.assertPointAlmostEqual(plan.end_positions["d"], positions["a"])

    def test_reverse_travel_uses_reverse_route_and_facing(self) -> None:
        positions = {"a": (0.0, 0.0), "b": (4.0, 0.0), "c": (8.0, 0.0)}
        plan = plan_follow_leader(
            list(positions),
            positions,
            1,
            8,
            FollowLeaderOptions(
                topology="open",
                order_mode="roster",
                curved=False,
                direction=-1,
                face_direction=True,
            ),
        )

        self.assertEqual(plan.leader_id, "a")
        self.assertPointAlmostEqual(plan.end_positions["b"], positions["a"])
        self.assertPointAlmostEqual(plan.end_positions["a"], (-4.0, 0.0))
        self.assertAlmostEqual(plan.count_facings["b"][4.0], 90.0, places=3)

    def test_direction_facing_turns_with_a_sharp_route(self) -> None:
        positions = {"a": (0.0, 0.0), "b": (4.0, 0.0), "c": (4.0, 4.0), "d": (8.0, 4.0)}
        plan = plan_follow_leader(
            list(positions),
            positions,
            1,
            8,
            FollowLeaderOptions(
                topology="open",
                order_mode="roster",
                curved=False,
                advance_spots=2,
                face_direction=True,
                samples_per_count=4,
            ),
        )

        facings = plan.count_facings["a"]
        self.assertAlmostEqual(facings[1.25], 270.0, places=3)
        self.assertTrue(any(abs(value - 180.0) < 0.001 for count, value in facings.items() if count > 4.5))
        self.assertAlmostEqual(plan.end_facings["a"], 270.0, places=3)

    def test_smooth_route_produces_continuous_sub_count_keys(self) -> None:
        positions = {
            "a": (-8.0, -4.0),
            "b": (-4.0, 2.0),
            "c": (0.0, -2.0),
            "d": (4.0, 3.0),
            "e": (8.0, 0.0),
        }
        plan = plan_follow_leader(
            list(positions),
            positions,
            1,
            8,
            FollowLeaderOptions(
                topology="open",
                order_mode="roster",
                curved=True,
                face_direction=True,
                samples_per_count=8,
            ),
        )

        self.assertGreater(len(plan.route), 90)
        self.assertGreater(len(plan.count_positions["c"]), 50)
        rounded_facings = {round(value, 1) for value in plan.count_facings["c"].values()}
        self.assertGreater(len(rounded_facings), 8)

    def test_group_modes_split_rows_and_sections(self) -> None:
        positions = {
            "t1": (0.0, 0.0),
            "t2": (4.0, 0.0),
            "m1": (0.0, 6.0),
            "m2": (4.0, 6.0),
        }
        rows = split_follow_leader_groups(list(positions), positions, "rows")
        sections = split_follow_leader_groups(
            list(positions),
            positions,
            "sections",
            {"t1": "Trumpets", "t2": "Trumpets", "m1": "Mellos", "m2": "Mellos"},
        )
        self.assertEqual([set(group) for group in rows], [{"t1", "t2"}, {"m1", "m2"}])
        self.assertEqual([set(group) for group in sections], [{"t1", "t2"}, {"m1", "m2"}])

    def assertPointAlmostEqual(self, first: tuple[float, float], second: tuple[float, float]) -> None:
        self.assertAlmostEqual(first[0], second[0], places=3)
        self.assertAlmostEqual(first[1], second[1], places=3)


class FollowLeaderFacingModelTests(unittest.TestCase):
    def test_count_facings_round_trip_and_drive_playback(self) -> None:
        drill_set = DrillSet(
            "Set 1",
            1,
            8,
            dot_positions={"a": (8.0, 0.0)},
            dot_facings={"a": 90.0},
            count_facings={"a": {1.0: 270.0, 4.0: 180.0, 8.0: 90.0}},
        )
        restored = DrillSet.from_json(drill_set.to_json())
        self.assertEqual(restored.count_facings, drill_set.count_facings)

        project = DrillProject(
            ProjectMetadata("Facing", 120, 8, "4/4"),
            dots=[Dot("a", "A", 0.0, 0.0)],
            sets=[restored],
        )
        project.ensure_set_positions()
        self.assertAlmostEqual(interpolate_dot_facings(project, 0, 1.0)["a"], 270.0)
        self.assertAlmostEqual(interpolate_dot_facings(project, 0, 2.5)["a"], 225.0)
        self.assertAlmostEqual(interpolate_dot_facings(project, 0, 8.0)["a"], 90.0)

    def test_count_facings_survive_project_save_and_load(self) -> None:
        project = DrillProject(
            ProjectMetadata("Saved Facing", 120, 8, "4/4"),
            dots=[Dot("a", "A", 0.0, 0.0)],
            sets=[
                DrillSet(
                    "Set 1",
                    1,
                    8,
                    dot_positions={"a": (8.0, 0.0)},
                    dot_facings={"a": 90.0},
                    count_facings={"a": {1.0: 270.0, 4.0: 180.0, 8.0: 90.0}},
                )
            ],
        )
        with tempfile.TemporaryDirectory() as temp:
            project_dir = Path(temp) / "project"
            save_project(project_dir, project, backup=False)
            restored = load_project(project_dir)
        self.assertEqual(restored.sets[0].count_facings, project.sets[0].count_facings)


if __name__ == "__main__":
    unittest.main()
