import json

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.schema.events import (
    BeatEvent,
    ChordEvent,
    DrumHitEvent,
    KeyEvent,
    LyricEvent,
    NoteEvent,
    RestEvent,
)
from backend.schema.manifest import SongManifest
from backend.schema.migrations import (
    check_schema_version,
    migrate_events,
    migrate_legacy_beats,
    migrate_legacy_key,
    migrate_legacy_lyrics,
    migrate_legacy_notes,
)
from backend.schema.units import (
    CONFIDENCE_MAX,
    CONFIDENCE_MIN,
    MIDI_PITCH_MAX,
    MIDI_PITCH_MIN,
    MIDI_PPQ,
    SCHEMA_VERSION,
    STEM_ROLES,
    EVENT_TYPES,
)
from backend.schema.validation import (
    validate_manifest,
    validate_note_event_patch,
    validate_schema_version,
    validate_song_id,
)


class TestUnits:
    def test_midi_pitch_range_valid(self):
        assert MIDI_PITCH_MIN == 0
        assert MIDI_PITCH_MAX == 127

    def test_confidence_range(self):
        assert CONFIDENCE_MIN == 0.0
        assert CONFIDENCE_MAX == 1.0

    def test_ppq_standard(self):
        assert MIDI_PPQ == 480

    def test_schema_version_is_string(self):
        assert isinstance(SCHEMA_VERSION, str)
        assert bool(SCHEMA_VERSION)

    def test_stem_roles_contains_expected(self):
        expected = {"vocals", "bass", "drums", "guitar", "piano", "other"}
        assert expected.issubset(set(STEM_ROLES))

    def test_event_types_contains_expected(self):
        expected = {"note", "rest", "chord", "beat", "key"}
        assert expected.issubset(set(EVENT_TYPES) | {"key"})


class TestMusicalEventBase:
    def test_note_event_construction_valid(self):
        event = NoteEvent(
            track_id="vocals",
            event_type="note",
            start_time=0.25,
            end_time=0.75,
            confidence=0.88,
            source_model="pyin_librosa",
            midi_pitch=64,
            frequency_hz=329.63,
            velocity=100,
        )
        assert event.track_id == "vocals"
        assert event.event_type == "note"
        assert event.midi_pitch == 64
        assert event.frequency_hz == 329.63
        assert event.confidence == 0.88

    def test_note_event_midi_pitch_clamp_low(self):
        with pytest.raises(ValidationError):
            NoteEvent(
                track_id="vocals",
                event_type="note",
                start_time=0.0,
                end_time=0.5,
                confidence=0.9,
                source_model="pyin_librosa",
                midi_pitch=-1,
            )

    def test_note_event_midi_pitch_clamp_high(self):
        with pytest.raises(ValidationError):
            NoteEvent(
                track_id="vocals",
                event_type="note",
                start_time=0.0,
                end_time=0.5,
                confidence=0.9,
                source_model="pyin_librosa",
                midi_pitch=128,
            )

    def test_note_event_end_before_start(self):
        with pytest.raises(ValidationError):
            NoteEvent(
                track_id="vocals",
                event_type="note",
                start_time=1.0,
                end_time=0.5,
                confidence=0.9,
                source_model="pyin_librosa",
                midi_pitch=60,
            )

    def test_confidence_above_1(self):
        with pytest.raises(ValidationError):
            NoteEvent(
                track_id="vocals",
                event_type="note",
                start_time=0.0,
                end_time=0.5,
                confidence=1.5,
                source_model="pyin_librosa",
                midi_pitch=60,
            )

    def test_confidence_below_0(self):
        with pytest.raises(ValidationError):
            NoteEvent(
                track_id="vocals",
                event_type="note",
                start_time=0.0,
                end_time=0.5,
                confidence=-0.1,
                source_model="pyin_librosa",
                midi_pitch=60,
            )

    def test_event_id_auto_generated(self):
        first = NoteEvent(
            track_id="vocals",
            event_type="note",
            start_time=0.0,
            end_time=0.5,
            confidence=0.9,
            source_model="pyin_librosa",
            midi_pitch=60,
        )
        second = NoteEvent(
            track_id="vocals",
            event_type="note",
            start_time=0.5,
            end_time=1.0,
            confidence=0.9,
            source_model="pyin_librosa",
            midi_pitch=62,
        )
        assert first.event_id != second.event_id

    def test_rest_event_construction(self):
        event = RestEvent(
            track_id="vocals",
            event_type="rest",
            start_time=0.0,
            end_time=0.75,
            confidence=0.5,
            source_model="pyin_librosa",
            duration_s=0.75,
        )
        assert event.duration_s > 0

    def test_chord_event_construction(self):
        event = ChordEvent(
            track_id="piano",
            event_type="chord",
            start_time=0.0,
            end_time=1.0,
            confidence=0.91,
            source_model="basic_pitch",
            root="C",
            quality="major",
            extensions=["7"],
            inversion=0,
        )
        assert event.root == "C"
        assert event.quality == "major"

    def test_drum_hit_event_construction(self):
        event = DrumHitEvent(
            track_id="drums",
            event_type="drum_hit",
            start_time=1.0,
            end_time=1.1,
            confidence=0.95,
            source_model="adtlib",
            drum_type="kick",
            velocity=100,
        )
        assert event.drum_type == "kick"

    def test_beat_event_construction(self):
        event = BeatEvent(
            track_id="mix",
            event_type="beat",
            start_time=0.5,
            end_time=0.5,
            confidence=1.0,
            source_model="librosa_beat_track",
            beat_number=1,
            is_downbeat=True,
            tempo_bpm=120.0,
        )
        assert event.beat_number == 1
        assert event.is_downbeat is True

    def test_key_event_construction(self):
        event = KeyEvent(
            track_id="mix",
            event_type="key",
            start_time=0.0,
            end_time=None,
            confidence=0.84,
            source_model="krumhansl_schmuckler",
            tonic="C",
            mode="major",
        )
        assert event.tonic == "C"
        assert event.mode == "major"

    def test_extra_fields_allowed(self):
        event = NoteEvent(
            track_id="vocals",
            event_type="note",
            start_time=0.0,
            end_time=0.5,
            confidence=0.9,
            source_model="pyin_librosa",
            midi_pitch=60,
            extra_field="allowed",
        )
        assert event.extra_field == "allowed"

    def test_source_model_required(self):
        with pytest.raises(ValidationError):
            NoteEvent(
                track_id="vocals",
                event_type="note",
                start_time=0.0,
                end_time=0.5,
                confidence=0.9,
                midi_pitch=60,
            )

    def test_schema_version_default(self):
        event = NoteEvent(
            track_id="vocals",
            event_type="note",
            start_time=0.0,
            end_time=0.5,
            confidence=0.9,
            source_model="pyin_librosa",
            midi_pitch=60,
        )
        assert event.schema_version == SCHEMA_VERSION


