# Installation

This guide covers normal user installation, source setup, MP4 export requirements, updating, and Windows builds.

## Recommended Windows Install

1. Go to the [latest Drill Pirate release](https://github.com/CaKa12152/Drill-Pirate/releases/latest).
2. Download the Windows ZIP file.
3. Extract the ZIP completely.
4. Open the extracted folder.
5. Run `Drill Pirate.exe`.

Do not drag only `Drill Pirate.exe` to another folder. The app depends on files packaged beside the executable.

## Windows SmartScreen

Alpha builds are unsigned. Windows may show a SmartScreen warning.

Use this path only if you downloaded the app from the official release page:

1. Click `More info`.
2. Click `Run anyway`.

Code signing is listed as a release-readiness item in the roadmap.

## MP4 Export and ffmpeg

MP4 export requires `ffmpeg.exe`. It is not required for editing, audio playback, waveform display, PDFs, CSVs, or project ZIP exports.

### Option A: Select ffmpeg inside Drill Pirate

1. Download a Windows ffmpeg build.
2. Extract it.
3. Open Drill Pirate.
4. Go to `File > Export`.
5. Click `Set ffmpeg.exe`.
6. Select the `ffmpeg.exe` file inside the extracted `bin` folder.

Drill Pirate remembers this path.

### Option B: Add ffmpeg to PATH

Add the extracted `ffmpeg\bin` folder to the Windows `PATH` environment variable. Open a new terminal and verify:

```powershell
ffmpeg -version
```

If the command works in a new terminal, Drill Pirate should also be able to find it.

## Updating the App

Drill Pirate checks the GitHub latest release after startup.

When an update is available:

- `Install` downloads and installs the latest release without requiring Git.
- `Skip This Version` hides that release until a newer version is published.
- `Ignore` closes the prompt for the current session.

After a successful update, the next run shows the release log pulled from the GitHub latest release description. The release-log dialog has `Ok` and `Dont Show Again`.

Update settings:

- `Stable Releases` checks GitHub latest release.
- `Beta / Pre-Releases` checks recent GitHub releases and can offer pre-release builds.

ZIP updates are size-checked, optionally SHA-256 checked when a checksum asset is published, validated as ZIP files, and installed with rollback if the copy step fails.

## Source Setup

Use this if you are developing or testing directly from the repository.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m drill_writer
```

## Build a Windows EXE

Install requirements first, then run:

```powershell
.\build_exe.ps1
```

Expected output:

```text
dist\Drill Pirate\Drill Pirate.exe
dist\Drill Pirate Alpha 2.3.0 Windows.zip
```

Give testers the ZIP or the whole `dist\Drill Pirate` folder.

## App Data Locations

| Path | Purpose |
| --- | --- |
| `Documents\Drill Pirate Projects` | Project library scanned by the home screen. |
| `Documents\Drill Pirate Plugins` | Plugin folders and `plugins_state.json`. |
| Project `audio\` | Copied project audio files. |
| Project `props\` | Imported prop images. |

## Uninstall

Drill Pirate currently uses a portable ZIP-style distribution.

To remove it:

1. Delete the extracted app folder.
2. Optionally delete `Documents\Drill Pirate Projects`.
3. Optionally delete `Documents\Drill Pirate Plugins`.

Keep project folders if you want to preserve shows.
