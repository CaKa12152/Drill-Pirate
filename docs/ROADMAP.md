# Drill Pirate Roadmap

Drill Pirate is currently **Alpha v2.8.0**. It supports complete show creation, advanced formation design, synchronized playback, specialized performance tracking, customizable printing, video export, plugins, project recovery, and in-app updates. The remaining roadmap focuses on real-world validation, collaboration, accessibility, distribution, and release operations rather than adding disconnected tools.

## Current Product Baseline

### Design and Motion

- Set-based and per-count performer movement with editable movement windows.
- Lines, curves, arcs, circles, blocks, polygons, stars, spirals, scatter forms, SVG forms, and plugin-provided forms.
- Unified transform controls, rotation, scaling, warping, mirroring, arrays, parallel forms, rank/file generation, and live symmetry.
- Group Motion Ribbons, shared path handles, Formation Morph, and a CAD path toolkit.
- Follow the Leader across open paths, closed forms, corners, curves, and complex outlines, with optional direction-of-travel facing.
- Global destination assignment that preserves the target formation while minimizing travel, spacing conflicts, crossings, and unnecessary performer swaps.
- Collision, crossing-path, travel-speed, stride, and performer-limit analysis with timeline warnings.
- Constraints for lines, arcs, blocks, pivots, intervals, sections, and neighboring relationships.
- Construction guides, measurement overlays, annotations, no-go regions, and reference layers.

### Music and Show Planning

- Audio-clock playback, waveform scrubbing, hit markers, tempo events, ritardandos, fermatas, pickup offsets, and multiple audio versions.
- MusicXML and MIDI import with measures, tempos, and rehearsal marks.
- Phrase-based set generation, automated set suggestions, and transition planning.
- Storyboard planning for movements, scenes, production notes, and visual pacing.
- Continuity instructions, movement style, facing, horn direction, choreography, and equipment events by count range.
- Director's Notes attached to each set for visual intent, production cues, and staff drill-book pages.

### Specialized Production

- Configurable football fields, high-school and college hashes, indoor floors, parade routes, and custom staging surfaces.
- Guard equipment and choreography tracks, including tosses and equipment changes.
- Movable props, performer attachments, carrying/pushing/rotation behavior, and a layered real-yard Prop Studio with field-scale preview.
- Front ensemble and drum-major stand placement.
- Performer-specific physical limits and instrument-aware movement warnings.

### Workflow and Interface

- Responsive Home project library with search, previews, recovery cards, and plugin management.
- Workspace profiles, detachable docks, layout reset/restore, command palette, shortcut editor, favorites, macros, and radial tools.
- Searchable roster, selection sets, hierarchical groups, section locking, multi-set editing, bulk properties, and keyboard drill entry.
- Responsive editor context bar, standard menu organization, workflow-ordered design pages, and dark/light themes.
- Set thumbnails, minimap, preview cache, background analysis, and lazy project preview loading.
- Configurable 6:5, 8:5, 12:5, 16:5, and custom drill grids with official-hash priority snapping and snap-aware on-field form handles.

### Data, Export, and Extensibility

- Versioned project schemas, migrations, atomic saves, versioned autosave backups, recovery, and Restore Previous Save.
- Crash logs and one-click bug-report bundles with project and environment diagnostics.
- MP4 export with background progress, cancellation, quality options, audio, and optional title card.
- Drill sheets, staff packets, section packets, dot books, coordinate summaries, CSV, project ZIP, print preview, and batch profiles.
- Per-project visual PDF layouts with arbitrary text/images, field and table elements, reusable presets, branding, page-size/orientation control, and dynamic set-note tokens.
- Versioned plugin API, compatibility gating, trust and permission prompts, plugin isolation, examples, and diagnostics.
- Stable/beta update channels, release notes, checksum verification, ZIP validation, failed-update rollback, and skip/ignore controls.

## Alpha to Beta Priorities

### P0 — Reliability and Data Confidence

Implemented in the v2.8 development cycle:

- [x] Automated playback matrix and configurable timed soak runner for 200, 300, 400, and 500 performers.
- [x] Fixture projects for large SVG-derived forms, Follow the Leader, moving props, choreography, tempo maps, and custom surfaces.
- [x] Save/load and migration coverage for every published project schema from v1 through v6.
- [x] Transactional multi-file saves with rollback tests for interrupted commits, low disk space, damaged JSON, and incomplete cleanup.
- [x] Deterministic visual/content tests for drill sheets, dot books, section packets, staff packets, coordinate summaries, CSV, project ZIP, and MP4 profiles.
- [x] Actionable Save, Autosave, Recovery, Project Open, Update, Bug Report, Shortcut, and Export failure dialogs.

Remaining operational validation:

- Run multi-hour soak sessions on the minimum and recommended Windows hardware profiles.
- Validate real MP4 output against the supported FFmpeg version matrix in addition to deterministic mocked encoding tests.
- Add damaged-audio, device-disconnect, GPU-reset, and forced-process-termination scenarios to release testing.

### P0 — Drill Correctness

Implemented in the v2.8 development cycle:

- [x] Structured repairable/unavoidable explanations for fixed start, fixed destination, no-go, path, and timing conflicts.
- [x] Guided destination-repair previews with exact owner swaps, before/apply scoring, and destination-picture preservation.
- [x] Structural and geometric validation for manually edited Bezier paths and generated Group Motion Ribbons.
- [x] Facing-relative turn-rate, backward/lateral movement, continuity, equipment, choreography, and prop-handling safety models.
- [x] Deterministic quarter-step football rounding and one shared coordinate formatter for every performer-facing export.
- [x] Reference regression cases for Side 1/Side 2, hashes, sidelines, yard lines, goal lines, end zones, indoor floors, parade routes, and CSV output.