class TestSongManifest:
    def test_minimal_manifest_parses(self):
        payload = {
            "song_id": "song_123",
            "title": "Demo Song",
            "stems": ["vocals", "bass", "drums"],
        }
        manifest = SongManifest.model_validate(payload)
        assert manifest.song_id == "song_123"
        assert manifest.title == "Demo Song"

    def test_new_fields_have_safe_defaults(self):
        manifest = SongManifest.model_validate({
            "song_id": "song_123",
            "title": "Demo Song",
            "stems": ["vocals"],
        })
        assert manifest.schema_version == SCHEMA_VERSION
        assert isinstance(manifest.transcription_runs, list)
        assert isinstance(manifest.artifacts, dict)

    def test_extra_fields_tolerated(self):
        manifest = SongManifest.model_validate(
            {
                "song_id": "song_123",
                "title": "Demo Song",
                "stems": ["vocals"],
                "legacy_custom_field": "x",
            }
        )
        assert manifest.legacy_custom_field == "x"

    def test_from_file_roundtrip(self, tmp_path):
        payload = {
            "song_id": "song_roundtrip",
            "title": "Roundtrip Song",
            "stems": ["vocals", "drums"],
        }
        file_path = tmp_path / "manifest.json"
        file_path.write_text(json.dumps(payload), encoding="utf-8")

        manifest = SongManifest.from_file(file_path)
        assert manifest.song_id == "song_roundtrip"

        output_path = tmp_path / "manifest_out.json"
        manifest.to_file(output_path)
        reloaded = SongManifest.from_file(output_path)
        assert reloaded.song_id == "song_roundtrip"

    def test_to_file_atomic(self, tmp_path):
        manifest = SongManifest.model_validate({
            "song_id": "atomic_song",
            "title": "Atomic Song",
            "stems": ["vocals"],
        })
        target = tmp_path / "manifest.json"
        manifest.to_file(target)
        assert not any(tmp_path.glob("*.tmp"))

    def test_from_file_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            SongManifest.from_file(tmp_path / "missing.json")

    def test_from_file_invalid_json_raises(self, tmp_path):
        invalid_path = tmp_path / "invalid.json"
        invalid_path.write_text("{{not json", encoding="utf-8")
        with pytest.raises((json.JSONDecodeError, ValidationError)):
            SongManifest.from_file(invalid_path)


