# Project Format

Drill Pirate projects are folders containing JSON files plus copied media assets. This keeps projects portable and easy to back up.

## Default Project Library

The home screen scans:

```text
Documents\Drill Pirate Projects
```

Each valid project folder must include:

```text
metadata.json
sets.json
dots.json
```

## Folder Layout

Typical project:

```text
My_Show\
  audio\
    show_audio.wav
  props\
    window_prop.png
  metadata.json
  dots.json
  props.json
  sets.json
  show.json
```

## `metadata.json`

Stores project-level identity and default timing.

```json
{
  "show_title": "My Show",
  "initial_tempo": 160.0,
  "default_counts_per_set": 16,
  "time_signature": "4/4",
  "audio_file": "audio/show_audio.wav"
}
```

Fields:

| Field | Meaning |
| --- | --- |
| `show_title` | Display title. |
| `initial_tempo` | Universal/default tempo. |
| `default_counts_per_set` | Count length used when creating new sets. |
| `time_signature` | Display metadata. |
| `audio_file` | Relative path to the main audio file. |

## `dots.json`

Stores performer roster data.

```json
{
  "dots": [
    {
      "id": "dot001",
      "name": "Dot 1",
      "x": 0.0,
      "y": 0.0,
      "color": "#e53935",
      "section": "winds",
      "instrument": "",
      "rank": "",
      "equipment": "",
      "layer": "Main"
    }
  ]
}
```

The dot `x` and `y` fields are field coordinates, not pixels.

## `props.json`

Stores imported prop metadata.

```json
{
  "props": [
    {
      "id": "prop001",
      "name": "Window Prop",
      "image_file": "props/window_prop.png",
      "x": 0.0,
      "y": 0.0,
      "width": 24.0,
      "height": 8.0,
      "rotation": 0.0,
      "layer": "Props"
    }
  ]
}
```

Prop images are copied into the project `props\` folder.

## `sets.json`

Stores every set and all set-specific positions/timing/path data.

```json
{
  "sets": [
    {
      "name": "Set 1",
      "start_count": 1,
      "end_count": 16,
      "tempo": null,
      "dot_positions": {
        "dot001": {
          "x": 0.0,
          "y": 0.0
        }
      },
      "prop_positions": {
        "prop001": {
          "x": 0.0,
          "y": 0.0,
          "width": 24.0,
          "height": 8.0,
          "rotation": 0.0
        }
      },
      "path_anchors": {},
      "path_controls": {},
      "count_positions": {},
      "movement_styles": {},
      "transition": "linear"
    }
  ]
}
```

Set fields:

| Field | Meaning |
| --- | --- |
| `name` | Editable set label. |
| `start_count` | First count of this set. |
| `end_count` | Last count of this set. |
| `tempo` | Optional set tempo override; `null` uses project/timing-map tempo. |
| `dot_positions` | End/start position map for each performer in this set. |
| `prop_positions` | Prop state for this set. |
| `path_anchors` | Red path anchor points per performer. |
| `path_controls` | Bezier tangent control data per performer. |
| `count_positions` | Per-count keyframe overrides. |
| `movement_styles` | Set-specific movement style metadata. |
| `transition` | `linear`, `ease_in_out`, or `curved`. |

## `show.json`

Stores show-level data that does not belong to only one set.

```json
{
  "title": "My Show",
  "version": 2,
  "schema_version": 2,
  "markers": [
    {
      "count": 12.0,
      "label": "Hit 1"
    }
  ],
  "constraints": [],
  "audio_versions": [
    {
      "name": "Main Audio",
      "audio_file": "audio/show_audio.wav",
      "active": true
    }
  ],
  "timing_events": [
    {
      "event_type": "anchor",
      "count": 1.0,
      "milliseconds": 0.0,
      "tempo": 0.0,
      "end_count": 0.0,
      "end_tempo": 0.0,
      "label": ""
    }
  ]
}
```

Timing event types include anchors, tempo changes, ritardandos, fermatas, and pickup-related timing data.

## Schema Version

Drill Pirate writes the current project schema into `show.json`.

```json
{
  "version": 2,
  "schema_version": 2
}
```

When an older project opens, Drill Pirate migrates it before loading and creates a `migration` backup first. If a project was saved by a newer unsupported app version, Drill Pirate refuses to open it instead of silently damaging it.

## Coordinates

Drill Pirate stores coordinates as yard-based field units:

- `x = 0` is the 50-yard line.
- Negative `x` is Side 1.
- Positive `x` is Side 2.
- `y = 0` is midfield front-to-back.
- Negative `y` is toward the front sideline.
- Positive `y` is toward the back sideline.

The coordinate formatter converts these values into drill-sheet language:

- `On 50`.
- `On 45 S2`.
- `2 steps inside 40 S1`.
- `On FH`.
- `6 steps in front of FH`.

## Autosave

Project data is autosaved during editing and saved when returning home or closing a project window. Use `File > Save` before exporting or sharing a project ZIP.

## Backups and Recovery

Backups are stored inside each project:

```text
My_Show\
  .drill_pirate_backups\
    2026-07-06T20-30-15Z_autosave.zip
    2026-07-06T20-31-02Z_manual.zip
```

Backups include the core JSON files:

- `metadata.json`
- `dots.json`
- `props.json`
- `sets.json`
- `show.json`

Use `File > Restore Previous Save` to restore a backup. Drill Pirate creates a `pre_restore` backup before overwriting current JSON files.

## Editing JSON Manually

Manual JSON editing is possible but not recommended while Drill Pirate is open. If you edit project files by hand:

1. Close the project in Drill Pirate.
2. Back up the folder.
3. Edit JSON.
4. Reopen the project.
5. Verify every set before continuing.
