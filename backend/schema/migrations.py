from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from backend.schema.events import AnyMusicalEvent, BeatEvent, KeyEvent, LyricEvent, NoteEvent
from backend.schema.units import SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS


class MigrationError(Exception):
    pass


MIGRATION_REGISTRY: dict[str, Callable] = {
    "legacy_notes": lambda raw, stem="unknown", source_model="pyin_librosa": migrate_legacy_notes(raw, stem=stem, source_model=source_model),
    "legacy_beats": lambda raw, stem="unknown", source_model="librosa_beat_track": migrate_legacy_beats(raw, source_model=source_model),
    "legacy_key": lambda raw, stem="unknown", source_model="krumhansl_schmuckler": migrate_legacy_key(raw, source_model=source_model),
    "legacy_lyrics": lambda raw, stem="unknown", source_model="whisper": migrate_legacy_lyrics(raw, source_model=source_model),
}


def _parse_tonic_and_mode(key_label: str) -> tuple[str, str]:
    if not key_label or not isinstance(key_label, str):
        raise ValueError("key label must be a non-empty string")

    normalized = key_label.strip()
    if not normalized:
        raise ValueError("key label must not be empty")

    lower = normalized.lower()
    if " minor" in lower:
        tonic, _, _ = normalized.rpartition(" ")
        return tonic.strip(), "minor"
    if " major" in lower:
        tonic, _, _ = normalized.rpartition(" ")
        return tonic.strip(), "major"

    if lower.endswith("minor"):
        tonic = normalized[:-5].strip()
        return tonic, "minor"
    if lower.endswith("major"):
        tonic = normalized[:-5].strip()
        return tonic, "major"

    return normalized, "major"


def migrate_legacy_notes(raw: list[dict], stem: str, source_model: str = "pyin_librosa") -> list[NoteEvent]:
    events: list[NoteEvent] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        start_time = float(item.get("time", 0.0))
        duration = float(item.get("duration", 0.0))
        end_time = start_time + duration
        frequency_hz = item.get("frequency")
        confidence = float(item.get("confidence", 0.5))
        midi_pitch = int(item.get("midi_note", 0))

        note = NoteEvent(
            event_id=str(uuid4()),
            track_id=stem,
            event_type="note",
            start_time=start_time,
            end_time=end_time,
            confidence=confidence,
            source_model=source_model,
            midi_pitch=midi_pitch,
            frequency_hz=float(frequency_hz) if frequency_hz is not None else None,
            duration_s=duration,
            is_rest=False,
        )
        events.append(note)
    return events


def migrate_legacy_beats(raw: dict, source_model: str = "librosa_beat_track") -> list[AnyMusicalEvent]:
    beat_times: list[float] = []
    if isinstance(raw, dict):
        beat_times = raw.get("beats") or raw.get("beat_times") or []

    events: list[AnyMusicalEvent] = []
    bpm_value = raw.get("bpm") if isinstance(raw, dict) else None
    if bpm_value is not None:
        events.append(
            BeatEvent(
                event_id=str(uuid4()),
                track_id="mix",
                event_type="beat",
                start_time=0.0,
                end_time=0.0,
                confidence=1.0,
                source_model=source_model,
                beat_number=1,
                is_downbeat=True,
                tempo_bpm=float(bpm_value),
            )
        )

    for index, timestamp in enumerate(beat_times, start=1):
        events.append(
            BeatEvent(
                event_id=str(uuid4()),
                track_id="mix",
                event_type="beat",
                start_time=float(timestamp),
                end_time=float(timestamp),
                confidence=1.0,
                source_model=source_model,
                beat_number=index,
                is_downbeat=index == 1,
                tempo_bpm=float(bpm_value) if bpm_value is not None else None,
            )
        )

    return events


def migrate_legacy_key(raw: dict, source_model: str = "krumhansl_schmuckler") -> list[KeyEvent]:
    if not isinstance(raw, dict):
        return []

    key_label = raw.get("key", "C major")
    tonic, mode = _parse_tonic_and_mode(str(key_label))
    confidence = float(raw.get("confidence", 0.5))

    return [
        KeyEvent(
            event_id=str(uuid4()),
            track_id="mix",
            event_type="key",
            start_time=0.0,
            end_time=None,
            confidence=confidence,
            source_model=source_model,
            tonic=tonic,
            mode=mode,
            analysis_end_time=None,
            manually_overridden=False,
        )
    ]


def migrate_legacy_lyrics(raw: dict, source_model: str = "whisper") -> list[LyricEvent]:
    if not isinstance(raw, dict):
        return []

    segments = raw.get("segments") or []
    events: list[LyricEvent] = []
    word_index = 0

    for segment in segments:
        if not isinstance(segment, dict):
            continue
        words = segment.get("words") or []
        for word_item in words:
            if not isinstance(word_item, dict):
                continue
            word = str(word_item.get("word", ""))
            probability = word_item.get("probability")
            start_time = float(word_item.get("start", 0.0))
            end_time = float(word_item.get("end", start_time))
            events.append(
                LyricEvent(
                    event_id=str(uuid4()),
                    track_id="mix",
                    event_type="lyric",
                    start_time=start_time,
                    end_time=end_time,
                    confidence=float(probability) if probability is not None else 0.5,
                    source_model=source_model,
                    word=word,
                    syllable=None,
                    word_index=word_index,
                    syllable_index=0,
                    alignment_confidence=float(probability) if probability is not None else None,
                    source_note_id=None,
                )
            )
            word_index += 1

    return events


def check_schema_version(data: dict) -> str:
    if not isinstance(data, dict):
        return "legacy_unknown"

    if "schema_version" in data:
        value = str(data["schema_version"])
        if value in SUPPORTED_SCHEMA_VERSIONS or value == SCHEMA_VERSION:
            return value
        return "legacy_unknown"

    if isinstance(data.get("segments"), list):
        return "legacy_lyrics"
    if isinstance(data.get("beats"), list) or isinstance(data.get("beat_times"), list):
        return "legacy_beats"
    if "key" in data:
        return "legacy_key"
    if isinstance(data, list):
        return "legacy_notes"
    if isinstance(data.get("time"), (int, float)):
        return "legacy_notes"

    return "legacy_unknown"


def migrate_events(data: dict | list, file_type: str, stem: str = "unknown") -> list[AnyMusicalEvent]:
    if isinstance(data, dict) and data.get("schema_version") == SCHEMA_VERSION:
        return [AnyMusicalEvent.model_validate(item) for item in data.get("events", [])]

    if isinstance(data, list) and file_type == "notes":
        return migrate_legacy_notes(data, stem=stem)

    detected_version = check_schema_version(data)

    if detected_version in SUPPORTED_SCHEMA_VERSIONS or detected_version == SCHEMA_VERSION:
        if isinstance(data, dict):
            if "events" in data and isinstance(data["events"], list):
                return [AnyMusicalEvent.model_validate(item) for item in data["events"]]
            return [AnyMusicalEvent.model_validate(data)]
        if isinstance(data, list):
            return [AnyMusicalEvent.model_validate(item) for item in data]

    if detected_version in MIGRATION_REGISTRY:
        if file_type == "notes":
            return migrate_legacy_notes(data, stem=stem)
        if file_type == "beats":
            return migrate_legacy_beats(data)
        if file_type == "key":
            return migrate_legacy_key(data)
        if file_type == "lyrics":
            return migrate_legacy_lyrics(data)

    raise MigrationError(f"Unknown schema version or unrecognized legacy payload for file_type={file_type!r}")
