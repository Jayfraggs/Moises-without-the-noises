"""
pitch_shift.py — simple helper to shift a WAV file's pitch in-memory.

Provides a single function `shift_pitch(wav_path: Path, semitones: float) -> bytes`
that preserves the input sample rate and returns WAV bytes written to an
in-memory buffer (no disk writes).
"""

from pathlib import Path
import io
import librosa
import soundfile as sf
import numpy as np


def shift_pitch(wav_path: Path, semitones: float) -> bytes:
    """
    Load `wav_path`, shift by `semitones` (positive = up), and return WAV bytes.

    Preserves the original sample rate by loading with `sr=None`.
    """
    y, sr = librosa.load(str(wav_path), sr=None, mono=False)

    # librosa.effects.pitch_shift accepts mono (1D) or single-channel arrays.
    # If we have multi-channel audio, apply the transform per-channel.
    if y.ndim == 1:
        y_shifted = librosa.effects.pitch_shift(y, sr=sr, n_steps=semitones)
    else:
        y_shifted = np.stack([
            librosa.effects.pitch_shift(ch, sr=sr, n_steps=semitones)
            for ch in y
        ])

    buf = io.BytesIO()
    # soundfile expects shape (samples, channels) for multi-channel audio
    data_to_write = y_shifted.T if y_shifted.ndim > 1 else y_shifted
    sf.write(buf, data_to_write, sr, format="WAV")
    buf.seek(0)
    return buf.read()
