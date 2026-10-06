import pytest
from pydantic import ValidationError

from backend.transcription.config import ENGINE_REGISTRY, TranscriptionConfig, is_engine_available


class TestTranscriptionConfig:
    def test_default_construction(self):
        config = TranscriptionConfig(stem_type="vocals")
        assert config.stem_type == "vocals"
        assert config.quality_profile == "standard"
        assert config.minimum_confidence == 0.3

    def test_quality_profile_valid_values(self):
        for profile in ("fast", "standard", "high_quality"):
            config = TranscriptionConfig(stem_type="vocals", quality_profile=profile)
            assert config.quality_profile == profile

    def test_quality_profile_invalid(self):
        with pytest.raises(ValidationError):
            TranscriptionConfig(stem_type="vocals", quality_profile="ultra")

    def test_onset_threshold_range(self):
        with pytest.raises(ValidationError):
            TranscriptionConfig(stem_type="vocals", onset_threshold=-0.1)
        with pytest.raises(ValidationError):
            TranscriptionConfig(stem_type="vocals", onset_threshold=1.1)

    def test_config_hash_is_deterministic(self):
        first = TranscriptionConfig(stem_type="vocals", onset_threshold=0.5)
        second = TranscriptionConfig(stem_type="vocals", onset_threshold=0.5)
        assert first.config_hash == second.config_hash

    def test_config_hash_changes_with_config(self):
        first = TranscriptionConfig(stem_type="vocals", onset_threshold=0.5)
        second = TranscriptionConfig(stem_type="vocals", onset_threshold=0.7)
        assert first.config_hash != second.config_hash

    def test_config_hash_excludes_device(self):
        first = TranscriptionConfig(stem_type="vocals", device="cpu")
        second = TranscriptionConfig(stem_type="vocals", device="cuda")
        assert first.config_hash == second.config_hash

    def test_config_hash_excludes_source_model(self):
        first = TranscriptionConfig(stem_type="vocals", source_model="model_a")
        second = TranscriptionConfig(stem_type="vocals", source_model="model_b")
        assert first.config_hash == second.config_hash

    def test_stem_type_must_be_stem_role(self):
        with pytest.raises(ValidationError):
            TranscriptionConfig(stem_type="theremin")

    def test_chunk_duration_positive(self):
        with pytest.raises(ValidationError):
            TranscriptionConfig(stem_type="vocals", chunk_duration_s=0)

    def test_minimum_note_length_positive(self):
        with pytest.raises(ValidationError):
            TranscriptionConfig(stem_type="vocals", minimum_note_length_ms=-10)


class TestEngineRegistry:
    def test_registry_contains_all_expected_engines(self):
        expected = {"pyin", "basic_pitch", "piano_kong", "adtlib", "mt3"}
        assert expected.issubset(ENGINE_REGISTRY)

    def test_pyin_is_not_polyphonic(self):
        assert ENGINE_REGISTRY["pyin"]["polyphonic"] is False

    def test_basic_pitch_is_polyphonic(self):
        assert ENGINE_REGISTRY["basic_pitch"]["polyphonic"] is True

    def test_mt3_is_disabled(self):
        assert ENGINE_REGISTRY["mt3"].get("enabled") is False

    def test_all_entries_have_license_field(self):
        for entry in ENGINE_REGISTRY.values():
            assert "license" in entry

    def test_all_entries_have_data_cost(self):
        for entry in ENGINE_REGISTRY.values():
            value = entry["data_cost_mb"]
            assert isinstance(value, (int, float)) and not isinstance(value, bool)

    def test_pyin_has_zero_data_cost(self):
        assert ENGINE_REGISTRY["pyin"]["data_cost_mb"] == 0


class TestIsEngineAvailable:
    def test_pyin_available(self):
        assert is_engine_available("pyin") is True

    def test_nonexistent_engine(self):
        assert is_engine_available("not_a_real_engine") is False

    def test_never_raises(self):
        for value in ("", " ", "not_a_real_engine", None, "pyin"):
            result = is_engine_available(value)
            assert isinstance(result, bool)

    def test_mt3_unavailable_by_default(self):
        assert is_engine_available("mt3") is False
