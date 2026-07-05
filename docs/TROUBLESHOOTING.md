# Troubleshooting

Use this page to diagnose common user-facing problems.

## The App Does Not Open

Try:

1. Extract the ZIP fully before running.
2. Run `Drill Pirate.exe` from inside the extracted folder.
3. Do not move only the `.exe` out of the folder.
4. If SmartScreen appears, choose `More info` then `Run anyway` only if the file came from the official release page.

If the app still fails, send the release version, Windows version, and a screenshot of the error.

## Projects Are Missing From the Home Screen

The home screen scans:

```text
Documents\Drill Pirate Projects
```

A project folder must contain:

```text
metadata.json
sets.json
dots.json
```

If a project is elsewhere, use its folder as the save location when creating/opening workflows allow it, or move/copy it into the project library.

## UI Looks Crushed

Try:

- Maximize the window.
- Use `View > Workspaces > Focus Field`.
- Float panels to another monitor.
- Close unused panels and restore them later from `View > Panels`.
- Use the command palette instead of keeping every tool panel open.

If the layout gets stuck after opening a project while already fullscreen, resize the window once or switch workspaces.

## Audio Plays From the Wrong Device

Open:

```text
Settings > Preferences > Devices
```

Then:

1. Choose `Windows Default` to follow the system device.
2. Or choose a specific connected output.
3. Click `Refresh` after plugging in headphones.
4. Apply/OK.

If a selected device is unplugged, Drill Pirate falls back to Windows Default.

## Console Shows `AUDCLNT_E_DEVICE_INVALIDATED`

This means Windows invalidated the selected audio device, usually because headphones, Bluetooth audio, or the default device changed while Qt was using it.

Fix:

1. Open Settings.
2. Go to `Devices`.
3. Click `Refresh`.
4. Select `Windows Default`.
5. Restart Drill Pirate if audio remains distorted.

## Audio Is Clipping or Distorted

Try:

- Select `Windows Default` instead of a specific output device.
- Reopen the project after changing audio devices.
- Lower the Windows app volume for Drill Pirate.
- Check whether the source audio file itself is clipping.
- Avoid rapidly switching Bluetooth/headphone devices during playback.

## Waveform Looks Flat

Try:

1. Open the timeline/audio area.
2. Click `Reload Audio`.
3. Confirm the project has an active audio file.
4. Try a WAV file if the MP3 decoder fails on that file.
5. Confirm the audio is not extremely compressed/limited.

Waveform display does not require ffmpeg.

## Auto Hit Markers Do Not Appear

Auto hit detection depends on waveform peaks. If a track is heavily compressed or has no clear transients, the detector may find few or no hits.

Try:

- Reload audio.
- Add manual markers.
- Use count markers for the current set.
- Use timing anchors for precise musical alignment.

## MP4 Export Says ffmpeg Is Missing

Open:

```text
File > Export > Set ffmpeg.exe
```

Select the actual `ffmpeg.exe` file, not just the folder.

Or verify PATH in a new terminal:

```powershell
ffmpeg -version
```

## MP4 Export Seems Stuck Near the End

The progress dialog may spend time near the end while ffmpeg finalizes video/audio encoding.

If it never completes:

1. Re-select `ffmpeg.exe`.
2. Export a short test project.
3. Check disk space.
4. Avoid exporting to a protected folder.
5. Try a simpler audio file path with no unusual characters.

## SVG Import Fails

Try:

- Use a simple SVG path.
- Convert text to paths in your vector editor.
- Expand strokes/outlines.
- Avoid embedded raster images inside the SVG.
- Avoid extremely complex SVGs with thousands of tiny path segments.

If a file always fails, include the SVG with the bug report.

## SVG or Shape Import Puts Dots on Top of Each Other

Try:

- Increase selected performer count only after confirming the shape path is clean.
- Use a simpler path with fewer sharp corners.
- Use scale form after placement.
- Review corners and manually adjust anchors if needed.

This area is still improving; include the SVG and project ZIP when reporting cases.

## Form Paths Look Chaotic

Try:

1. Undo the form placement.
2. Re-select marchers in the intended order.
3. Apply the form again.
4. Use `Analyze Paths`.
5. Use `Clear Selected Paths` if old anchors are affecting the move.
6. Add path anchors manually where a performer should route around traffic.
7. Use `Follow-Leader Conveyor` for outline rotation/conveyor visuals.

Auto-planning is not yet a full commercial collision solver.

## Dragging a Tool Handle Moves the Whole Form

Make sure the correct tool is active. Advanced tool handles only behave as handles when the corresponding tool is active. Switch to the tool again from the toolbar or shortcut, then drag the visible handle.

## Plugins Do Not Appear

Check:

```text
Documents\Drill Pirate Plugins
```

Each plugin should be a folder with:

```text
plugin.json
plugin.py
```

Then:

1. Restart Drill Pirate or return to the home screen.
2. Open the `Plugins` tab.
3. Enable the plugin.
4. Open a project if the plugin adds project-window features.

## Plugin Crashes or Breaks the UI

Disable the plugin from the home screen `Plugins` tab.

If Drill Pirate cannot open far enough to disable it:

1. Go to `Documents\Drill Pirate Plugins`.
2. Move the plugin folder somewhere else.
3. Reopen Drill Pirate.

Plugins run as trusted Python code and are not sandboxed.

## Update Prompt Does Not Install

Try:

- Check internet access.
- Open the GitHub Releases page manually.
- Download the ZIP manually.
- Extract over a fresh folder rather than over a running app folder.
- Confirm antivirus did not quarantine the downloaded update.

Source/development runs cannot replace themselves; they open/download the release instead.

## Performance Is Slow on Large Shows

Try:

- Hide labels.
- Hide unused sections/layers.
- Use Focus Field workspace.
- Avoid extremely large prop images.
- Close extra floating panels.
- Use path analysis on selected sections instead of everything when possible.
- Save and reopen after heavy SVG/path editing.

Projects with 200-400 performers are the target range, but dense paths, labels, props, and PDFs can still be expensive.
