# Drill Pirate Roadmap

Drill Pirate is currently **Alpha v2.7.0**. It already supports complete show creation, advanced formation design, synchronized playback, specialized performance tracking, printing, video export, plugins, project recovery, and in-app updates. The remaining roadmap focuses on reliability, validation, collaboration, and release operations rather than adding disconnected tools.

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

### Specialized Production

- Configurable football fields, high-school and college hashes, indoor floors, parade routes, and custom staging surfaces.
- Guard equipment and choreography tracks, including tosses and equipment changes.
- Movable props, performer attachments, carrying/pushing/rotation behavior, and an in-app prop designer.
- Front ensemble and drum-major stand placement.
- Performer-specific physical limits and instrument-aware movement warnings.

### Workflow and Interface

- Responsive Home project library with search, previews, recovery cards, and plugin management.
- Workspace profiles, detachable docks, layout reset/restore, command palette, shortcut editor, favorites, macros, and radial tools.
- Searchable roster, selection sets, hierarchical groups, section locking, multi-set editing, bulk properties, and keyboard drill entry.
- Responsive editor context bar, standard menu organization, workflow-ordered design pages, and dark/light themes.
- Set thumbnails, minimap, preview cache, background analysis, and lazy project preview loading.

### Data, Export, and Extensibility

- Versioned project schemas, migrations, atomic saves, versioned autosave backups, recovery, and Restore Previous Save.
- Crash logs and one-click bug-report bundles with project and environment diagnostics.
- MP4 export with background progress, cancellation, quality options, audio, and optional title card.
- Drill sheets, staff packets, section packets, dot books, coordinate summaries, CSV, project ZIP, print preview, and batch profiles.
- Versioned plugin API, compatibility gating, trust and permission prompts, plugin isolation, examples, and diagnostics.
- Stable/beta update channels, release notes, checksum verification, ZIP validation, failed-update rollback, and skip/ignore controls.

## Alpha to Beta Priorities

### P0 — Reliability and Data Confidence

- Add long-running playback soak tests at 200, 300, 400, and 500 performers.
- Add fixture-based regression projects for large SVG forms, Follow the Leader, props, choreography, tempo maps, and custom surfaces.
- Expand save/load and migration tests across every previously published project schema.
- Stress-test autosave recovery during interrupted writes, low disk space, and damaged JSON files.
- Add deterministic export tests for every PDF, CSV, ZIP, and MP4 profile.
- Audit all user-facing failures so they produce actionable dialogs instead of silent failures or console-only messages.

### P0 — Drill Correctness

- Improve conflict explanations when fixed start and destination pictures make a collision unavoidable.
- Add guided repair options that preview destination swaps before applying them.
- Strengthen validation for manually edited Bezier paths and group motion ribbons.
- Add biomechanical turn-rate, backward-march, equipment, prop, and direction-change modeling beyond simple yards-per-count limits.
- Audit coordinate rounding and every printed coordinate against real dot-book expectations.
- Add reference test cases for side-to-side, front/back hash, yard-line, end-zone, indoor, and parade coordinates.

### P0 — Playback and Audio

- Improve frame scheduling diagnostics and expose dropped-frame counters.
- Add automatic quality reduction or render caching when a show exceeds the real-time performance budget.
- Expand Windows audio-device recovery testing for disconnects, default-device changes, Bluetooth latency, and device invalidation.
- Add waveform and playback tests for long files, compressed files, variable bitrate, and unusual sample rates.
- Verify pause, seek, loop, tempo-map changes, and set boundaries under sustained UI load.

### P1 — User Validation

- Publish a structured Beta test plan covering creation, editing, playback, printing, updating, recovery, and plugins.
- Add an optional first-run diagnostics check for graphics, audio output, write permissions, and FFmpeg capability.
- Add opt-in anonymous reliability metrics or a simpler in-app test-report workflow.
- Track reproducible issues by project schema, app version, Windows version, GPU, audio device, and plugin set.
- Define Beta-blocking severity levels and a public known-issues list.

## Beta Development Priorities

### Collaboration and Review

- Add comments and review notes attached to sets, counts, performers, paths, and storyboard scenes.
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

- Expand template customization for headers, branding, field crop, coordinate wording, and continuity placement.
- Add individual performer packet batching with section-specific instructions and equipment notes.
- Add instructor packets combining conflicts, continuity, storyboard notes, and rehearsal priorities.
- Add print-template presets that can be shared between projects and users.
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
