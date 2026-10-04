"""
bpm.py — Beat & tempo detection using librosa.

Returns BPM, beat timestamps, downbeats, and tempo stability. Stability
is derived from the coefficient of variation of inter-beat intervals:
CV=0 is perfectly metronomic, normalised to 0-100 (higher = more stable).

Note: librosa's beat tracker has a 120 BPM prior. Very fast (>160 BPM) or
very slow (<60 BPM) material may resolve to half/double time. For the Colab
pipeline, the notebook runs the same detector — the mwtn project defers
beat_this (the neural tracker) to a future v2 since it requires GPU or a
local model download that contradicts the Colab-first design.
"""

from __future__ import annotations

import logging

import librosa
import numpy as np

logger = logging.getLogger("mwtn.bpm")


def detect_beats(audio_path: str) -> dict:
    """
    Returns:
        {
          "bpm":             float,
          "beats":           [float, ...],   # beat timestamps in seconds
          "downbeats":       [float, ...],   # every 4th beat (estimated)
          "tempo_stability": int | None,     # 0-100, higher = more stable
        }
    """
    y, sr = librosa.load(audio_path, sr=None, mono=True)

    # Harmonic/percussive separation: beat tracking on percussive component
    # gives a cleaner onset envelope.
    try:
        _, y_percussive = librosa.effects.hpss(y)
    except Exception:
        y_percussive = y

    tempo_arr, beat_frames = librosa.beat.beat_track(
        y=y_percussive, sr=sr, units="frames", trim=False
    )
    try:
        tempo = float(tempo_arr[0])
    except (TypeError, IndexError):
        tempo = float(tempo_arr)

    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    downbeats = beat_times[::4]

    # Tempo stability: 1 - CV of inter-beat intervals, clamped 0-100.
    tempo_stability: int | None = None
    if len(beat_times) > 2:
        intervals = np.diff(beat_times)
        mean_iv = float(intervals.mean())
        if mean_iv > 0:
            cv = float(intervals.std() / mean_iv)
            tempo_stability = max(0, min(100, round((1 - min(cv, 1)) * 100)))

    return {
        "bpm": round(float(np.squeeze(tempo)), 2),
        "beats": [round(t, 4) for t in beat_times],
        "downbeats": [round(t, 4) for t in downbeats],
        "tempo_stability": tempo_stability,
    }
