from __future__ import annotations

from array import array
from dataclasses import dataclass
from math import ceil, sqrt
from pathlib import Path
from typing import Callable, Iterable
import wave


@dataclass(frozen=True, slots=True)
class WaveformData:
    peaks: list[float]
    rms: list[float]
    duration_ms: int
    sample_rate: int
    source_format: str


class WaveformDecodeError(RuntimeError):
    pass


CompressedDecoder = Callable[[Path, int], WaveformData]


def decode_audio_waveform(
    path: Path,
    target_count: int = 2200,
    compressed_decoder: CompressedDecoder | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> WaveformData:
    source = Path(path)
    if not source.exists():
        raise WaveformDecodeError(f"Audio file does not exist: {source}")
    if source.suffix.lower() in {".wav", ".wave"}:
        return decode_wav_waveform(source, target_count, cancelled=cancelled)
    if compressed_decoder is None:
        raise WaveformDecodeError(
            "This compressed audio format requires the operating-system audio decoder."
        )
    return compressed_decoder(source, target_count)


def decode_wav_waveform(
    path: Path,
    target_count: int = 2200,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> WaveformData:
    target = max(32, int(target_count))
    try:
        with wave.open(str(path), "rb") as audio:
            sample_rate = max(1, int(audio.getframerate()))
            frame_count = max(0, int(audio.getnframes()))
            channel_count = max(1, int(audio.getnchannels()))
            sample_width = int(audio.getsampwidth())
            if sample_width not in {1, 2, 3, 4}:
                raise WaveformDecodeError(f"Unsupported WAV sample width: {sample_width * 8}-bit PCM")
            frames_per_bin = max(1, ceil(frame_count / target))
            peaks: list[float] = []
            rms_values: list[float] = []
            while len(peaks) < target:
                if cancelled is not None and cancelled():
                    raise WaveformDecodeError("Waveform decode cancelled.")
                raw = audio.readframes(frames_per_bin)
                if not raw:
                    break
                values = pcm_values(raw, sample_width)
                if not values:
                    continue
                peak = max(max(values), -min(values))
                square_mean = sum(float(value) * float(value) for value in values) / len(values)
                peaks.append(float(peak))
                rms_values.append(sqrt(square_mean))
    except WaveformDecodeError:
        raise
    except (EOFError, OSError, wave.Error) as exc:
        raise WaveformDecodeError(f"Could not decode WAV audio: {exc}") from exc
    if not peaks:
        raise WaveformDecodeError("The WAV file contains no decodable audio samples.")
    normalized_peaks, normalized_rms = normalize_envelopes(peaks, rms_values, target)
    return WaveformData(
        normalized_peaks,
        normalized_rms,
        int(frame_count / sample_rate * 1000),
        sample_rate,
        f"PCM {sample_width * 8}-bit / {channel_count} channel(s)",
    )


def pcm_values(raw: bytes, sample_width: int) -> list[int] | array:
    if sample_width == 1:
        return [(value - 128) * 256 for value in raw]
    if sample_width == 2:
        values = array("h")
        values.frombytes(raw[: len(raw) - len(raw) % 2])
        return values
    if sample_width == 4:
        values = array("i")
        values.frombytes(raw[: len(raw) - len(raw) % 4])
        return values
    result: list[int] = []
    for index in range(0, len(raw) - 2, 3):
        value = raw[index] | raw[index + 1] << 8 | raw[index + 2] << 16
        if value & 0x800000:
            value -= 0x1000000
        result.append(value)
    return result


def waveform_from_timed_envelopes(
    points: Iterable[tuple[float, float, float]],
    duration_ms: int,
    target_count: int = 2200,
    *,
    sample_rate: int = 0,
    source_format: str = "Decoded audio",
) -> WaveformData:
    target = max(32, int(target_count))
    duration = max(1, int(duration_ms))
    peak_bins = [0.0] * target
    rms_sums = [0.0] * target
    rms_counts = [0] * target
    for time_ms, peak, rms in points:
        index = min(target - 1, max(0, int(float(time_ms) / duration * target)))
        peak_bins[index] = max(peak_bins[index], abs(float(peak)))
        rms_sums[index] += abs(float(rms))
        rms_counts[index] += 1
    carry_peak = 0.0
    carry_rms = 0.0
    rms_bins: list[float] = []
    for index in range(target):
        if peak_bins[index] > 0:
            carry_peak = peak_bins[index]
        else:
            peak_bins[index] = carry_peak
        if rms_counts[index]:
            carry_rms = rms_sums[index] / rms_counts[index]
        rms_bins.append(carry_rms)
    normalized_peaks, normalized_rms = normalize_envelopes(peak_bins, rms_bins, target)
    return WaveformData(
        normalized_peaks,
        normalized_rms,
        duration,
        max(0, int(sample_rate)),
        source_format,
    )


def analyze_waveform(samples, target_count: int) -> tuple[list[float], list[float]]:
    if not samples:
        return [], []
    stride = max(1, ceil(len(samples) / max(1, target_count)))
    peaks: list[float] = []
    rms_values: list[float] = []
    for index in range(0, len(samples), stride):
        chunk = samples[index : index + stride]
        if not chunk:
            continue
        peak = max(max(chunk), -min(chunk))
        peaks.append(float(peak))
        rms_values.append(sqrt(sum(float(value) * float(value) for value in chunk) / len(chunk)))
    return normalize_envelopes(peaks, rms_values, target_count)


def normalize_envelopes(
    peaks: list[float],
    rms_values: list[float],
    target_count: int,
) -> tuple[list[float], list[float]]:
    normalized_peaks = robust_normalize(peaks, low_percentile=0.08, high_percentile=0.995, gamma=1.08)
    normalized_rms = robust_normalize(rms_values, low_percentile=0.12, high_percentile=0.97, gamma=1.35)
    return normalized_peaks[:target_count], normalized_rms[:target_count]


def robust_normalize(
    values: list[float],
    low_percentile: float,
    high_percentile: float,
    gamma: float,
) -> list[float]:
    if not values:
        return []
    sorted_values = sorted(values)
    low_index = min(len(sorted_values) - 1, max(0, int(len(sorted_values) * low_percentile)))
    high_index = min(len(sorted_values) - 1, max(0, int(len(sorted_values) * high_percentile)))
    floor_value = sorted_values[low_index]
    ceiling = max(floor_value + 1.0, sorted_values[high_index])
    normalized: list[float] = []
    for value in values:
        ratio = max(0.0, min(1.0, (value - floor_value) / (ceiling - floor_value)))
        normalized.append(0.03 + 0.97 * (ratio**gamma))
    return normalized
