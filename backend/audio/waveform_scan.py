"""
waveform_scan.py — Streaming peak scan for waveform display.

Ported from StemDeck (app/pipeline/audio_stats.py, MIT licence).

scan_stem() makes a single streaming pass over a WAV file using
soundfile.blocks() so memory use is proportional to one block, not the
whole file. Returns per-bucket [min, max] pairs (for the waveform canvas)
and overall RMS (for stem presence display). Both come from channel 0 only
— for stem WAVs this is fine since Demucs outputs mono-compatible stereo.
"""

from __future__ import annotations

import math
from pathlib import Path


def scan_stem(path: Path, buckets: int = 1500) -> tuple[list[list[float]], float]:
    """
    Stream-scan the WAV at `path` in fixed-size blocks.

    Returns:
        peaks: list of [min, max] float pairs, len ≤ buckets
        rms:   float — root-mean-square amplitude over channel 0
    """
    import numpy as np
    import soundfile as sf

    info = sf.info(str(path))
    frames = info.frames
    if frames == 0:
        return [], 0.0

    blocksize = max(1, frames // buckets)
    result: list[list[float]] = []
    sumsq = 0.0
    n = 0

    for block in sf.blocks(str(path), blocksize=blocksize, dtype="float32", always_2d=True):
        ch = block[:, 0]
        if ch.size == 0:
            continue
        result.append([float(np.min(ch)), float(np.max(ch))])
        sumsq += float(np.sum(ch.astype(np.float64) ** 2))
        n += ch.size

    rms = math.sqrt(sumsq / n) if n else 0.0
    return result[:buckets], rms
