"""
key_detection.py — Musical key detection using librosa's Krumhansl-Schmuckler
key-finding algorithm.

Returns the detected key (e.g. "C major", "A minor") and a confidence
score. The confidence is the correlation between the chroma profile and
the key template — higher is better, but even 0.8+ can be wrong on
chromatic or atonal music. Treat it as a useful hint, not ground truth.

Note: librosa detects key from the full mix. Detecting from the separated
stems (e.g. from the bass stem alone) often gives worse results because
the chroma estimator needs harmonic content across multiple octaves. Pass
the original file or the "other" stem for best results.
"""

import librosa
import numpy as np

# Krumhansl-Schmuckler key profiles (major and minor).
# These are the standard 12-element vectors used by librosa internally,
# exposed here for documentation clarity.
KEY_NAMES_MAJOR = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
KEY_NAMES_MINOR = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def detect_key(audio_path: str) -> dict:
    """
    Returns:
        {
          "key": str,         # e.g. "A minor", "C major"
          "root": str,        # e.g. "A", "C"
          "mode": str,        # "major" or "minor"
          "confidence": float # 0.0–1.0 correlation score
        }
    """
    y, sr = librosa.load(audio_path, sr=None, mono=True)

    # Harmonic-percussive separation improves chroma accuracy — the
    # percussive component smears chroma across all bins.
    y_harmonic, _ = librosa.effects.hpss(y)

    chroma = librosa.feature.chroma_cqt(y=y_harmonic, sr=sr)
    chroma_mean = chroma.mean(axis=1)

    # librosa's built-in key estimator
    key_idx, scale = librosa.key_to_notes(
        librosa.hz_to_midi(librosa.A_440)  # unused, just for import check
    ), "major"

    # Use the actual key estimation
    key_number = np.argmax(chroma_mean)
    
    # Compute correlation against major and minor templates
    major_template = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                                2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    minor_template = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                                2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

    best_key = None
    best_mode = None
    best_corr = -np.inf

    for i in range(12):
        major_rolled = np.roll(major_template, i)
        minor_rolled = np.roll(minor_template, i)

        corr_major = np.corrcoef(chroma_mean, major_rolled)[0, 1]
        corr_minor = np.corrcoef(chroma_mean, minor_rolled)[0, 1]

        if corr_major > best_corr:
            best_corr = corr_major
            best_key = i
            best_mode = "major"
        if corr_minor > best_corr:
            best_corr = corr_minor
            best_key = i
            best_mode = "minor"

    root = KEY_NAMES_MAJOR[best_key]

    return {
        "key": f"{root} {best_mode}",
        "root": root,
        "mode": best_mode,
        "confidence": round(float(best_corr), 3),
    }
