import pytest

basic_pitch_available = pytest.importorskip(
    "basic_pitch",
    reason="basic-pitch not installed. Run: pip install basic-pitch",
)

from backend.schema.events import NoteEvent
from backend.schema.units import SCHEMA_VERSION
from backend.transcription.config import TranscriptionConfig
from backend.transcription.engines.basic_pitch import BasicPitchEngine

pytestmark = pytest.mark.integration


class TestBasicPitchEngineHealth:
    def test_health_check_passes(self):
        assert BasicPitchEngine().health_check() is True

    def test_model_info_polyphonic_true(self):
        assert BasicPitchEngine().model_info()["polyphonic"] is True

    def test_model_info_has_version(self):
        assert "version" in BasicPitchEngine().model_info()

    def test_supports_vocals_standard(self):
        engine = BasicPitchEngine()
        assert engine.supports("vocals", "standard") is True

    def test_supports_piano_high_quality(self):
        engine = BasicPitchEngine()
        assert engine.supports("piano", "high_quality") is True

    def test_does_not_support_fast_profile(self):
        engine = BasicPitchEngine()
        assert engine.supports("vocals", "fast") is False

    def test_does_not_support_drums(self):
        engine = BasicPitchEngine()
        assert engine.supports("drums", "standard") is False


class TestBasicPitchTranscription:
    def test_c_major_returns_note_events(self, c_major_scale_path):
        config = TranscriptionConfig(stem_type="vocals", quality_profile="standard")
        events = BasicPitchEngine().transcribe(str(c_major_scale_path), config)
        assert len(events) > 0
        assert all(isinstance(event, NoteEvent) for event in events)

    def test_c_major_pitches_in_range(self, c_major_scale_path):
        config = TranscriptionConfig(stem_type="vocals", quality_profile="standard")
        events = BasicPitchEngine().transcribe(str(c_major_scale_path), config)
        assert all(60 <= event.midi_pitch <= 72 for event in events)

    def test_events_have_schema_fields(self, c_major_scale_path):
        config = TranscriptionConfig(stem_type="vocals", quality_profile="standard")
        events = BasicPitchEngine().transcribe(str(c_major_scale_path), config)
        assert events
        assert all("basic_pitch" in event.source_model for event in events)
        assert all(event.schema_version == SCHEMA_VERSION for event in events)
        assert all(0.0 <= event.confidence <= 1.0 for event in events)

    def test_major_triad_detects_multiple_simultaneous_notes(self, major_triad_path):
        config = TranscriptionConfig(
            stem_type="piano",
            quality_profile="standard",
            minimum_confidence=0.2,
            minimum_note_length_ms=100.0,
        )
        events = BasicPitchEngine().transcribe(str(major_triad_path), config)
        assert len(events) >= 2, f"Expected ≥2 simultaneous notes, got {len(events)}"
        pitches = {event.midi_pitch for event in events}
        expected = {60, 64, 67}
        assert len(pitches & expected) >= 2

    def test_silence_produces_no_events(self, silence_path):
        config = TranscriptionConfig(
            stem_type="vocals",
            quality_profile="standard",
            minimum_confidence=0.3,
        )
        events = BasicPitchEngine().transcribe(str(silence_path), config)
        assert len(events) == 0

    def test_events_sorted_by_start_time(self, c_major_scale_path):
        config = TranscriptionConfig(stem_type="vocals", quality_profile="standard")
        events = BasicPitchEngine().transcribe(str(c_major_scale_path), config)
        start_times = [event.start_time for event in events]
        assert start_times == sorted(start_times)

    def test_confidence_filter_works(self, c_major_scale_path):
        relaxed_config = TranscriptionConfig(
            stem_type="vocals",
            quality_profile="standard",
            minimum_confidence=0.0,
        )
        strict_config = TranscriptionConfig(
            stem_type="vocals",
            quality_profile="standard",
            minimum_confidence=0.99,
        )
        relaxed_events = BasicPitchEngine().transcribe(str(c_major_scale_path), relaxed_config)
        strict_events = BasicPitchEngine().transcribe(str(c_major_scale_path), strict_config)
        assert len(relaxed_events) >= len(strict_events)

    def test_missing_file_raises(self, tmp_path):
        config = TranscriptionConfig(stem_type="vocals", quality_profile="standard")
        with pytest.raises((FileNotFoundError, RuntimeError)):
            BasicPitchEngine().transcribe(str(tmp_path / "does_not_exist.wav"), config)
