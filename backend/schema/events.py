from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.schema.units import (
    CONFIDENCE_MAX,
    CONFIDENCE_MIN,
    EVENT_TYPES,
    MIDI_PITCH_MAX,
    MIDI_PITCH_MIN,
    SCHEMA_VERSION,
)


class MusicalEventBase(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))  # Unique event identifier for linking downstream analysis results.
    track_id: str  # Stem or track name this event belongs to.
    event_type: str  # Canonical event type string from the shared unit schema.
    start_time: float = Field(ge=0.0)  # Event start time measured in seconds from audio start.
    end_time: float | None = None  # Optional event end time, measured in seconds from audio start.
    confidence: float  # Event confidence clamped to the shared [0.0, 1.0] range.
    source_model: str  # Model or pipeline name that generated the event.
    solfa: str | None = None  # Movable-do syllable resolved from key context, when applicable.
    schema_version: str = SCHEMA_VERSION  # Schema version for serialization compatibility.
    model_config = ConfigDict(extra="allow")  # Allow forward-compatible metadata fields without breaking validation.

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in EVENT_TYPES:
            raise ValueError(f"event_type must be one of: {EVENT_TYPES}")
        return normalized

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: float | int) -> float:
        numeric_value = float(value)
        if numeric_value < CONFIDENCE_MIN or numeric_value > CONFIDENCE_MAX:
            raise ValueError(f"confidence must be in [{CONFIDENCE_MIN}, {CONFIDENCE_MAX}]")
        return numeric_value

    @field_validator("end_time")
    @classmethod
    def validate_end_time(cls, value: float | None, info: object) -> float | None:
        if value is None:
            return value
        start_time = info.data.get("start_time")
        if start_time is not None and value < start_time:
            raise ValueError("end_time must be greater than or equal to start_time")
        return value


class NoteEvent(MusicalEventBase):
    event_type: Literal["note"] = "note"  # Note-like musical events are the primary pitched-event payload.
    midi_pitch: int  # MIDI note number in the canonical integer pitch domain.
    frequency_hz: float | None = None  # Optional raw frequency in Hz when known from the analysis model.
    velocity: int | None = None  # Optional MIDI velocity in the inclusive range [0, 127].
    duration_s: float | None = None  # Optional explicit note duration in seconds for convenience.
    is_rest: bool = False  # Whether this event carries a silent/resting pitch placeholder.
    quantized_position: dict | None = None  # Placeholder for downstream quantization metadata.
    pitch_confidence: float | None = None  # Separate confidence when the pitch estimator exposes it.

    @field_validator("midi_pitch")
    @classmethod
    def validate_midi_pitch(cls, value: int) -> int:
        integer_value = int(value)
        if integer_value < MIDI_PITCH_MIN or integer_value > MIDI_PITCH_MAX:
            raise ValueError(f"midi_pitch must be in [{MIDI_PITCH_MIN}, {MIDI_PITCH_MAX}]")
        return integer_value

    @field_validator("velocity")
    @classmethod
    def validate_velocity(cls, value: int | None) -> int | None:
        if value is None:
            return value
        integer_value = int(value)
        if integer_value < 0 or integer_value > 127:
            raise ValueError("velocity must be in [0, 127]")
        return integer_value

    @field_validator("pitch_confidence")
    @classmethod
    def validate_pitch_confidence(cls, value: float | None) -> float | None:
        if value is None:
            return value
        numeric_value = float(value)
        if numeric_value < CONFIDENCE_MIN or numeric_value > CONFIDENCE_MAX:
            raise ValueError(f"pitch_confidence must be in [{CONFIDENCE_MIN}, {CONFIDENCE_MAX}]")
        return numeric_value

    @model_validator(mode="after")
    def set_duration_from_end_time(self) -> "NoteEvent":
        if self.end_time is not None and self.duration_s is None:
            self.duration_s = self.end_time - self.start_time
        if self.duration_s is not None and self.duration_s < 0:
            raise ValueError("duration_s must be non-negative")
        return self


class RestEvent(MusicalEventBase):
    event_type: Literal["rest"] = "rest"  # Rest events represent explicit silence between notes.
    duration_s: float  # Rest duration in seconds.
    quantized_position: dict | None = None  # Placeholder for downstream quantization metadata.

    @field_validator("duration_s")
    @classmethod
    def validate_duration_s(cls, value: float) -> float:
        numeric_value = float(value)
        if numeric_value <= 0:
            raise ValueError("duration_s must be greater than 0")
        return numeric_value


