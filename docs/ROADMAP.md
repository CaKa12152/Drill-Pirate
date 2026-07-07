# Roadmap and Production-Readiness Notes

Drill Pirate is an alpha application. It has a working editing/export foundation, but commercial drill-writing software needs more depth in several areas.

## Highest Priority

### Collision Avoidance

Current state:

- Path analysis warns about close spacing, crossing paths, high travel speed, and sampled conflict timeline counts.
- Auto-plan selected paths can add basic route anchors.

Production target:

- Whole-section collision prediction.
- Minimum-spacing constraints across full transitions.
- Better crossing-path resolution.
- Speed and stride-length warnings.
- Automated rerouting with user approval.

### Intelligent Path Planning

Current state:

- Ordered formation tools preserve performer order and closed forms rotate/reverse targets to reduce travel.
- Users can add anchors and Bezier handles.
- Follow-leader conveyor supports ordered outline movement.

Production target:

- Assignment optimization that minimizes total travel and avoids role swaps.
- Multi-agent route planning.
- Preserve form intervals during transitions.
- Avoid velocity spikes.
- Let the user choose between shortest path, section-preserving path, and follow-leader path.

### Playback Reliability

Current state:

- Audio-backed playback, waveform scrubbing, timing-map anchors, and markers exist.

Production target:

- More robust audio device recovery.
- Higher-confidence frame scheduling under heavy load.
- Better diagnostics for dropped frames.
- Optional render cache for complex shows.

## Drill-Writing Depth

### Per-Count Editing

Current state:

- Count keyframes can store per-count positions.

Production target:

- Full per-count editor with clearer graph/timeline visualization.
- Per-count prop states.
- Better continuity editing.
- Velocity graph and easing editor.

### Constraint Solving

Current state:

- Line, pivot, arc, and block constraints exist and apply during movement.

Production target:

- Real constraint solver.
- Keep selected marchers in a line/arc/grid during edits.
- Pivot constraints.
- Maintain fixed interval while scaling/rotating.
- Constraints visible and editable in the UI.

### Formation Library

Current state:

- Lines, curves, arcs, circles, rectangles, spirals, blocks, scatter, mirror, SVG shapes, plugin tools.

Production target:

- More built-in common drill forms.
- Letters and symbols.
- Better SVG cleanup and corner spacing.
- Custom shape library.
- Reusable formation presets.

## Music and Rehearsal

### Audio Synchronization

Current state:

- Timing anchors, tempo events, ritardandos, fermatas, pickup offsets, waveform, markers, multiple audio versions.

Production target:

- Beat-grid editor.
- Measure-number lane.
- Tempo map visualization.
- Better automatic beat/hit detection.
- Multiple synchronized audio stems.

### Rehearsal Tools

Current state:

- Loop current set, count finder, movement styles, markers.

Production target:

- Section-only playback.
- Performer lookup mode.
- Slow-motion presets.
- Repeat count ranges.
- Rehearsal notes by set and section.
- Mobile-friendly performer charts.

## Printing and Export

Current state:

- MP4, project ZIP, drill sheet PDF, dot book PDF, staff packet PDF, coordinate CSV.

Production target:

- Fully customizable dot-book templates.
- Section-only packets.
- Instructor packets with notes and warnings.
- Continuity sheets.
- Performer coordinate summaries.
- Print preview.
- Batch export profiles.

## Plugin Ecosystem

Current state:

- Trusted folder plugins.
- Python runtime bundled in the EXE.
- Plugins can add UI, commands, styles, and custom form tools.

Production target:

- Versioned plugin API.
- Plugin compatibility warnings.
- Safer plugin permissions.
- Plugin signing or trust prompts.
- Example plugin gallery.
- Better developer diagnostics.

## Distribution and Operations

Current state:

- PyInstaller Windows build.
- GitHub release updater.
- Release-log popup.

Production target:

- Signed installer.
- Auto-update rollback.
- Crash reporting.
- Portable and installer builds.
- macOS package.
- Automated release CI.
- Regression test suite.

## Commercial-Use Bar

Before calling Drill Pirate commercially production-ready, the project should have:

- Strong automated test coverage for project save/load.
- Robust collision/path assignment validation.
- Reliable playback on large shows.
- Signed Windows installer.
- Crash reports or diagnostic bundles.
- Clear license file.
- Formal support/reporting process.
- Backward-compatible project migration tests.
- User documentation kept in sync with releases.
