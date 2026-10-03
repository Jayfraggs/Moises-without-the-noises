"""
tests/test_separation_models.py

Tests for the SUPPORTED_MODELS registry and run_separation() validation layer.
Does NOT run actual Demucs/Spleeter/etc. — only the config and dispatch logic.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from separation import SUPPORTED_MODELS, DEFAULT_MODEL, run_separation, _normalise_stem_name


class TestSupportedModels:
    REQUIRED_KEYS = {"stems", "description", "engine", "engine_key", "pip_hint", "data_cost_mb"}

    def test_all_models_have_required_fields(self):
        for name, cfg in SUPPORTED_MODELS.items():
            missing = self.REQUIRED_KEYS - set(cfg.keys())
            assert not missing, f"Model '{name}' missing fields: {missing}"

    def test_stems_are_non_empty_lists(self):
        for name, cfg in SUPPORTED_MODELS.items():
            assert isinstance(cfg["stems"], list), f"'{name}'.stems should be a list"
            assert len(cfg["stems"]) >= 2, f"'{name}' should have at least 2 stems"

    def test_default_model_exists(self):
        assert DEFAULT_MODEL in SUPPORTED_MODELS, \
            f"DEFAULT_MODEL '{DEFAULT_MODEL}' not in SUPPORTED_MODELS"

    def test_all_engines_have_runners(self):
        from separation import _ENGINE_RUNNERS
        for name, cfg in SUPPORTED_MODELS.items():
            eng = cfg["engine"]
            assert eng in _ENGINE_RUNNERS, \
                f"Model '{name}' engine '{eng}' has no runner in _ENGINE_RUNNERS"

    def test_demucs_models_present(self):
        assert "htdemucs_ft" in SUPPORTED_MODELS
        assert "htdemucs_6s" in SUPPORTED_MODELS

    def test_spleeter_variants_present(self):
        assert "spleeter:2stems" in SUPPORTED_MODELS
        assert "spleeter:4stems" in SUPPORTED_MODELS
        assert "spleeter:5stems" in SUPPORTED_MODELS

    def test_openunmix_variants_present(self):
        assert "umxl" in SUPPORTED_MODELS
        assert "umxhq" in SUPPORTED_MODELS

    def test_mdx_models_present(self):
        assert "mdx-vocalft" in SUPPORTED_MODELS
        assert "mdx-inst-hq3" in SUPPORTED_MODELS

    def test_roformer_models_present(self):
        assert "bs-roformer" in SUPPORTED_MODELS
        assert "melband-roformer" in SUPPORTED_MODELS

    def test_data_cost_positive(self):
        for name, cfg in SUPPORTED_MODELS.items():
            assert cfg["data_cost_mb"] > 0, \
                f"'{name}'.data_cost_mb should be positive"

    def test_htdemucs_6s_has_guitar_and_piano(self):
        stems = SUPPORTED_MODELS["htdemucs_6s"]["stems"]
        assert "guitar" in stems
        assert "piano" in stems

    def test_htdemucs_ft_has_no_guitar(self):
        stems = SUPPORTED_MODELS["htdemucs_ft"]["stems"]
        assert "guitar" not in stems
        assert "piano" not in stems

    def test_bs_roformer_has_6_stems(self):
        assert len(SUPPORTED_MODELS["bs-roformer"]["stems"]) == 6

    def test_2stem_models_have_exactly_2_stems(self):
        two_stem_models = [
            "spleeter:2stems", "mdx-vocalft", "mdx-inst-hq3", "melband-roformer"
        ]
        for name in two_stem_models:
            cfg = SUPPORTED_MODELS[name]
            assert len(cfg["stems"]) == 2, \
                f"'{name}' should have exactly 2 stems, got {cfg['stems']}"


class TestRunSeparationValidation:
    def test_invalid_model_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown model"):
            run_separation(
                Path(tmp_path / "fake.mp3"),
                "test_song",
                model_name="nonexistent_model_xyz",
            )

    def test_valid_model_name_accepted_before_runner(self, monkeypatch, tmp_path):
        """
        Test that a valid model name passes the guard clause.
        We monkeypatch the runner to avoid actually running Demucs.
        """
        ran = {}

        def fake_runner(input_path, song_dir, engine_key, report):
            ran["called"] = True
            ran["engine_key"] = engine_key
            # Return dummy stem files so the rest of run_separation can proceed
            wav = song_dir / "vocals.wav"
            wav.write_bytes(b"")
            return {"vocals": wav}

        import separation as sep
        monkeypatch.setitem(sep._ENGINE_RUNNERS, "demucs", fake_runner)

        fake_audio = tmp_path / "song.mp3"
        fake_audio.write_bytes(b"fake")

        # Should not raise on the model name check
        try:
            run_separation(fake_audio, "my_song", model_name="htdemucs_ft")
        except Exception:
            pass  # Runner may fail after the dispatch — that's fine for this test

        assert ran.get("called"), "Runner should have been called"
        assert ran["engine_key"] == "htdemucs_ft"