class TestMigrations:
    def test_migrate_legacy_notes_basic(self):
        raw = [
            {"time": 0.0, "duration": 0.5, "midi_note": 60, "confidence": 0.81},
            {"time": 0.5, "duration": 0.5, "midi_note": 62, "confidence": 0.87},
        ]
        events = migrate_legacy_notes(raw, stem="vocals")
        assert isinstance(events, list)
        assert all(isinstance(item, NoteEvent) for item in events)
        assert events[0].start_time == 0.0
        assert events[1].midi_pitch == 62
        assert events[1].confidence == 0.87

    def test_migrate_legacy_notes_empty_list(self):
        assert migrate_legacy_notes([], stem="vocals") == []

    def test_migrate_legacy_beats_basic(self):
        raw = {"bpm": 120.0, "beats": [0.5, 1.0, 1.5]}
        events = migrate_legacy_beats(raw)
        assert isinstance(events[0], BeatEvent)
        assert [event.start_time for event in events if event.start_time > 0.0] == [0.5, 1.0, 1.5]

    def test_migrate_legacy_key_major(self):
        events = migrate_legacy_key({"key": "C major", "confidence": 0.83})
        assert isinstance(events, list)
        event = events[0]
        assert isinstance(event, KeyEvent)
        assert event.tonic == "C"
        assert event.mode == "major"
        assert event.confidence == 0.83

    def test_migrate_legacy_key_minor(self):
        events = migrate_legacy_key({"key": "F# minor", "confidence": 0.71})
        event = events[0]
        assert isinstance(event, KeyEvent)
        assert event.tonic == "F#"
        assert event.mode == "minor"

    def test_migrate_legacy_lyrics_basic(self):
        raw = {
            "segments": [
                {"words": [{"word": "hello", "start": 0.0, "end": 0.25, "probability": 0.9}, {"word": "world", "start": 0.25, "end": 0.5, "probability": 0.8}]}
            ]
        }
        events = migrate_legacy_lyrics(raw)
        assert isinstance(events, list)
        assert all(isinstance(item, LyricEvent) for item in events)
        assert events[0].word == "hello"
        assert events[1].start_time == 0.25

    def test_check_schema_version_returns_current(self):
        assert check_schema_version({"schema_version": "1.0"}) == "1.0"

    def test_check_schema_version_missing(self):
        assert check_schema_version({"midi_pitch": 60, "time": 1.0}) == "legacy_notes"

    def test_migrate_events_dispatcher_notes(self):
        legacy_notes = [{"time": 0.0, "duration": 0.5, "midi_note": 60, "confidence": 0.9}]
        events = migrate_events(legacy_notes, "notes", "vocals")
        assert isinstance(events, list)
        assert all(isinstance(item, NoteEvent) for item in events)


class TestValidation:
    def test_validate_song_id_valid(self):
        assert validate_song_id("abc-123_XYZ") == "abc-123_XYZ"

    def test_validate_song_id_path_traversal(self):
        with pytest.raises(HTTPException) as exc:
            validate_song_id("../evil")
        assert exc.value.status_code == 400

    def test_validate_song_id_too_long(self):
        with pytest.raises(HTTPException) as exc:
            validate_song_id("a" * 65)
        assert exc.value.status_code == 400

    def test_validate_song_id_empty(self):
        with pytest.raises(HTTPException) as exc:
            validate_song_id("")
        assert exc.value.status_code == 400

    def test_validate_manifest_valid(self):
        manifest = validate_manifest({
            "song_id": "song_123",
            "title": "Demo",
            "stems": ["vocals", "drums"],
        })
        assert isinstance(manifest, SongManifest)

    def test_validate_manifest_missing_required(self):
        with pytest.raises(HTTPException) as exc:
            validate_manifest({"title": "Demo"})
        assert exc.value.status_code == 422

    def test_validate_schema_version_supported(self):
        assert validate_schema_version({"schema_version": "1.0"}) == "1.0"

    def test_validate_schema_version_unsupported(self):
        with pytest.raises(HTTPException) as exc:
            validate_schema_version({"schema_version": "99.0"})
        assert exc.value.status_code == 422

    def test_validate_schema_version_missing(self):
        assert validate_schema_version({}) == "legacy"

    def test_validate_note_event_patch_valid(self):
        patch = validate_note_event_patch({"midi_pitch": 64})
        assert patch == {"midi_pitch": 64}

    def test_validate_note_event_patch_invalid_pitch(self):
        with pytest.raises(HTTPException) as exc:
            validate_note_event_patch({"midi_pitch": 200})
        assert exc.value.status_code == 400

    def test_validate_note_event_patch_unknown_key(self):
        with pytest.raises(HTTPException) as exc:
            validate_note_event_patch({"color": "red"})
        assert exc.value.status_code == 400
