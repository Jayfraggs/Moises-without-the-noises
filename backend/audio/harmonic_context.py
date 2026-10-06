"""Time-varying key analysis and key-aware enharmonic pitch spelling."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import librosa
from .key_detection import _detect_key

PITCH_CLASS_TO_NAME = {0: "C", 1: "C#", 2: "D", 3: "D#", 4: "E", 5: "F", 6: "F#", 7: "G", 8: "G#", 9: "A", 10: "A#", 11: "B"}
ENHARMONIC_MAP: dict[int, dict[str, str]] = {1: {"sharps": "C#", "flats": "Db"}, 3: {"sharps": "D#", "flats": "Eb"}, 6: {"sharps": "F#", "flats": "Gb"}, 8: {"sharps": "G#", "flats": "Ab"}, 10: {"sharps": "A#", "flats": "Bb"}}
FLAT_KEYS = {"F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb", "D", "G", "Bf", "Gm", "Cm", "Fm", "Bbm", "Ebm", "Abm"}
SCALE_INTERVALS: dict[str, list[int]] = {"major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10], "dorian": [0, 2, 3, 5, 7, 9, 10], "mixolydian": [0, 2, 4, 5, 7, 9, 10], "phrygian": [0, 1, 3, 5, 7, 8, 10]}
_NAME_MAP = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "Fb": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11, "Cb": 11, "B#": 0}


def note_name_to_pitch_class(name: str) -> int:
    """Map a note name to 0=C through 11=B."""
    try:
        return _NAME_MAP[name.strip()]
    except KeyError as exc:
        raise ValueError(f"Unrecognized note name: {name!r}") from exc


def get_key_preference(tonic: str) -> str:
    """Return the preferred accidental family for a key tonic."""
    return "flats" if tonic in {"F", "Bb", "Eb", "Ab", "Db", "Gb"} else "sharps"


def spell_pitch(midi_pitch: int, tonic: str, mode: str) -> str:
    """Spell a MIDI pitch according to the active key."""
    del mode
    pitch_class = midi_pitch % 12
    if pitch_class not in ENHARMONIC_MAP:
        return PITCH_CLASS_TO_NAME[pitch_class]
    return ENHARMONIC_MAP[pitch_class][get_key_preference(tonic)]


def get_scale_degrees(tonic: str, mode: str) -> list[int]:
    """Return ordered scale pitch classes for the supplied key."""
    return [(note_name_to_pitch_class(tonic) + interval) % 12 for interval in SCALE_INTERVALS.get(mode, SCALE_INTERVALS["major"])]


def is_chromatic(midi_pitch: int, tonic: str, mode: str) -> bool:
    """Return whether a MIDI pitch is outside the active diatonic scale."""
    return midi_pitch % 12 not in get_scale_degrees(tonic, mode)


@dataclass
class KeyMapEntry:
    tonic: str
    mode: str
    confidence: float
    start_s: float
    end_s: float | None
    source: str = "krumhansl_schmuckler"
    manually_overridden: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    def covers_time(self, time_s: float) -> bool:
        return self.start_s <= time_s and (self.end_s is None or time_s < self.end_s)


@dataclass
class KeyMap:
    entries: list[KeyMapEntry]
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.entries:
            raise ValueError("KeyMap requires at least one entry")

    def get_key_at(self, time_s: float) -> KeyMapEntry:
        for entry in reversed(self.entries):
            if entry.covers_time(time_s):
                return entry
        return self.entries[0]

    def spell_pitch_at(self, midi_pitch: int, time_s: float) -> str:
        entry = self.get_key_at(time_s)
        return spell_pitch(midi_pitch, entry.tonic, entry.mode)

    def to_dict(self) -> dict:
        return {"schema_version": self.schema_version, "key_map": [entry.to_dict() for entry in self.entries]}

    @classmethod
    def from_dict(cls, data: dict) -> "KeyMap":
        raw_entries = data.get("key_map")
        if isinstance(raw_entries, list) and raw_entries:
            entries = [KeyMapEntry(str(item["tonic"]), str(item.get("mode", "major")).lower(), float(item.get("confidence", 0.0)), float(item.get("start_s", 0.0)), float(item["end_s"]) if item.get("end_s") is not None else None, str(item.get("source", "krumhansl_schmuckler")), bool(item.get("manually_overridden", False))) for item in raw_entries]
            return cls(entries, str(data.get("schema_version", "1.0")))
        key = data.get("key")
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Key data must contain a non-empty 'key' or 'key_map'")
        tonic, mode = _parse_legacy_key(key, data.get("scale"))
        return cls.from_single_key(tonic, mode, _normalize_confidence(data.get("confidence", data.get("key_confidence", 0.0))))

    @classmethod
    def from_single_key(cls, tonic: str, mode: str, confidence: float, source: str = "krumhansl_schmuckler") -> "KeyMap":
        return cls([KeyMapEntry(tonic, mode, confidence, 0.0, None, source)])


def build_key_map_from_segments(audio_path: str | Path, segment_duration_s: float = 30.0) -> KeyMap:
    """Analyze half-overlapped windows and merge consecutive matching keys."""
    if segment_duration_s <= 0:
        raise ValueError("segment_duration_s must be greater than zero")
    y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    if y.size == 0:
        raise ValueError(f"Cannot analyze empty audio: {audio_path}")
    samples = max(1, int(segment_duration_s * sr))
    hop = max(1, samples // 2)
    detected: list[KeyMapEntry] = []
    starts = [0] if len(y) <= samples else range(0, len(y), hop)
    for start in starts:
        segment = y[start:min(start + samples, len(y))]
        chroma = librosa.feature.chroma_cqt(y=segment, sr=sr)
        label, scale, confidence = _detect_key(chroma.mean(axis=1).tolist())
        tonic, mode = _parse_legacy_key(label, scale)
        detected.append(KeyMapEntry(tonic, mode, confidence / 100.0, start / sr, None))
    merged: list[KeyMapEntry] = []
    for entry in detected:
        if merged and (merged[-1].tonic, merged[-1].mode) == (entry.tonic, entry.mode):
            previous = merged[-1]
            previous.confidence = (previous.confidence + entry.confidence) / 2.0
        else:
            if merged:
                merged[-1].end_s = entry.start_s
            merged.append(entry)
    merged[-1].end_s = None
    return KeyMap(merged)


def load_or_build_key_map(audio_path: Path, cache_path: Path, force: bool = False) -> KeyMap:
    """Load a cache, migrating legacy global keys, or analyze and cache audio."""
    if cache_path.exists() and not force:
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            key_map = KeyMap.from_dict(data)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            key_map = None
        if key_map is not None:
            if "key_map" not in data:
                _write_key_map_cache(cache_path, key_map)
            return key_map
    key_map = build_key_map_from_segments(audio_path)
    _write_key_map_cache(cache_path, key_map)
    return key_map


def _write_key_map_cache(cache_path: Path, key_map: KeyMap) -> None:
    first = key_map.entries[0]
    payload = {"schema_version": "2.0", "key_map": [entry.to_dict() for entry in key_map.entries], "key": f"{first.tonic} {first.mode}", "confidence": first.confidence}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _parse_legacy_key(key: str, scale: object = None) -> tuple[str, str]:
    parts = key.strip().split()
    if not parts:
        raise ValueError("Key label cannot be empty")
    tonic = parts[0]
    note_name_to_pitch_class(tonic)
    label_mode, scale_mode = " ".join(parts[1:]).lower(), str(scale or "").lower()
    return tonic, "minor" if "min" in label_mode or "minor" in scale_mode else "major"


def _normalize_confidence(value: object) -> float:
    confidence = float(value or 0.0)
    return confidence / 100.0 if confidence > 1.0 else confidence
