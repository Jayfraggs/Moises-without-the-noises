"""Beat grid and meter analysis utilities for MWTN."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import librosa

from backend.audio.duration_mapper import TICKS_PER_BEAT


@dataclass
class TimeSig:
    numerator: int
    denominator: int

    def beats_per_measure(self) -> int:
        return self.numerator

    def ticks_per_measure(self) -> int:
        return self.numerator * TICKS_PER_BEAT


SUPPORTED_TIME_SIGNATURES = [
    TimeSig(2, 4),
    TimeSig(3, 4),
    TimeSig(4, 4),
    TimeSig(6, 8),
]


@dataclass
class BeatGridEntry:
    beat_index: int
    time_s: float
    measure_number: int
    beat_in_measure: int
    is_downbeat: bool
    tempo_bpm: float


@dataclass
class BeatGrid:
    entries: list[BeatGridEntry]
    time_sig: TimeSig
    tempo_map: list[dict]
    assumed_time_sig: bool
    source: str

    def get_beat_at_time(self, time_s: float) -> BeatGridEntry | None:
        """Return the beat entry closest to time_s (before or at)."""
        if not self.entries:
            return None
        if time_s <= self.entries[0].time_s:
            return self.entries[0]
        if time_s >= self.entries[-1].time_s:
            return self.entries[-1]

        best = self.entries[0]
        for entry in self.entries[1:]:
            if entry.time_s <= time_s:
                best = entry
        return best

    def get_measure_range(self, measure_number: int) -> tuple[float, float] | None:
        """Return (start_s, end_s) for a given measure number."""
        if not self.entries or measure_number < 1:
            return None

        entries_in_measure = [e for e in self.entries if e.measure_number == measure_number]
        if not entries_in_measure:
            return None

        start_s = min(e.time_s for e in entries_in_measure)
        next_measure_start = min(
            (e.time_s for e in self.entries if e.measure_number == measure_number + 1),
            default=None,
        )
        end_s = next_measure_start if next_measure_start is not None else self.entries[-1].time_s
        return start_s, end_s

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict for caching as beats.json."""
        return {
            "entries": [
                {
                    "beat_index": int(entry.beat_index),
                    "time_s": float(entry.time_s),
                    "measure_number": int(entry.measure_number),
                    "beat_in_measure": int(entry.beat_in_measure),
                    "is_downbeat": bool(entry.is_downbeat),
                    "tempo_bpm": float(entry.tempo_bpm),
                }
                for entry in self.entries
            ],
            "time_sig": {
                "numerator": int(self.time_sig.numerator),
                "denominator": int(self.time_sig.denominator),
            },
            "tempo_map": [
                {
                    "beat_index": int(item["beat_index"]),
                    "time_s": float(item["time_s"]),
                    "bpm": float(item["bpm"]),
                }
                for item in self.tempo_map
            ],
            "assumed_time_sig": bool(self.assumed_time_sig),
            "source": str(self.source),
            "beats": [float(entry.time_s) for entry in self.entries],
            "bpm": float(self.tempo_map[0]["bpm"]) if self.tempo_map else 120.0,
        }


def detect_time_signature(beat_times: list[float], downbeat_times: list[float]) -> tuple[TimeSig, bool]:
    """Detect a supported time signature from beats and downbeats."""
    if not downbeat_times or len(downbeat_times) < 2:
        return TimeSig(4, 4), True

    counts: list[int] = []
    for prev_downbeat, next_downbeat in zip(downbeat_times, downbeat_times[1:]):
        count = sum(1 for beat in beat_times if prev_downbeat <= beat < next_downbeat)
        if count > 0:
            counts.append(count)

    if not counts:
        return TimeSig(4, 4), True

    average_beats = sum(counts) / len(counts)
    candidate = round(average_beats)

    if candidate not in {2, 3, 4, 6}:
        return TimeSig(4, 4), True

    for ts in SUPPORTED_TIME_SIGNATURES:
        if ts.numerator == candidate:
            return ts, False

    return TimeSig(4, 4), True


