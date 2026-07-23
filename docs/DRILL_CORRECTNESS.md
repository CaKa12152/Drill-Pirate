# Drill Correctness and Safety Analysis

Drill Pirate evaluates transitions against the authored pictures, movement timing, performer-facing data, equipment, props, choreography, and performance surface. The analyzer is a design and rehearsal aid; directors remain responsible for validating the result with performers and staff.

## Fixed-Picture Conflict Explanations

Each path warning is classified as either **repairable** or **unavoidable with the fixed pictures**.

- A start-picture spacing conflict must be repaired in the previous/start picture.
- A destination-picture spacing conflict must be repaired by spreading or changing the destination picture. Swapping destination owners cannot change spacing between fixed form spots.
- A speed conflict is fixed-picture infeasible when even the straight-line distance exceeds the performer limit within the authored movement window.
- An intermediate spacing conflict is repairable when both endpoint pictures are safe. Destination ownership, timing, or path geometry can then be changed without altering the destination picture.
- A no-go conflict is fixed-picture infeasible when either endpoint lies inside the no-go region; otherwise the route can be repaired.

The Safety panel shows the classification in the warning row. Hover a warning for its explanation and suggested repair.

## Guided Destination Repair

Select two or more performers and open **Tools > Guided Destination Repair** or press `Ctrl+Alt+Shift+C`.

The dialog compares shortest-travel, rank-preserving, section-preserving, clockwise, counterclockwise, Follow-the-Leader, and lowest-collision assignments. Selecting a row previews the complete assignment on the field before the project changes.

Each option reports:

- Number of destination owners changed.
- Total and longest travel distance.
- Predicted synchronized spacing conflicts and path crossings.
- Speed-limit violations and minimum spacing.
- The exact performer-to-destination ownership changes.

Every option preserves the exact destination coordinate multiset. Applying a repair is one undoable operation.

## Bezier Path Validation

The full path analyzer validates manually edited marcher paths for:

- Missing endpoints or orphaned Bezier controls.
- Anchor/control-count mismatches.
- Non-finite coordinates and duplicate anchors.
- Oversized tangent handles and broken tangency.
- Self-intersections, excessive detours, abrupt reversals, and routes outside the performance surface.

Invalid path structure is reported before export. The writer should repair error-level findings; warning-level findings may be intentional but should be rehearsed and documented.

## Group Motion Ribbon Validation

Motion ribbons receive the same geometry checks plus validation for duplicate/missing performers, insufficient route nodes, planning failures, and generated performer compression. The validator samples the generated group plan and reports the count and pair at the worst interval.

## Biomechanical Model

Safety analysis resolves instrument profiles and performer overrides, then evaluates movement at sampled count positions.

- Facing-relative forward, backward, and lateral/crab speed.
- Body-facing rotation and travel-direction turn rate.
- Abrupt direction changes, including stricter turning while moving backward.
- `Normal`, `Half Time`, `Double Time`, `Jazz Run`, `At Halt`, and `Visual` movement styles.
- Continuity direction compared with actual movement and facing.
- Equipment mobility modifiers, toss travel, and equipment-change travel.
- Prop carry/push/rotate speed reduction, size-adjusted rotation limits, and suggested handler counts.
- Surface bounds and parade-route corridor limits.

The model intentionally uses conservative defaults. Performer-specific exceptions belong in Physical Limits only after staff and performer verification.

## Coordinate Standard

Football coordinates use 8-to-5 step language rounded to the nearest quarter step with deterministic half-up rounding.

- `x = 0` is the 50-yard line.
- Negative `x` is Side 1; positive `x` is Side 2.
- Exact goal lines print as `On G S1/S2`.
- Positions past a goal line print as steps `into end zone`.
- Front sideline/hash directions use `in front of` toward the audience and `behind` toward the back sideline.
- College and high-school hash locations come from the selected surface definition.
- Indoor/staging coordinates are measured from center line and center front/back.
- Parade coordinates use station distance along the authored route and signed left/right offset from route center.

Dot books, coordinate summaries, staff/section packets, and CSV export all call the same surface-aware formatter.

## Regression Gate

Run the focused drill-correctness suite:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_drill_correctness_p0 -v
```

The reference matrix covers fixed-picture conflicts, repair previews, malformed Bezier/ribbon geometry, biomechanical warnings, Side 1/Side 2, hashes, sidelines, yard lines, goal lines, end zones, indoor floors, parade routes, and coordinate CSV output.
