# Reliability Testing

Drill Pirate includes a repeatable reliability gate for project data, playback, high-risk show fixtures, exports, and user-facing failures.

## Full Regression Suite

Run every automated test from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

The playback/audio reliability expansion brings the suite to 154 tests.

## Focused Reliability Suite

Run only the data-confidence, soak-matrix, fixture, and export tests:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_reliability.py" -v
```

This verifies:

- Playback at 200, 300, 400, and 500 performers.
- Position continuity across every set boundary.
- Large SVG-derived forms without duplicate coordinates.
- Follow the Leader ribbons and direction-of-travel facing data.
- Moving props and performer attachments.
- Guard choreography and equipment changes.
- Tempo maps containing pickups, tempo changes, ritardandos, and fermatas.
- Indoor/custom surface persistence.
- Project migrations from schemas v1 through v6.
- Interrupted-save rollback, low-disk behavior, and damaged JSON guidance.
- Deterministic PDF, CSV, project ZIP, and MP4 profile output.
- User-visible, actionable Save and Autosave failure handling.
- Frame scheduling diagnostics, automatic quality reduction/recovery, and playback-frame caching.
- Windows audio invalidation, disconnect/default-device selection, and Bluetooth stabilization policy.
- Long, compressed/VBR, unusual-rate, and unusual-bit-depth waveform fixtures.
- Pause, seek, loop, tempo-map, and set-boundary behavior under sustained 300-performer UI load.

Run only the playback and audio gate:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_playback_audio_p0.py" -v
```

See [Playback and Audio Reliability](PLAYBACK_AUDIO_RELIABILITY.md) for diagnostics, adaptive-quality behavior, and the Windows hardware qualification matrix.

## Timed Playback Soak

Run the default five-minute soak for each supported roster size:

```powershell
.\.venv\Scripts\python.exe tests\soak_playback.py
```

That runs for approximately 20 minutes total: five minutes each at 200, 300, 400, and 500 performers.

Use a longer release soak:

```powershell
.\.venv\Scripts\python.exe tests\soak_playback.py --minutes 30
```

Test selected roster sizes:

```powershell
.\.venv\Scripts\python.exe tests\soak_playback.py --minutes 10 --performers 300 500
```

Optionally enforce a machine-specific average frame-time budget:

```powershell
.\.venv\Scripts\python.exe tests\soak_playback.py --minutes 10 --max-average-frame-ms 16.67
```

The soak validates complete performer/facing maps, finite coordinates, audio/count round trips, set cycling, and frame-time statistics. Performance thresholds are optional because CI machines and user hardware vary significantly.

## Export Determinism

PDF determinism compares rendered page images rather than raw PDF bytes because PDF writers may include document metadata. CSV and project ZIP outputs are compared byte-for-byte. MP4 orchestration is tested with deterministic frame rendering and a deterministic encoder substitute; release testing should additionally encode one real MP4 using each supported FFmpeg encoder.

## Release Gate

Before publishing a build:

1. Run the focused reliability suite.
2. Run the full regression suite.
3. Run at least a five-minute soak at all four roster sizes.
4. Open fixture-equivalent real projects in the packaged EXE.
5. Export one real PDF batch and one real MP4.
6. Verify the release ZIP checksum and launch the packaged EXE.
