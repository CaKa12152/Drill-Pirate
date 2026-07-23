# Playback and Audio Reliability

Drill Pirate treats audio or the internal monotonic timer as the show clock. Rendering may reduce visual detail when a computer cannot sustain the requested frame budget, but adaptive playback never changes show counts, set timing, marcher coordinates, facings, prop states, or the audio position.

## Live Diagnostics

The `Audio & Counts` timeline displays:

- Displayed field FPS over the rolling sample window.
- Dropped frames, separated into late timer deadlines and intentional adaptive skips.
- Average and 95th-percentile frame cost.
- Current quality level: `Full`, `Balanced`, or `Performance`.
- Playback-frame cache hit rate.

Use `Playback > Reset Playback Diagnostics` or the timeline's `Reset Stats` button before profiling a section. Audio-clock regressions and unusually large jumps are also recorded internally for debugging.

## Adaptive Playback

Adaptive playback starts at full visual quality and evaluates a rolling frame-cost window. If the field exceeds its real-time budget it progressively:

1. Reduces nonessential panel, minimap, measurement, and choreography refresh frequency.
2. Reduces expensive painter hints and hides labels only on sufficiently large casts.
3. Targets 45 FPS and then 30 FPS while retaining the authoritative audio/count position.
4. Reuses evaluated position, facing, and prop frames during loops and repeated previews.
5. Restores higher quality after sustained headroom returns and restores full editing quality on pause.

These behaviors can be independently toggled in `Settings > Preferences > Playback`. Disabling adaptive quality keeps full rendering enabled. Disabling the cache immediately releases cached frames.

## Windows Audio Recovery

Qt audio output objects are recreated after endpoint invalidation rather than reusing a stale WASAPI device. Recovery preserves the requested output, playback position, volume, and whether playback was active.

The recovery path handles:

- `AUDCLNT_E_DEVICE_INVALIDATED` and equivalent resource errors.
- Unplugged wired, USB, HDMI, and dock outputs.
- Changes to the Windows default output while `Windows Default` is selected.
- Temporary fallback to the Windows default when a specifically selected device disconnects.
- Automatic return to a specifically selected device when it reconnects.
- Longer startup stabilization for Bluetooth and hands-free endpoints.
- Debounced topology changes, bounded fast retries, and low-frequency continued recovery after the fast retry window.

Pressing Pause during recovery cancels automatic resume. This prevents an endpoint reconnect from restarting playback after the writer intentionally stopped it.

## Waveform Decoding

Waveforms decode on a background thread and do not require FFmpeg. WAV files use a streaming PCM decoder with bounded envelope memory. MP3, AAC/M4A, FLAC, AIFF, and other compressed formats use the Qt/Windows codec path and map samples by decoded timestamps, which supports variable-bitrate sources.

Supported PCM regression coverage includes mono/stereo, 8/16/24/32-bit samples, 8 kHz through 96 kHz sample rates, long files, silence-to-impact dynamics, cancellation, and background completion. Reload with the application's `Reload Audio` command if a file is replaced outside Drill Pirate.

## Automated Gate

Run the focused playback/audio suite:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_playback_audio_p0.py" -v
```

The suite verifies frame diagnostics, adaptive degradation/recovery, cache eviction, endpoint-selection behavior, invalidation retry policy, Bluetooth delay policy, long and unusual WAV files, compressed/VBR timestamp mapping, asynchronous waveform loading, and pause/seek/loop/tempo/set-boundary behavior under a 300-performer UI workload.

The general reliability suite additionally exercises 200, 300, 400, and 500 performer playback fixtures:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

## Windows Hardware Qualification

Automated tests cannot physically disconnect user hardware. Before a public build, run this matrix in the packaged EXE with a five-minute show and record dropped frames before and after each event:

| Scenario | Required result |
| --- | --- |
| Unplug and reconnect 3.5 mm or USB headphones | Playback pauses briefly, output is recreated, position is retained, and audio resumes without clipping. |
| Switch Windows default from speakers to headphones | `Windows Default` follows the new endpoint without restarting the show. |
| Disable and re-enable a Bluetooth headset | Recovery waits for endpoint stabilization, resumes once, and does not produce repeated invalidation messages. |
| Remove the selected specific device | Drill Pirate temporarily uses the Windows default and retains the specific-device preference. |
| Reconnect the selected specific device | Output returns to the selected endpoint automatically. |
| Change default device during pause | Output updates but playback remains paused. |
| Seek and toggle loop during sustained 300–500 performer playback | Audio, waveform, set boundary, and field position remain synchronized. |
| Play long MP3 VBR, FLAC, 48 kHz, and 96 kHz files | Waveform completes in the background and visible dynamics match audible impacts. |

Any failure should be reported with `Help > Export Bug Report Bundle`, the device description, Windows version, connection type, and the playback diagnostics text.
