"""Offline chord detection with an optional autochord engine and librosa fallback."""
from __future__ import annotations

import json
from pathlib import Path

import librosa
import numpy as np

try:  # Supports both the backend package and the legacy backend-directory entry point.
    from backend.audio.harmonic_context import KeyMap, PITCH_CLASS_TO_NAME
    from backend.audio.meter import BeatGrid
    from backend.schema.events import ChordEvent
except ModuleNotFoundError:  # pragma: no cover - exercised by legacy backend tests
    from audio.harmonic_context import KeyMap, PITCH_CLASS_TO_NAME
    from audio.meter import BeatGrid
    from schema.events import ChordEvent


QUALITY_MAP = {
    "maj": "major", "min": "minor", "dim": "diminished", "aug": "augmented",
    "7": "dominant7", "maj7": "major7", "min7": "minor7", "dim7": "diminished7",
    "hdim7": "half-diminished7", "sus2": "sus2", "sus4": "sus4", "": "major",
}
CHORD_TEMPLATES: dict[str, np.ndarray] = {
    "major": np.array([1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0], dtype=float),
    "minor": np.array([1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0], dtype=float),
}
_SILENCE_LABELS = {"N", "N/A", "NA", "NONE", "NO_CHORD", "SILENCE"}


def parse_chord_label(label: str) -> tuple[str, str, list[str]]:
    """Parse an autochord label into root, normalized quality, and extensions."""
    normalized = label.strip()
    if normalized.upper() in _SILENCE_LABELS:
        return "N", "none", []
    root, separator, suffix = normalized.partition(":")
    if not root:
        raise ValueError(f"Chord label has no root: {label!r}")
    raw_quality = suffix.lower() if separator else ""
    quality = QUALITY_MAP.get(raw_quality, raw_quality or "major")
    extensions = ["7"] if raw_quality in {"7", "maj7", "min7", "dim7", "hdim7"} else []
    return root, quality, extensions


def detect_chords_autochord(audio_path: str | Path) -> list[tuple[float, float, str, float]]:
    """Run autochord and return (start, end, label, confidence) segments."""
    import autochord

    chords = autochord.recognize(str(audio_path))
    return [(float(chord[0]), float(chord[1]), str(chord[2]), 1.0) for chord in chords]


def detect_chords_librosa(
    audio_path: str | Path, hop_length: int = 4096
) -> list[tuple[float, float, str, float]]:
    """Use chroma-template matching when the optional neural engine is unavailable."""
    y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    if y.size == 0:
        return []
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length)
    if chroma.shape[1] == 0:
        return []
    times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=hop_length)
    results: list[tuple[float, float, str, float]] = []
    for index, frame_chroma in enumerate(chroma.T):
        best_root, best_quality, best_score = 0, "major", -1.0
        for root_pc in range(12):
            rolled = np.roll(frame_chroma, -root_pc)
            for quality, template in CHORD_TEMPLATES.items():
                score = float(np.dot(rolled, template) / (np.linalg.norm(rolled) * np.linalg.norm(template) + 1e-8))
                if score > best_score:
                    best_root, best_quality, best_score = root_pc, quality, score
        start_s = float(times[index])
        end_s = float(times[index + 1]) if index + 1 < len(times) else start_s + (hop_length / sr)
        results.append((start_s, end_s, f"{PITCH_CLASS_TO_NAME[best_root]}:{best_quality[:3]}", best_score))
    return _merge_consecutive_chords(results)


def _merge_consecutive_chords(
    raw: list[tuple[float, float, str, float]]
) -> list[tuple[float, float, str, float]]:
    """Merge adjacent frames which resolve to the same chord label."""
    merged: list[tuple[float, float, str, float]] = []
    for start_s, end_s, label, confidence in raw:
        if merged and merged[-1][2] == label:
            previous_start, _previous_end, previous_label, previous_confidence = merged[-1]
            merged[-1] = (previous_start, end_s, previous_label, max(previous_confidence, confidence))
        else:
            merged.append((start_s, end_s, label, confidence))
    return merged


def align_chords_to_beat_grid(
    chord_segments: list[tuple[float, float, str, float]],
    grid: BeatGrid,
    key_map: KeyMap,
    source_model_name: str = "unknown",
) -> list[ChordEvent]:
    """Convert chord segments to beat-aligned canonical chord events."""
    del key_map  # Reserved for future key-aware root spelling.
    events: list[ChordEvent] = []
    for start_s, end_s, label, confidence in chord_segments:
        root, quality, extensions = parse_chord_label(label)
        if root.upper() in _SILENCE_LABELS:
            continue
        beat = grid.get_beat_at_time(start_s)
        alignment = None if beat is None else {"measure": beat.measure_number, "beat": beat.beat_in_measure}
        events.append(ChordEvent(
            start_time=float(start_s), end_time=float(end_s), root=root, quality=quality,
            extensions=extensions, beat_aligned_start=alignment, confidence=max(0.0, min(1.0, float(confidence))),
            source_model=source_model_name, track_id="mix",
        ))
    return events


def detect_chords(audio_path: str | Path, grid: BeatGrid, key_map: KeyMap) -> list[ChordEvent]:
    """Detect chords using autochord when installed, otherwise librosa chroma."""
    try:
        import autochord as autochord_module
        raw = detect_chords_autochord(audio_path)
        source_model = f"autochord_{getattr(autochord_module, '__version__', 'unknown')}"
    except Exception as error:
        print(f"autochord unavailable ({error}); falling back to librosa chroma detection.")
        raw = detect_chords_librosa(audio_path)
        source_model = f"librosa_chroma_{librosa.__version__}"
    return align_chords_to_beat_grid(raw, grid, key_map, source_model)


def load_or_detect_chords(
    audio_path: Path, cache_path: Path, grid: BeatGrid, key_map: KeyMap, force: bool = False
) -> list[ChordEvent]:
    """Load cached chord events or detect, serialize, and return fresh events."""
    if cache_path.exists() and not force:
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [ChordEvent.model_validate(item) for item in data]
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    events = detect_chords(audio_path, grid, key_map)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps([event.model_dump(mode="json") for event in events], indent=2), encoding="utf-8")
    return events
