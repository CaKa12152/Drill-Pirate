# Exports

Open the export dialog with:

```text
File > Export
Ctrl+E
```

The export dialog includes:

- MP4 Video.
- Drill Sheet PDF.
- Dot Book PDF.
- Staff Packet PDF.
- Coordinate CSV.
- Project ZIP.
- Set ffmpeg.exe.

## MP4 Video

MP4 export renders the full show animation and audio through ffmpeg.

Requirements:

- `ffmpeg.exe` must be available.
- The project should be saved.
- Audio should be loaded if you want audio in the rendered video.

Set ffmpeg:

1. Open `File > Export`.
2. Click `Set ffmpeg.exe`.
3. Select the actual `ffmpeg.exe` file.

Or add `ffmpeg\bin` to the Windows `PATH`.

MP4 export uses a progress dialog. Encoding may spend time near the end while ffmpeg finalizes the video file. If it never completes, verify the ffmpeg path and check available disk space.

## Project ZIP

Project ZIP creates a backup/share package of the project folder.

It includes:

- Audio files.
- Prop images.
- Project JSON files.
- Dot data.
- Set data.
- Metadata.
- Show-level markers, timing events, constraints, and audio versions.

It does not include the internal `.drill_pirate_backups` history folder, so normal project exports stay smaller.

Use this when reporting bugs because it preserves the project state.

## Drill Sheet PDF

Drill Sheet PDF creates a landscape page for each set.

Typical contents:

- Show title.
- Set name.
- Count range.
- Tempo.
- Field image.
- Set notes/details relevant to performers and staff.

The field image is designed to take most of the page.

## Dot Book PDF

Dot Book PDF creates performer-focused coordinate pages.

Typical contents:

- Performer name/ID.
- Section/instrument metadata when available.
- Set-by-set coordinates.
- Movement-style notes where assigned.

Use this for individual performer packets.

## Staff Packet PDF

Staff Packet PDF is intended for staff and instructor review.

Typical contents:

- Show summary.
- Set pages.
- Larger field images.
- Path/safety warning summaries.
- Key metadata needed for rehearsal planning.

## Coordinate CSV

Coordinate CSV exports performer coordinates for every set.

Use this for:

- Spreadsheet review.
- External dot-card workflows.
- Debugging coordinate problems.
- Importing into another tool.

## PDF and CSV Requirements

PDF and CSV exports do not require ffmpeg.

They use the project data currently saved in Drill Pirate. Save before exporting if you want to be certain the files match the current window state.

## Export Quality Checklist

Before sharing exports:

1. Save the project.
2. Scrub through every set.
3. Analyze selected or all paths.
4. Check markers and timing anchors.
5. Confirm props are visible and correctly scaled.
6. Export a project ZIP for backup.
7. Export PDFs/CSV for rehearsal.
8. Export MP4 last because it takes the longest.

## Common Export Problems

| Problem | Fix |
| --- | --- |
| MP4 says ffmpeg is missing | Use `Set ffmpeg.exe` or add `ffmpeg\bin` to PATH. |
| MP4 stays near the end for a while | Wait for ffmpeg finalization; large shows/audio can take time. |
| MP4 never finishes | Re-select ffmpeg, check disk space, then try a shorter project. |
| PDF misses a recent edit | Save the project and export again. |
| Exported project is too large | Audio and prop image files are included; compress or replace oversized media. |
| Coordinates look wrong | Check the set position and verify the performer is on the intended side/hash. |
