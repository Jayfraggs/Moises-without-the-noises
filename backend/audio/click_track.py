"""Generate a simple WAV click track from a beats JSON artifact."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import wavfile


_CLICK_DURATION_SECONDS = 0.020
_TAIL_SILENCE_SECONDS = 2.0
_DOWNBEAT_FREQUENCY_HZ = 1000.0
_BEAT_FREQUENCY_HZ = 800.0
_AMPLITUDE = 0.8


def _load_beats(beats_json_path: Path) -> list[dict[str, Any]]:
    with beats_json_path.open("r", encoding="utf-8") as beats_file:
        payload = json.load(beats_file)

    if not isinstance(payload, dict) or not isinstance(payload.get("beats"), list):
        raise ValueError("beats JSON must contain a 'beats' list")
    if not payload["beats"]:
        raise ValueError("beats JSON must contain at least one beat")
    if not all(isinstance(beat, dict) for beat in payload["beats"]):
        raise ValueError("each beat must be an object")
    return payload["beats"]


def generate_click_track(
    beats_json_path: Path,
    output_path: Path,
    sample_rate: int = 44100,
) -> Path:
    """Write a mono 16-bit WAV click track and return its output path.

    Beat timestamps are read from each beat object's ``time_s`` field. The
    first beat determines the start of the rendered timeline, and two seconds
    of silence follow the last beat.
    """
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")

    beats = _load_beats(beats_json_path)
    timestamps: list[tuple[float, int]] = []
    for beat in beats:
        time_s = beat.get("time_s")
        if isinstance(time_s, bool) or not isinstance(time_s, (int, float)):
            raise ValueError("each beat must contain a numeric time_s")
        if not np.isfinite(time_s) or time_s < 0:
            raise ValueError("beat time_s values must be finite and non-negative")
        beat_number = beat.get("beat_number")
        if isinstance(beat_number, bool) or not isinstance(beat_number, int):
            raise ValueError("each beat must contain an integer beat_number")
        timestamps.append((float(time_s), beat_number))

    first_time = min(time_s for time_s, _ in timestamps)
    last_time = max(time_s for time_s, _ in timestamps)
    total_samples = int(np.ceil((last_time - first_time + _TAIL_SILENCE_SECONDS) * sample_rate))
    audio = np.zeros(total_samples, dtype=np.float64)
    click_samples = max(1, int(round(_CLICK_DURATION_SECONDS * sample_rate)))
    envelope = np.linspace(1.0, 0.0, click_samples, endpoint=False)
    sample_times = np.arange(click_samples, dtype=np.float64) / sample_rate

    for time_s, beat_number in timestamps:
        start = int(round((time_s - first_time) * sample_rate))
        end = min(start + click_samples, total_samples)
        if start >= total_samples:
            continue
        frequency = (
            _DOWNBEAT_FREQUENCY_HZ if beat_number == 1 else _BEAT_FREQUENCY_HZ
        )
        click = _AMPLITUDE * np.sin(2.0 * np.pi * frequency * sample_times) * envelope
        audio[start:end] += click[: end - start]

    pcm_audio = np.clip(audio, -1.0, 1.0)
    wavfile.write(output_path, sample_rate, np.rint(pcm_audio * 32767.0).astype(np.int16))
    return output_path
