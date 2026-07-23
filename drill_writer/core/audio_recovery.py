from __future__ import annotations

from dataclasses import dataclass


WINDOWS_DEFAULT_DEVICE_ID = "__windows_default__"


@dataclass(frozen=True, slots=True)
class AudioDeviceSelection:
    requested_id: str
    physical_id: str
    used_fallback: bool


def choose_audio_device_id(
    requested_id: object,
    available_ids: list[str] | tuple[str, ...] | set[str],
    default_id: object,
) -> AudioDeviceSelection:
    requested = str(requested_id or WINDOWS_DEFAULT_DEVICE_ID)
    available = {str(device_id) for device_id in available_ids if str(device_id)}
    default = str(default_id or "")
    if requested == WINDOWS_DEFAULT_DEVICE_ID:
        return AudioDeviceSelection(requested, default if default in available else "", False)
    if requested in available:
        return AudioDeviceSelection(requested, requested, False)
    fallback = default if default in available else ""
    return AudioDeviceSelection(requested, fallback, True)


DEVICE_INVALIDATION_TERMS = (
    "audclnt_e_device_invalidated",
    "device invalidated",
    "device removed",
    "audio device was disconnected",
    "audio output device",
    "no audio device",
    "resource error",
)


def is_recoverable_audio_device_error(message: object) -> bool:
    normalized = str(message or "").strip().lower()
    return bool(normalized) and any(term in normalized for term in DEVICE_INVALIDATION_TERMS)


def recommended_audio_resume_delay_ms(device_description: object) -> int:
    description = str(device_description or "").lower()
    if any(term in description for term in ("bluetooth", "hands-free", "headset", "airpods", "buds")):
        return 240
    if any(term in description for term in ("usb", "dock", "display audio", "hdmi")):
        return 130
    return 80


@dataclass(slots=True)
class AudioRecoveryPolicy:
    attempts: int = 0
    max_attempts: int = 6
    recovering: bool = False
    last_reason: str = ""

    def schedule(self, reason: object) -> int | None:
        normalized = str(reason or "Audio output changed").strip()
        if self.recovering:
            self.last_reason = normalized or self.last_reason
            return None
        if self.attempts >= self.max_attempts:
            self.recovering = True
            self.last_reason = normalized
            return 5000
        delays = (0, 120, 300, 700, 1400, 2400)
        delay = delays[min(self.attempts, len(delays) - 1)]
        self.attempts += 1
        self.recovering = True
        self.last_reason = normalized
        return delay

    def completed(self, success: bool) -> None:
        self.recovering = False
        if success:
            self.attempts = 0
            self.last_reason = ""

    def reset(self) -> None:
        self.attempts = 0
        self.recovering = False
        self.last_reason = ""
