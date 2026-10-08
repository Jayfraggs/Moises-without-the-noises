"""Unified beat analysis entry point with backward-compatible cache handling."""

from __future__ import annotations

import json
import os
from pathlib import Path

from backend.audio.meter import BeatGrid, BeatGridEntry, TimeSig, analyze_rhythm, build_beat_grid

BEATS_JSON_SCHEMA_VERSION = "2.0"


def _deserialize_beat_grid(payload: dict) -> BeatGrid:
    """Deserialize a cached BeatGrid from JSON data."""
    time_sig_data = payload.get("time_sig", {"numerator": 4, "denominator": 4})
    time_sig = TimeSig(
        numerator=int(time_sig_data.get("numerator", 4)),
        denominator=int(time_sig_data.get("denominator", 4)),
    )

    entries = [
        BeatGridEntry(
            beat_index=int(entry.get("beat_index", idx)),
            time_s=float(entry.get("time_s", 0.0)),
            measure_number=int(entry.get("measure_number", 1)),
            beat_in_measure=int(entry.get("beat_in_measure", 1)),
            is_downbeat=bool(entry.get("is_downbeat", False)),
            tempo_bpm=float(entry.get("tempo_bpm", 120.0)),
        )
        for idx, entry in enumerate(payload.get("entries", []))
    ]

    tempo_map = [
        {
            "beat_index": int(item.get("beat_index", 0)),
            "time_s": float(item.get("time_s", 0.0)),
            "bpm": float(item.get("bpm", 120.0)),
        }
        for item in payload.get("tempo_map", [])
    ]

    return BeatGrid(
        entries=entries,
        time_sig=time_sig,
        tempo_map=tempo_map,
        assumed_time_sig=bool(payload.get("assumed_time_sig", True)),
        source=str(payload.get("source", "librosa")),
    )


def _legacy_beat_grid_from_cache(payload: dict) -> BeatGrid:
    """Reconstruct a minimal BeatGrid from legacy beats.json data without reanalysis."""
    bpm_value = float(payload.get("bpm", 120.0))
    beat_times = [float(value) for value in payload.get("beats", [])]

    if not beat_times:
        return BeatGrid(
            entries=[],
            time_sig=TimeSig(4, 4),
            tempo_map=[],
            assumed_time_sig=True,
            source="legacy",
        )

    downbeat_times = beat_times[::4]
    grid = build_beat_grid(beat_times, downbeat_times, TimeSig(4, 4))
    grid.assumed_time_sig = True
    grid.source = "legacy"

    if not grid.tempo_map:
        grid.tempo_map = [{"beat_index": 0, "time_s": beat_times[0], "bpm": bpm_value}]
    return grid


def write_beats_json(grid: BeatGrid, path: Path) -> None:
    """Write BeatGrid to disk as beats.json. Atomic write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = grid.to_dict()
    data["schema_version"] = BEATS_JSON_SCHEMA_VERSION
    data["bpm"] = grid.tempo_map[0]["bpm"] if grid.tempo_map else 120.0
    data["beats"] = [entry.time_s for entry in grid.entries]

    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_or_analyze_beats(
    audio_path: Path,
    cache_path: Path,
    force_reanalyze: bool = False,
    device: str = "cpu",
) -> BeatGrid:
    """
    Load beats from cache if available and valid. Otherwise run full analysis.
    cache_path: path to beats.json inside the song directory.
    """
    if not force_reanalyze and cache_path.exists():
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            schema_version = payload.get("schema_version")
            if schema_version == BEATS_JSON_SCHEMA_VERSION:
                return _deserialize_beat_grid(payload)
            if schema_version is None:
                grid = _legacy_beat_grid_from_cache(payload)
                write_beats_json(grid, cache_path)
                return grid
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass

    grid = analyze_rhythm(audio_path, device=device)
    write_beats_json(grid, cache_path)
    return grid


def get_tempo_at_time(grid: BeatGrid, time_s: float) -> float:
    """Return BPM from the tempo map at a given timestamp."""
    if not grid.tempo_map:
        return 120.0

    for entry in reversed(grid.tempo_map):
        if time_s >= float(entry["time_s"]):
            return float(entry["bpm"])

    return float(grid.tempo_map[0]["bpm"])


__all__ = [
    "BEATS_JSON_SCHEMA_VERSION",
    "write_beats_json",
    "load_or_analyze_beats",
    "get_tempo_at_time",
]
