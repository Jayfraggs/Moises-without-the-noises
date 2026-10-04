"""
key_detection.py — Musical key detection using Albrecht-Shanahan profiles.

Albrecht-Shanahan profiles (2013) are derived from a corpus of popular music
and weight the natural-minor b7 highly — unlike Krumhansl-Schmuckler which was
derived from Bach chorales and biases toward harmonic minor. This matters for
rock/pop where the b7 is the diatonic seventh and rings out constantly.

Also computes LUFS integrated loudness and sample peak using pyloudnorm when
available (graceful fallback to None if not installed).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("mwtn.key_detection")

# Albrecht-Shanahan profiles rescaled so tonic weight ≈ 5.
_MAJOR_PROFILE = (5.47, 0.14, 2.55, 0.14, 3.15, 2.16, 0.37, 4.92, 0.21, 1.84, 0.18, 1.86)
_MINOR_PROFILE = (5.06, 0.14, 2.42, 2.42, 0.35, 1.96, 0.35, 4.16, 2.53, 0.28, 2.67, 0.62)
_PITCHES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

# When major and minor scores are within this fraction of the winner, prefer
# minor — pop/rock has a strong minor-mode prior.
_MINOR_TIE_BREAK_FRAC = 0.05


def _correlate(profile: tuple, chroma: list[float], shift: int) -> float:
    n = len(profile)
    rotated = [chroma[(i + shift) % n] for i in range(n)]
    mean_p = sum(profile) / n
    mean_c = sum(rotated) / n
    num = sum((profile[i] - mean_p) * (rotated[i] - mean_c) for i in range(n))
    denom_p = sum((profile[i] - mean_p) ** 2 for i in range(n)) ** 0.5
    denom_c = sum((rotated[i] - mean_c) ** 2 for i in range(n)) ** 0.5
    if denom_p == 0 or denom_c == 0:
        return 0.0
    return num / (denom_p * denom_c)


def _detect_key(chroma_mean: list[float]) -> tuple[str, str, int]:
    """
    Returns (label, scale_name, confidence_pct).
    label:          e.g. "G# min"
    scale_name:     "Major" or "Natural Minor"
    confidence_pct: 0-100
    """
    raw: list[tuple] = []
    for shift in range(12):
        root_strength = chroma_mean[shift]
        pearson_maj = _correlate(_MAJOR_PROFILE, chroma_mean, shift)
        pearson_min = _correlate(_MINOR_PROFILE, chroma_mean, shift)
        raw.append((pearson_maj * root_strength, pearson_maj, f"{_PITCHES[shift]} maj", shift))
        raw.append((pearson_min * root_strength, pearson_min, f"{_PITCHES[shift]} min", shift))
    raw.sort(key=lambda x: x[0], reverse=True)

    best_maj = next(c for c in raw if c[2].endswith("maj"))
    best_min = next(c for c in raw if c[2].endswith("min"))

    gap = abs(best_maj[0] - best_min[0])
    threshold = max(abs(best_maj[0]), abs(best_min[0])) * _MINOR_TIE_BREAK_FRAC
    winner = (best_maj if best_maj[0] > best_min[0] else best_min) if gap > threshold else best_min

    runner_up = next(c for c in raw if c[2] != winner[2])
    confidence_score = winner[0] - runner_up[0]
    confidence_pct = max(0, min(100, round(confidence_score / 0.15 * 100)))

    label = winner[2]
    scale_name = "Major" if label.endswith("maj") else "Natural Minor"
    return label, scale_name, confidence_pct


def _measure_loudness(y: object, sr: int) -> tuple[float | None, float | None]:
    """Integrated loudness (LUFS) and sample peak (dBFS). Both may be None."""
    import numpy as np

    if y is None or getattr(y, "size", 0) == 0:
        return None, None

    peak_lin = float(np.abs(y).max())
    peak_db = 20.0 * float(np.log10(peak_lin)) if peak_lin > 1e-9 else None

    lufs: float | None = None
    try:
        import pyloudnorm as pyln
        meter = pyln.Meter(sr)
        lufs_raw = float(meter.integrated_loudness(y))
        if np.isfinite(lufs_raw):
            lufs = lufs_raw
    except (ImportError, ValueError):
        pass
    return lufs, peak_db


def _ffmpeg_bin() -> str:
    found = shutil.which("ffmpeg")
    return found if found else "ffmpeg"


def _load_audio_ffmpeg(source: str, sr: int = 22050, duration: float | None = 180.0) -> tuple | None:
    """Decode audio to mono float32 numpy array via ffmpeg subprocess."""
    import numpy as np

    path = Path(source)
    if not path.is_file():
        logger.warning("key_detection: source not found: %s", source)
        return None

    cmd = [
        _ffmpeg_bin(), "-nostdin", "-loglevel", "error",
        "-i", str(path),
        "-ac", "1", "-ar", str(sr), "-f", "f32le",
    ]
    if duration is not None:
        cmd += ["-t", str(duration)]
    cmd.append("-")

    try:
        proc = subprocess.run(cmd, capture_output=True, check=True, timeout=120)
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning("key_detection: ffmpeg failed for %s: %s", source, e)
        return None

    y = np.frombuffer(proc.stdout, dtype=np.float32)
    if y.size == 0:
        return None
    return y, sr


def detect_key(audio_path: str) -> dict:
    """
    Returns:
        {
          "key":           str,         # e.g. "A min"
          "scale":         str,         # "Natural Minor" or "Major"
          "key_confidence": int,        # 0-100
          "lufs":          float|None,
          "peak_db":       float|None,
          "dynamic_range": float|None,
        }
    """
    try:
        import librosa
    except ImportError:
        logger.warning("librosa not available — key detection skipped")
        return {"key": None, "scale": None, "key_confidence": None,
                "lufs": None, "peak_db": None, "dynamic_range": None}

    loaded = _load_audio_ffmpeg(audio_path, sr=22050, duration=180.0)
    if loaded is None:
        # Fallback to librosa.load for formats ffmpeg might not handle
        try:
            y, sr = librosa.load(audio_path, sr=22050, mono=True, duration=180.0)
        except Exception as e:
            logger.warning("key_detection: librosa.load also failed: %s", e)
            return {"key": None, "scale": None, "key_confidence": None,
                    "lufs": None, "peak_db": None, "dynamic_range": None}
    else:
        y, sr = loaded

    try:
        y_harmonic, _ = librosa.effects.hpss(y)
        chroma = librosa.feature.chroma_cqt(y=y_harmonic, sr=sr)
        chroma_mean = chroma.mean(axis=1).tolist()

        if any(chroma_mean):
            key, scale, confidence = _detect_key(chroma_mean)
        else:
            key, scale, confidence = None, None, None

        lufs, peak_db = _measure_loudness(y, sr)
        dynamic_range: float | None = None
        if lufs is not None and peak_db is not None:
            dynamic_range = round(peak_db - lufs, 1)

        return {
            "key": key,
            "scale": scale,
            "key_confidence": confidence,
            "lufs": round(lufs, 1) if lufs is not None else None,
            "peak_db": round(peak_db, 1) if peak_db is not None else None,
            "dynamic_range": dynamic_range,
        }
    except Exception as e:
        logger.exception("key_detection failed for %s: %s", audio_path, e)
        return {"key": None, "scale": None, "key_confidence": None,
                "lufs": None, "peak_db": None, "dynamic_range": None}
