# Drill Pirate

Drill Pirate is a desktop drill-writing application for marching band and DCI-style visual design. It combines a field editor, set-based animation, audio synchronization, formation tools, props, plugins, and production exports into one Windows-first creative workflow.

> Current release: **Alpha 2.4.0**

## Quick Links

| Resource | Purpose |
| --- | --- |
| [User Guide](docs/USER_GUIDE.md) | Complete walkthrough for writing a show in Drill Pirate. |
| [Installation](docs/INSTALLATION.md) | Download, run, source setup, ffmpeg setup, and Windows EXE builds. |
| [Feature Reference](docs/FEATURES.md) | Full feature list organized by area of the app. |
| [Keyboard Shortcuts](docs/KEYBOARD_SHORTCUTS.md) | Built-in shortcuts and shortcut customization. |
| [Exports](docs/EXPORTS.md) | MP4, project ZIP, drill sheets, dot books, staff packets, and CSV exports. |
| [Project Format](docs/PROJECT_FORMAT.md) | Project folder layout and JSON data model. |
| [Plugin Development](docs/PLUGIN_DEVELOPMENT.md) | Plugin folder layout, hooks, form tools, settings, previews, and security notes. |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common install, audio, export, plugin, and performance fixes. |
| [Release and Support](docs/RELEASE_AND_SUPPORT.md) | Public release checklist, tester instructions, bug reports, and update flow. |
| [Roadmap](docs/ROADMAP.md) | Current alpha limitations and production-readiness targets. |

## What Drill Pirate Does

- Creates projects with title, audio, universal tempo, default counts, time signature, and starting marcher count.
- Displays a home project library from `Documents\Drill Pirate Projects` with field-preview cards.
- Provides a dark/light themed UI while keeping the field readable and field-like.
- Edits marchers, props, sets, count ranges, tempos, movement styles, markers, and path anchors.
- Uses a real field coordinate system and exports performer-readable coordinates such as `On 45 S2` and `6 steps in front of FH`.
- Plays animation against the audio/timing map with waveform scrubbing and count markers.
- Provides formation tools for lines, curves, arcs, circles, rectangles, spirals, grids, SVG/imported shapes, scatter layouts, mirrors, scaling, centering, and follow-leader/conveyor motion.
- Supports dockable/floating panels, workspace presets, command palette, shortcut editor, searchable marchers, batch editing, and plugin-created tools.
- Exports MP4 video, project ZIP backups, drill-sheet PDFs, dot-book PDFs, staff packets, and coordinate CSV files.
- Protects projects with schema migrations, atomic JSON saves, versioned backups, recovery prompts, and Restore Previous Save.
- Logs unexpected crashes and can export a one-click bug report bundle with logs and project files.
- Supports stable/beta update channels with size/checksum verification, ZIP validation, rollback on install-copy failure, and per-version release notes.
- Improves drill correctness with deterministic form assignment, conflict timeline analysis, stronger constraints, and coordinate regression tests.

## Install for Testers

1. Download the latest Windows ZIP from the [GitHub Releases page](https://github.com/CaKa12152/Drill-Pirate/releases/latest).
2. Extract the entire ZIP folder.
3. Run `Drill Pirate.exe` from inside the extracted folder.
4. If Windows SmartScreen appears, choose `More info` then `Run anyway`.

Do not run only the `.exe` outside the folder. The bundled Qt files, plugins, Python runtime, and assets must remain beside the executable.

## Run From Source

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m drill_writer
```

## Build the Windows EXE

```powershell
.\build_exe.ps1
```

The build output is created at:

```text
dist\Drill Pirate\Drill Pirate.exe
dist\Drill Pirate Alpha 2.4.0 Windows.zip
```

## Important Locations

| Location | Contents |
| --- | --- |
| `Documents\Drill Pirate Projects` | User project folders scanned by the home screen. |
| `Documents\Drill Pirate Plugins` | User plugin folders and plugin enable/disable state. |
| Project `audio\` folder | Copied audio files for the project. |
| Project `props\` folder | Imported prop images. |
| Project JSON files | `metadata.json`, `dots.json`, `sets.json`, `props.json`, and `show.json`. |
| Project `.drill_pirate_backups` folder | Versioned JSON backups used by project recovery and Restore Previous Save. |

## MP4 Export Requirement

MP4 export requires `ffmpeg.exe`. Drill Pirate does not bundle ffmpeg.

Use one of these options:

- Put the `ffmpeg\bin` folder on your Windows `PATH`.
- Open `File > Export > Set ffmpeg.exe` and select the exact executable.

PDF, CSV, ZIP, waveform display, and normal editing do not require ffmpeg.

## Plugin Support

Plugins are normal folders inside `Documents\Drill Pirate Plugins`. They run inside the bundled Python runtime in the packaged EXE, so normal users do not need Python installed. Plugins can register menu actions, panel buttons, custom form tools, adjustable tool settings, draggable on-field handles, and stylesheet changes.

Plugins are powerful and run as trusted code. Only install plugins from people you trust.

## Alpha Status

Drill Pirate is usable for alpha testing and real feedback, but it is not yet a finished commercial drill-writing package. The most important remaining production areas are deeper collision avoidance, true constraint solving, more advanced printed coordinate books, installer/signing polish, automated release QA, and broader test coverage.

See [Roadmap](docs/ROADMAP.md) for the full production-readiness list.