Remaining field validation:

- Compare generated coordinates with independent staff dot-book samples from multiple college, high-school, indoor, and parade programs.
- Calibrate instrument/equipment/prop limits with qualified visual staff and performer feedback before presenting them as organization-specific policy.

### P0 — Playback and Audio

- [x] Rolling frame scheduling diagnostics with displayed FPS, dropped-deadline/adaptive-skip counters, render percentiles, audio-clock anomaly tracking, and cache statistics.
- [x] Automatic visual-quality reduction, throttled auxiliary panel work, label suppression for large casts, frame caching, and stable quality recovery without changing show timing.
- [x] Windows audio endpoint recreation and retry coverage for disconnects, default-device changes, selected-device fallback/return, Bluetooth stabilization, and device invalidation.
- [x] Background waveform regression coverage for long files, compressed/VBR timestamp mapping, unusual sample rates, multiple PCM depths, and channel layouts without requiring FFmpeg.
- [x] Sustained UI-load verification for pause, seek, loop, tempo-map mapping, set boundaries, cache reuse, and editing-quality restoration.

Remaining release qualification:

- Run the packaged-EXE Windows hardware matrix in `PLAYBACK_AUDIO_RELIABILITY.md` on wired, USB, HDMI, and at least two Bluetooth endpoints before each Beta release.
- Record machine-specific 30-minute soak baselines for integrated graphics and discrete-GPU systems at 300 and 500 performers.

### P1 — User Validation

- Publish a structured Beta test plan covering creation, editing, playback, printing, updating, recovery, and plugins.
- Add an optional first-run diagnostics check for graphics, audio output, write permissions, and FFmpeg capability.
- Add opt-in anonymous reliability metrics or a simpler in-app test-report workflow.
- Track reproducible issues by project schema, app version, Windows version, GPU, audio device, and plugin set.
- Define Beta-blocking severity levels and a public known-issues list.

## Beta Development Priorities

### Collaboration and Review

- Expand set-level Director's Notes into threaded review comments attached to counts, performers, paths, and storyboard scenes.
- Add project comparison and change summaries between saved versions.
- Add safer formation, timing-map, prop, and continuity transfer between projects.
- Explore read-only review packages for staff without the full editor.
- Investigate optional cloud backup and team sharing without making online access mandatory.

### Music and Rehearsal

- Add a dedicated beat-grid and tempo-map editor.
- Add synchronized audio stems and stem mute/solo controls.
- Improve automatic beat, impact, phrase, and rehearsal-mark detection.
- Add section-only playback, performer lookup, rehearsal loops, and configurable slow-motion presets.
- Add mobile-friendly performer charts and rehearsal packages.

### Printing and Performer Materials

- Validate the visual PDF layout system across common printers, duplex workflows, page sizes, field crops, and shared staff templates.
- Add individual performer packet batching with section-specific instructions and equipment notes.
- Add instructor packets combining conflicts, continuity, storyboard notes, and rehearsal priorities.
- Add portable print-template packs that can be shared between users without copying an entire project.
- Continue visual audits for common printers, page sizes, and duplex workflows.

### Plugin Ecosystem

- Freeze and document a Beta plugin API compatibility policy.
- Add plugin signing metadata and publisher identity.
- Add a curated plugin gallery with update discovery and compatibility filtering.
- Explore stronger process isolation for untrusted or resource-intensive plugins.
- Add automated plugin conformance tests for compiled Windows releases.

## Commercial-Use Requirements

Drill Pirate should not be described as commercially production-ready until all of the following are complete:

- Signed Windows installer with repair, uninstall, rollback, and optional portable installation.
- Automated release CI producing reproducible builds, checksums, release notes, and smoke-test results.
- Supported upgrade path across every public project schema and release channel.
- Documented support policy, response expectations, privacy policy, and security reporting process.
- Formal license and third-party dependency notices included in the application and distribution.
- Crash-free playback and editing targets established from sustained Beta usage.
- Verified export accuracy across staff packets, performer materials, coordinate CSV, project ZIP, and MP4.
- Accessibility pass for keyboard navigation, focus visibility, contrast, scaling, and screen readers.
- Performance certification for defined minimum and recommended hardware.
- A published compatibility matrix for Windows versions, audio formats, FFmpeg versions, and graphics hardware.

## Longer-Term Opportunities

- Native macOS package after Windows reliability targets are met.
- Tablet-focused rehearsal and performer companion experience.
- Cloud collaboration and project history as optional services.
- Marketplace distribution for reviewed plugins, templates, and formation libraries.
- Hardware-accelerated field rendering and export for extremely large productions.
- Interchange formats for other drill, music, CAD, and production-planning tools.

## Release Discipline

Every public release should:

1. Update the application version and all release-facing documentation.
2. Update this roadmap to move completed work into the product baseline.
3. Run the full automated test suite and UI smoke tests.
4. Launch the packaged executable and verify Home, project loading, playback, Settings, plugins, and export dialogs.
5. Publish the release ZIP and matching SHA-256 checksum.
6. Include a clear changelog, known issues, and tester focus areas on GitHub Releases.
