"""
Run this script once to generate all synthetic test audio fixtures.
Requires: numpy, soundfile
No models or network access needed.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

FIXTURES_DIR = Path(__file__).resolve().parent
AUDIO_DIR = FIXTURES_DIR / "audio"
GROUND_TRUTH_DIR = FIXTURES_DIR / "ground_truth"
SAMPLE_RATE = 22050


def generate_sine_note(freq_hz: float, duration_s: float, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Pure sine wave at freq_hz for duration_s seconds."""
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    return 0.5 * np.sin(2 * np.pi * freq_hz * t)


def generate_silence(duration_s: float, sr: int = SAMPLE_RATE) -> np.ndarray:
    return np.zeros(int(sr * duration_s), dtype=np.float32)


def generate_white_noise(duration_s: float, sr: int = SAMPLE_RATE, amplitude: float = 0.1) -> np.ndarray:
    return np.random.RandomState(42).randn(int(sr * duration_s)).astype(np.float32) * amplitude


def _normalize_peak(audio: np.ndarray) -> np.ndarray:
    peak = np.abs(audio).max() if audio.size else 1.0
    if peak < 1e-12:
        return audio
    return audio / (peak + 1e-8)


def _write_audio(path: Path, audio: np.ndarray, sr: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio.astype(np.float32), sr)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def generate_c_major_scale() -> np.ndarray:
    freqs = [261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88, 523.25]
    note_audio = []
    for freq in freqs:
        note_audio.append(generate_sine_note(freq, 0.5))
    return np.concatenate(note_audio)


def generate_g_major_scale() -> np.ndarray:
    freqs = [392.00, 440.00, 493.88, 523.25, 587.33, 659.25, 739.99, 783.99]
    note_audio = []
    for freq in freqs:
        note_audio.append(generate_sine_note(freq, 0.5))
    return np.concatenate(note_audio)


def generate_a_minor_scale() -> np.ndarray:
    freqs = [440.00, 493.88, 523.25, 587.33, 659.25, 698.46, 783.99, 880.00]
    note_audio = []
    for freq in freqs:
        note_audio.append(generate_sine_note(freq, 0.5))
    return np.concatenate(note_audio)


def generate_simple_melody() -> np.ndarray:
    freqs = [261.63, 329.63, 392.00, 329.63, 261.63]
    note_audio = []
    for freq in freqs:
        note_audio.append(generate_sine_note(freq, 0.5))
    return np.concatenate(note_audio)


def generate_major_triad() -> np.ndarray:
    c4 = generate_sine_note(261.63, 1.0)
    e4 = generate_sine_note(329.63, 1.0)
    g4 = generate_sine_note(392.00, 1.0)
    triad = c4 + e4 + g4
    return _normalize_peak(triad)


def generate_long_audio() -> np.ndarray:
    scale = generate_c_major_scale()
    repeated = np.concatenate([scale for _ in range(45)])
    extra = generate_c_major_scale()
    return np.concatenate([repeated, extra])


def generate_single_note_a4() -> np.ndarray:
    return generate_sine_note(440.0, 2.0)


def generate_all() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)

    _write_audio(AUDIO_DIR / "c_major_scale.wav", generate_c_major_scale())
    _write_audio(AUDIO_DIR / "g_major_scale.wav", generate_g_major_scale())
    _write_audio(AUDIO_DIR / "a_minor_scale.wav", generate_a_minor_scale())
    _write_audio(AUDIO_DIR / "simple_melody.wav", generate_simple_melody())
    _write_audio(AUDIO_DIR / "silence.wav", generate_silence(5.0))
    _write_audio(AUDIO_DIR / "noise.wav", generate_white_noise(3.0))
    _write_audio(AUDIO_DIR / "major_triad.wav", generate_major_triad())
    _write_audio(AUDIO_DIR / "long_audio.wav", generate_long_audio())
    _write_audio(AUDIO_DIR / "single_note_a4.wav", generate_single_note_a4())

    _write_json(
        GROUND_TRUTH_DIR / "c_major_scale.json",
        {
            "file": "c_major_scale.wav",
            "sample_rate": SAMPLE_RATE,
            "duration_s": 4.0,
            "expected_notes": [
                {"midi_pitch": 60, "start_time": 0.0, "end_time": 0.5, "frequency_hz": 261.63},
                {"midi_pitch": 62, "start_time": 0.5, "end_time": 1.0, "frequency_hz": 293.66},
                {"midi_pitch": 64, "start_time": 1.0, "end_time": 1.5, "frequency_hz": 329.63},
                {"midi_pitch": 65, "start_time": 1.5, "end_time": 2.0, "frequency_hz": 349.23},
                {"midi_pitch": 67, "start_time": 2.0, "end_time": 2.5, "frequency_hz": 392.00},
                {"midi_pitch": 69, "start_time": 2.5, "end_time": 3.0, "frequency_hz": 440.00},
                {"midi_pitch": 71, "start_time": 3.0, "end_time": 3.5, "frequency_hz": 493.88},
                {"midi_pitch": 72, "start_time": 3.5, "end_time": 4.0, "frequency_hz": 523.25},
            ],
            "expected_key": {"tonic": "C", "mode": "major"},
            "expected_tempo": 120.0,
            "expected_solfa": ["Do", "Re", "Mi", "Fa", "Sol", "La", "Ti", "Do"],
        },
    )

    _write_json(
        GROUND_TRUTH_DIR / "simple_melody.json",
        {
            "file": "simple_melody.wav",
            "expected_notes": [
                {"midi_pitch": 60, "start_time": 0.0, "end_time": 0.5},
                {"midi_pitch": 64, "start_time": 0.5, "end_time": 1.0},
                {"midi_pitch": 67, "start_time": 1.0, "end_time": 1.5},
                {"midi_pitch": 64, "start_time": 1.5, "end_time": 2.0},
                {"midi_pitch": 60, "start_time": 2.0, "end_time": 2.5},
            ],
            "expected_key": {"tonic": "C", "mode": "major"},
            "expected_solfa": ["Do", "Mi", "Sol", "Mi", "Do"],
        },
    )

    _write_json(
        GROUND_TRUTH_DIR / "major_triad.json",
        {
            "file": "major_triad.wav",
            "expected_notes": [{"midi_pitch": 60}, {"midi_pitch": 64}, {"midi_pitch": 67}],
            "note_count": 3,
            "polyphonic": True,
        },
    )


if __name__ == "__main__":
    generate_all()
    print("All fixtures generated successfully.")
    print(f"Audio files: tests/fixtures/audio/")
    print(f"Ground truth: tests/fixtures/ground_truth/")
