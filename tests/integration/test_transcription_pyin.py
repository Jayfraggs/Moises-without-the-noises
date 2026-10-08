import pytest

import librosa

from backend.schema.events import NoteEvent
from backend.schema.units import SCHEMA_VERSION
from backend.transcription.config import TranscriptionConfig
from backend.transcription.engines.pyin import PYINEngine

pytestmark = pytest.mark.integration


class TestPYINEngineHealth:
    def test_health_check_passes(self):
        assert PYINEngine().health_check() is True

    def test_model_info_shape(self):
        info = PYINEngine().model_info()
        assert set({"engine", "library", "version", "polyphonic"}).issubset(info)

    def test_polyphonic_is_false(self):
        assert PYINEngine().model_info()["polyphonic"] is False

    def test_supports_vocals_fast(self):
        assert PYINEngine().supports("vocals", "fast") is True

    def test_supports_bass_fast(self):
        assert PYINEngine().supports("bass", "fast") is True

    def test_does_not_support_guitar(self):
        assert PYINEngine().supports("guitar", "fast") is False

    def test_does_not_support_standard_profile(self):
        assert PYINEngine().supports("vocals", "standard") is False


class TestPYINTranscription:
    def test_c_major_returns_note_events(self, c_major_scale_path):
        config = TranscriptionConfig(stem_type="vocals", quality_profile="fast")
        events = PYINEngine().transcribe(str(c_major_scale_path), config)
        assert len(events) > 0
        assert all(isinstance(event, NoteEvent) for event in events)

    def test_c_major_note_count_approximate(self, c_major_scale_path):
        config = TranscriptionConfig(stem_type="vocals", quality_profile="fast")
        events = PYINEngine().transcribe(str(c_major_scale_path), config)
        assert 1 <= len(events) <= 10

    def test_c_major_pitches_are_in_range(self, c_major_scale_path):
        config = TranscriptionConfig(stem_type="vocals", quality_profile="fast")
        events = PYINEngine().transcribe(str(c_major_scale_path), config)
        assert all(60 <= event.midi_pitch <= 72 for event in events)

    def test_events_sorted_by_start_time(self, c_major_scale_path):
        config = TranscriptionConfig(stem_type="vocals", quality_profile="fast")
        events = PYINEngine().transcribe(str(c_major_scale_path), config)
        start_times = [event.start_time for event in events]
        assert start_times == sorted(start_times)

    def test_all_events_have_required_fields(self, c_major_scale_path):
        config = TranscriptionConfig(stem_type="vocals", quality_profile="fast")
        events = PYINEngine().transcribe(str(c_major_scale_path), config)
        assert all(event.source_model for event in events)
        assert all(event.track_id == "vocals" for event in events)
        assert all(0.0 <= event.confidence <= 1.0 for event in events)
        assert all(event.schema_version == SCHEMA_VERSION for event in events)

    def test_silence_returns_empty_or_low_confidence(self, silence_path):
        config = TranscriptionConfig(stem_type="vocals", quality_profile="fast", minimum_confidence=0.3)
        events = PYINEngine().transcribe(str(silence_path), config)
        assert len(events) == 0 or all(event.confidence < 0.5 for event in events)

    def test_missing_file_raises_file_not_found(self, tmp_path):
        config = TranscriptionConfig(stem_type="vocals", quality_profile="fast")
        with pytest.raises(FileNotFoundError):
            PYINEngine().transcribe(str(tmp_path / "does_not_exist.wav"), config)

    def test_minimum_confidence_filter(self, c_major_scale_path):
        default_config = TranscriptionConfig(stem_type="vocals", quality_profile="fast")
        default_events = PYINEngine().transcribe(str(c_major_scale_path), default_config)
        strict_config = TranscriptionConfig(stem_type="vocals", quality_profile="fast", minimum_confidence=0.99)
        strict_events = PYINEngine().transcribe(str(c_major_scale_path), strict_config)
        relaxed_config = TranscriptionConfig(stem_type="vocals", quality_profile="fast", minimum_confidence=0.0)
        relaxed_events = PYINEngine().transcribe(str(c_major_scale_path), relaxed_config)
        assert len(relaxed_events) >= len(default_events)

    def test_minimum_duration_filter(self, c_major_scale_path):
        config = TranscriptionConfig(stem_type="vocals", quality_profile="fast", minimum_note_length_ms=5000)
        events = PYINEngine().transcribe(str(c_major_scale_path), config)
        assert len(events) == 0

    def test_source_model_contains_librosa_version(self, c_major_scale_path):
        config = TranscriptionConfig(stem_type="vocals", quality_profile="fast")
        events = PYINEngine().transcribe(str(c_major_scale_path), config)
        assert events
        assert librosa.__version__ in events[0].source_model
