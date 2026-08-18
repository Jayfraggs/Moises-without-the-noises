"""
pitch.py — Pitch shifting via librosa (offline/server-side).

This is for the export path: if the user wants to download a stem
transposed by N semitones, we process it here and return a WAV.

For REAL-TIME pitch shifting during playback, this is NOT the right
module — that needs to happen in the browser via Web Audio API /
AudioWorklet. See frontend/src/AudioEngine.js for the playback side.

librosa.effects.pitch_shift uses a phase vocoder under the hood.
Quality is decent for small shifts (±6 semitones); larger shifts
introduce artifacts, especially on vocals. This is a known limitation
of phase vocoders vs. more sophisticated time-domain methods (e.g.
Rubber Band Library), but librosa is zero-dependency and good enough
for a v1.

Speed-without-pitch-change (time stretching) is also here:
librosa.effects.time_stretch. Same phase vocoder, same trade-offs.
"""

import io
import librosa
import soundfile as sf
import numpy as np


def pitch_shift_wav(audio_path: str, semitones: float) -> bytes:
    """
    Returns WAV bytes of the audio shifted by `semitones` semitones.
    Positive = up, negative = down. Range: -12 to +12 recommended.
    """
    y, sr = librosa.load(audio_path, sr=None, mono=False)

    # librosa.effects.pitch_shift expects mono or (channels, samples).
    # If stereo (2D), process each channel independently to avoid the
    # "too many dimensions" error.
    if y.ndim == 1:
        y_shifted = librosa.effects.pitch_shift(y, sr=sr, n_steps=semitones)
    else:
        y_shifted = np.stack([
            librosa.effects.pitch_shift(ch, sr=sr, n_steps=semitones)
            for ch in y
        ])

    buf = io.BytesIO()
    sf.write(buf, y_shifted.T if y_shifted.ndim > 1 else y_shifted, sr, format="WAV")
    buf.seek(0)
    return buf.read()


def time_stretch_wav(audio_path: str, rate: float) -> bytes:
    """
    Returns WAV bytes time-stretched by `rate` without changing pitch.
    rate > 1.0 = faster, rate < 1.0 = slower.
    Range: 0.5–2.0 recommended; outside that, artifact quality degrades.
    """
    y, sr = librosa.load(audio_path, sr=None, mono=False)

    if y.ndim == 1:
        y_stretched = librosa.effects.time_stretch(y, rate=rate)
    else:
        y_stretched = np.stack([
            librosa.effects.time_stretch(ch, rate=rate)
            for ch in y
        ])

    buf = io.BytesIO()
    sf.write(buf, y_stretched.T if y_stretched.ndim > 1 else y_stretched, sr, format="WAV")
    buf.seek(0)
    return buf.read()