class ChordEvent(MusicalEventBase):
    event_type: Literal["chord"] = "chord"  # Chord events describe harmonic content over a window.
    root: str  # Chord root note as a pitch-class label, e.g. G or Bb.
    quality: str  # Chord quality such as major, minor, or dominant7.
    extensions: list[str] = Field(default_factory=list)  # Additional chord tones beyond the triad.
    inversion: int = 0  # 0 means root position; higher values indicate inversions.
    bass_note: str | None = None  # Optional explicit bass note label.
    beat_aligned_start: dict | None = None  # Optional beat-grid alignment metadata.

    @field_validator("inversion")
    @classmethod
    def validate_inversion(cls, value: int) -> int:
        integer_value = int(value)
        if integer_value < 0:
            raise ValueError("inversion must be >= 0")
        return integer_value


class DrumHitEvent(MusicalEventBase):
    event_type: Literal["drum_hit"] = "drum_hit"  # Drum hit events are discrete percussion activations.
    drum_type: str  # Canonical drum type label such as kick or snare.
    velocity: int | None = None  # Optional percussion velocity in the MIDI range [0, 127].

    @field_validator("velocity")
    @classmethod
    def validate_velocity(cls, value: int | None) -> int | None:
        if value is None:
            return value
        integer_value = int(value)
        if integer_value < 0 or integer_value > 127:
            raise ValueError("velocity must be in [0, 127]")
        return integer_value


class LyricEvent(MusicalEventBase):
    event_type: Literal["lyric"] = "lyric"  # Lyric events align spoken tokens to time windows.
    word: str  # The lyric token text.
    syllable: str | None = None  # Optional syllable subset when a word is segmented.
    word_index: int  # 0-based index of this word in the lyric sequence.
    syllable_index: int = 0  # 0-based sub-index for multi-syllabic words.
    alignment_confidence: float | None = None  # Optional alignment confidence for a lyric token.
    source_note_id: str | None = None  # Optional link to an associated note event.

    @field_validator("word_index", "syllable_index")
    @classmethod
    def validate_non_negative_index(cls, value: int) -> int:
        integer_value = int(value)
        if integer_value < 0:
            raise ValueError("indexes must be >= 0")
        return integer_value

    @field_validator("alignment_confidence")
    @classmethod
    def validate_alignment_confidence(cls, value: float | None) -> float | None:
        if value is None:
            return value
        numeric_value = float(value)
        if numeric_value < CONFIDENCE_MIN or numeric_value > CONFIDENCE_MAX:
            raise ValueError(f"alignment_confidence must be in [{CONFIDENCE_MIN}, {CONFIDENCE_MAX}]")
        return numeric_value


class BeatEvent(MusicalEventBase):
    event_type: Literal["beat"] = "beat"  # Beat events mark rhythmic boundaries in the song timeline.
    beat_number: int  # 1-based beat number within the current measure.
    is_downbeat: bool = False  # True when this beat coincides with the downbeat.
    tempo_bpm: float | None = None  # Tempo estimate at this beat, in beats-per-minute.

    @field_validator("beat_number")
    @classmethod
    def validate_beat_number(cls, value: int) -> int:
        integer_value = int(value)
        if integer_value < 1:
            raise ValueError("beat_number must be >= 1")
        return integer_value


class KeyEvent(MusicalEventBase):
    event_type: Literal["key"] = "key"  # Key events describe the harmonic tonal center over time.
    tonic: str  # Tonic pitch class such as C, F#, or Bb.
    mode: str  # Musical mode, currently major or minor for v1.
    analysis_end_time: float | None = None  # End of the analysis window; None implies until the end of audio.
    manually_overridden: bool = False  # Whether the key estimate was user- or editor-adjusted.

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"major", "minor"}:
            raise ValueError("mode must be 'major' or 'minor'")
        return normalized


class TempoEvent(MusicalEventBase):
    event_type: Literal["tempo"] = "tempo"  # Tempo events declare tempo estimates over a time range.
    tempo_bpm: float  # Tempo value in beats-per-minute.
    analysis_end_time: float | None = None  # End of the tempo analysis window; None implies until end of audio.

    @field_validator("tempo_bpm")
    @classmethod
    def validate_tempo_bpm(cls, value: float) -> float:
        numeric_value = float(value)
        if numeric_value <= 0:
            raise ValueError("tempo_bpm must be greater than 0")
        return numeric_value


class SectionEvent(MusicalEventBase):
    event_type: Literal["section"] = "section"  # Section events mark structural regions like verse or chorus.
    label: str  # Structural label such as intro or bridge.


AnyMusicalEvent = Annotated[
    NoteEvent | RestEvent | ChordEvent | DrumHitEvent | LyricEvent | BeatEvent | KeyEvent | TempoEvent | SectionEvent,
    Field(discriminator="event_type"),
]
