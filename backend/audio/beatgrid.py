"""
beatgrid.py — Full-length beat grid extraction for the click track.

Ported from StemDeck app/pipeline/beatgrid.py (Apache-2.0).

The analyze.py module estimates BPM from the first 180 s of audio (good
for the metadata chip). This module tracks beats over the FULL track from
the isolated drums stem so the click track doesn't drift. Output is
stems/<song_id>/beats.json, which the /api/songs/{id}/beats endpoint
serves (and which the existing simpler detect_beats() in bpm.py falls
back to when this isn't available).

Unlike StemDeck we run against stems that already exist in the data dir
rather than a jobs pipeline, so path handling is simplified accordingly.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("mwtn.beatgrid")

_MIN_BEATS = 8
_MIN_BPM = 30.0
_MAX_BPM = 300.0
_GRID_OUTLIER_FRAC = 0.10
_EXTRAPOLATE_EDGE_BEATS = 9
_SOURCE_PREFERENCE = ("drums", "other", "bass", "vocals")


def _pick_source(stems_dir: Path) -> tuple[Path, str] | None:
    for name in _SOURCE_PREFERENCE:
        candidate = stems_dir / f"{name}.wav"
        if candidate.is_file():
            return candidate, name
    return None


def _sanitize(beat_times: object, duration: float) -> list[float]:
    import numpy as np

    arr = np.asarray(beat_times, dtype=float).ravel()
    arr = arr[np.isfinite(arr)]
    arr = arr[(arr >= 0.0) & (arr <= duration)]
    arr.sort()
    if arr.size == 0:
        return []
    keep = np.concatenate(([True], np.diff(arr) > 1e-3))
    return [round(float(t), 6) for t in arr[keep]]


def _fill_interior_gaps(beats: list[float]) -> tuple[list[float], int]:
    """Subdivide gaps left by the detector in drum-free sections."""
    import numpy as np

    if len(beats) < 4:
        return beats, 0

    arr = np.asarray(beats, dtype=float)
    intervals = np.diff(arr)
    win = 4  # local window for period estimate

    out: list[float] = [float(arr[0])]
    inserted = 0
    for i, d in enumerate(intervals):
        lo = max(0, i - win)
        hi = min(len(intervals), i + win + 1)
        neighbourhood = np.concatenate([intervals[lo:i], intervals[i + 1 : hi]])
        period = float(np.median(neighbourhood)) if neighbourhood.size else float(np.median(intervals))
        if period > 0:
            k = int(round(d / period))
            if k >= 2 and abs(d / k - period) < 0.08 * period:
                for j in range(1, k):
                    out.append(float(arr[i] + d * j / k))
                    inserted += 1
        out.append(float(arr[i + 1]))

    return out, inserted


def _extend_to_track_edges(
    beats: list[float], duration: float
) -> tuple[list[float], int, int]:
    import numpy as np

    if len(beats) < 3:
        return beats, 0, 0

    arr = np.asarray(beats, dtype=float)
    edge = min(_EXTRAPOLATE_EDGE_BEATS, len(arr))
    head_iv = float(np.median(np.diff(arr[:edge])))
    tail_iv = float(np.median(np.diff(arr[-edge:])))
    if head_iv <= 0 or tail_iv <= 0:
        return beats, 0, 0

    head: list[float] = []
    t = arr[0] - head_iv
    while t >= 0.0:
        head.append(t)
        t -= head_iv
    head.reverse()

    tail: list[float] = []
    t = arr[-1] + tail_iv
    while t <= duration:
        tail.append(t)
        t += tail_iv

    return head + [float(b) for b in arr] + tail, len(head), len(tail)


def _enforce_grid_consistency(beats: list[float]) -> tuple[list[float], int]:
    import numpy as np

    if len(beats) < 3:
        return beats, 0

    arr = np.asarray(beats, dtype=float)
    median_interval = float(np.median(np.diff(arr)))
    if median_interval <= 0:
        return beats, 0
    tol = median_interval * _GRID_OUTLIER_FRAC

    out = arr.copy()
    predicted = (arr[:-2] + arr[2:]) / 2.0
    bad = np.abs(arr[1:-1] - predicted) > tol
    out[1:-1] = np.where(bad, predicted, arr[1:-1])
    corrected = int(bad.sum())

    first_pred = out[1] - (out[2] - out[1])
    if abs(out[0] - first_pred) > tol:
        out[0] = first_pred
        corrected += 1
    last_pred = out[-2] + (out[-2] - out[-3])
    if abs(out[-1] - last_pred) > tol:
        out[-1] = last_pred
        corrected += 1

    return [float(t) for t in out], corrected


def compute_beat_grid(stems_dir: Path) -> dict | None:
    """
    Detect beat times across the full track using the drums stem (preferred).
    Writes stems_dir/beats.json and returns the grid dict, or None on failure.
    Never raises — a missing grid degrades the click track, it must not break imports.
    """
    try:
        import librosa
        import numpy as np
    except ImportError:
        logger.warning("librosa not installed — skipping beat grid")
        return None

    try:
        picked = _pick_source(stems_dir)
        if picked is None:
            logger.warning("beatgrid: no usable source stem in %s", stems_dir)
            return None
        source, source_label = picked

        from audio.bpm import detect_beats
        result = detect_beats(str(source))
        beats_raw = result.get("beats", [])
        bpm_raw = result.get("bpm", 0)
        tempo_stability = result.get("tempo_stability")

        if not beats_raw or len(beats_raw) < _MIN_BEATS:
            logger.warning("beatgrid: only %d beats detected", len(beats_raw))
            return None

        import soundfile as sf
        info = sf.info(str(source))
        duration = float(info.frames) / info.samplerate

        beats = _sanitize(beats_raw, duration)
        if len(beats) < _MIN_BEATS:
            return None

        # Gap fill then consistency pass
        beats, gap_filled = _fill_interior_gaps(beats)
        beats = _sanitize(beats, duration)
        beats, corrected_count = _enforce_grid_consistency(beats)
        beats = _sanitize(beats, duration)

        if len(beats) < _MIN_BEATS:
            return None

        beats_arr = np.asarray(beats, dtype=float)
        median_interval = float(np.median(np.diff(beats_arr)))
        if median_interval <= 0:
            return None
        bpm = 60.0 / median_interval
        if not (_MIN_BPM <= bpm <= _MAX_BPM):
            logger.warning("beatgrid: implausible %.1f BPM", bpm)
            return None

        intervals = np.diff(beats_arr)
        cv = float(intervals.std() / median_interval)

        beats, head_added, tail_added = _extend_to_track_edges(beats, duration)
        beats = _sanitize(beats, duration)

        if len(beats) < _MIN_BEATS:
            return None

        final_median = float(np.median(np.diff(np.asarray(beats, dtype=float))))
        bpm = 60.0 / final_median if final_median > 0 else bpm

        grid = {
            "version": 1,
            "source": source_label,
            "detector": "librosa",
            "bars": [],  # downbeat detection requires beat_this; not available locally
            "bpm": round(bpm, 3),
            "duration": round(duration, 3),
            "confidence": None,
            "interval_cv": round(cv, 4),
            "tempo_stability": tempo_stability,
            "gap_filled": gap_filled,
            "corrected": corrected_count,
            "extrapolated_head": head_added,
            "extrapolated_tail": tail_added,
            "beats": [round(float(b), 6) for b in beats],
        }

        tmp = stems_dir / "beats.json.tmp"
        tmp.write_text(json.dumps(grid), encoding="utf-8")
        tmp.replace(stems_dir / "beats.json")
        logger.info(
            "beatgrid: %d beats, %.2f BPM, cv=%.3f (source=%s)",
            len(beats), bpm, cv, source_label
        )
        return grid
    except Exception:
        logger.exception("beatgrid failed for %s", stems_dir)
        return None