def build_beat_grid(beat_times: list[float], downbeat_times: list[float], time_sig: TimeSig) -> BeatGrid:
    """Construct a BeatGrid from detected beat and downbeat times."""
    if not beat_times:
        return BeatGrid(entries=[], time_sig=time_sig, tempo_map=[], assumed_time_sig=False, source="librosa")

    entries: list[BeatGridEntry] = []
    tempo_map: list[dict] = []

    for i, beat_time in enumerate(beat_times):
        measure_number = (i // time_sig.numerator) + 1
        beat_in_measure = (i % time_sig.numerator) + 1
        is_downbeat = beat_in_measure == 1

        if i == 0:
            if len(beat_times) > 1:
                tempo_bpm = 60.0 / max(beat_times[1] - beat_time, 0.001)
            else:
                tempo_bpm = 120.0
        elif i == len(beat_times) - 1:
            tempo_bpm = 60.0 / max(beat_time - beat_times[i - 1], 0.001)
        else:
            prev_t = beat_times[i - 1]
            next_t = beat_times[i + 1]
            bpm_prev = 60.0 / max(beat_time - prev_t, 0.001)
            bpm_next = 60.0 / max(next_t - beat_time, 0.001)
            tempo_bpm = (bpm_prev + bpm_next) / 2.0

        entries.append(
            BeatGridEntry(
                beat_index=i,
                time_s=float(beat_time),
                measure_number=measure_number,
                beat_in_measure=beat_in_measure,
                is_downbeat=is_downbeat,
                tempo_bpm=float(tempo_bpm),
            )
        )

    if entries:
        tempo_map.append({"beat_index": 0, "time_s": entries[0].time_s, "bpm": entries[0].tempo_bpm})
        for idx in range(1, len(entries)):
            if abs(entries[idx].tempo_bpm - tempo_map[-1]["bpm"]) > 2.0:
                tempo_map.append({"beat_index": idx, "time_s": entries[idx].time_s, "bpm": entries[idx].tempo_bpm})

    return BeatGrid(
        entries=entries,
        time_sig=time_sig,
        tempo_map=tempo_map,
        assumed_time_sig=False,
        source="librosa",
    )


def track_beats_madmom(audio_path: str | Path, device: str = "cpu") -> tuple[list[float], list[float]]:
    """
    Returns (beat_times, downbeat_times) using madmom RNNBeatProcessor + RNNDownBeatProcessor.
    Raises ImportError if madmom not installed.
    """
    try:
        from madmom.features.beats import RNNBeatProcessor, DBNBeatTrackingProcessor
        from madmom.features.downbeats import RNNDownBeatProcessor, DBNDownBeatTrackingProcessor
    except ImportError as exc:  # pragma: no cover - import guard
        raise ImportError("madmom is not installed") from exc

    beat_proc = RNNBeatProcessor()(str(audio_path))
    beat_times = DBNBeatTrackingProcessor(fps=100)(beat_proc).tolist()

    downbeat_proc = RNNDownBeatProcessor()(str(audio_path))
    downbeat_activations = DBNDownBeatTrackingProcessor(beats_per_bar=[2, 3, 4, 6], fps=100)(downbeat_proc)
    downbeat_times = [float(row[0]) for row in downbeat_activations if int(row[1]) == 1]

    return beat_times, downbeat_times


def track_beats_librosa(audio_path: str | Path) -> tuple[list[float], list[float]]:
    """
    Returns (beat_times, downbeat_times) using librosa.
    downbeat_times is approximate: every 4th beat from the first.
    """
    audio, sr = librosa.load(str(audio_path), sr=None, mono=True)
    _, beat_frames = librosa.beat.beat_track(y=audio, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    downbeat_times = beat_times[::4]
    return beat_times, downbeat_times


def analyze_rhythm(audio_path: str | Path, device: str = "cpu") -> BeatGrid:
    """Top-level function. Tries madmom first; falls back to librosa."""
    try:
        beat_times, downbeat_times = track_beats_madmom(audio_path, device)
        source = "madmom"
    except ImportError:
        beat_times, downbeat_times = track_beats_librosa(audio_path)
        source = "librosa"

    time_sig, assumed = detect_time_signature(beat_times, downbeat_times)
    grid = build_beat_grid(beat_times, downbeat_times, time_sig)
    grid.source = source
    grid.assumed_time_sig = assumed
    return grid


__all__ = [
    "TimeSig",
    "SUPPORTED_TIME_SIGNATURES",
    "BeatGridEntry",
    "BeatGrid",
    "detect_time_signature",
    "build_beat_grid",
    "track_beats_madmom",
    "track_beats_librosa",
    "analyze_rhythm",
]
