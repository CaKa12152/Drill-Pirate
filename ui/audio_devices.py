from __future__ import annotations

from PySide6.QtMultimedia import QAudioDevice, QMediaDevices


AUDIO_OUTPUT_DEVICE_SETTING = "audio/output_device_id"
DEFAULT_AUDIO_OUTPUT_DEVICE_ID = "__windows_default__"


def normalize_audio_output_device_id(device_id: object) -> str:
    value = str(device_id or "").strip()
    return value or DEFAULT_AUDIO_OUTPUT_DEVICE_ID


def audio_device_id(device: QAudioDevice) -> str:
    return bytes(device.id()).hex()


def audio_device_label(device: QAudioDevice) -> str:
    label = device.description() or "Unknown audio device"
    if device.isDefault():
        return f"{label} (current Windows default)"
    return label


def audio_output_devices() -> list[QAudioDevice]:
    return [device for device in QMediaDevices.audioOutputs() if not device.isNull()]


def audio_output_for_id(device_id: object) -> QAudioDevice:
    normalized = normalize_audio_output_device_id(device_id)
    if normalized != DEFAULT_AUDIO_OUTPUT_DEVICE_ID:
        for device in audio_output_devices():
            if audio_device_id(device) == normalized:
                return device
    return QMediaDevices.defaultAudioOutput()


def audio_output_label_for_id(device_id: object) -> str:
    normalized = normalize_audio_output_device_id(device_id)
    if normalized == DEFAULT_AUDIO_OUTPUT_DEVICE_ID:
        device = QMediaDevices.defaultAudioOutput()
        if device.isNull():
            return "Windows Default"
        return f"Windows Default - {device.description()}"
    for device in audio_output_devices():
        if audio_device_id(device) == normalized:
            return audio_device_label(device)
    return "Selected device unavailable - using Windows Default"
