"""End-to-end harmonic pipeline tests using local synthetic audio fixtures."""

import json

import pytest

from backend.audio.chord_detection import detect_chords, load_or_detect_chords
from backend.audio.harmonic_context import KeyMap, load_or_build_key_map
from backend.audio.meter import TimeSig, build_beat_grid
from tests.unit.test_meter import make_beat_times, make_downbeat_times


pytestmark = pytest.mark.integration


def _grid():
    beat_times = make_beat_times(120.0, 4.0)
    return build_beat_grid(beat_times, make_downbeat_times(beat_times, 4), TimeSig(4, 4))


class TestKeyMapFromAudio:
    def test_c_major_scale_key_detection(self, c_major_scale_path, tmp_path):
        key_map = load_or_build_key_map(c_major_scale_path, tmp_path / "key.json")
        assert len(key_map.entries) >= 1
        active = key_map.get_key_at(0.0)
        assert active.tonic in ("C", "A")
        assert active.mode in ("major", "minor")
        assert 0.0 <= active.confidence <= 1.0

    def test_key_map_caches_on_second_call(self, c_major_scale_path, tmp_path):
        cache = tmp_path / "key.json"
        first = load_or_build_key_map(c_major_scale_path, cache)
        second = load_or_build_key_map(c_major_scale_path, cache)
        assert first.entries[0].tonic == second.entries[0].tonic

    def test_key_cache_file_written(self, c_major_scale_path, tmp_path):
        cache = tmp_path / "key.json"
        load_or_build_key_map(c_major_scale_path, cache)
        assert cache.exists()
        payload = json.loads(cache.read_text(encoding="utf-8"))
        assert "key_map" in payload
        assert "key" in payload

    def test_silence_produces_a_key_entry(self, silence_path, tmp_path):
        key_map = load_or_build_key_map(silence_path, tmp_path / "key.json")
        assert len(key_map.entries) >= 1


class TestChordDetectionPipeline:
    def test_librosa_fallback_runs_on_c_major(self, c_major_scale_path):
        chords = detect_chords(c_major_scale_path, _grid(), KeyMap.from_single_key("C", "major", 0.9))
        assert isinstance(chords, list)
        assert all(hasattr(chord, "root") for chord in chords)

    def test_chord_events_have_required_fields(self, c_major_scale_path):
        chords = detect_chords(c_major_scale_path, _grid(), KeyMap.from_single_key("C", "major", 0.9))
        for chord in chords:
            assert chord.root
            assert chord.quality
            assert 0.0 <= chord.confidence <= 1.0
            assert chord.start_time >= 0.0

    def test_chord_cache_written(self, c_major_scale_path, tmp_path):
        cache = tmp_path / "chords.json"
        load_or_detect_chords(c_major_scale_path, cache, _grid(), KeyMap.from_single_key("C", "major", 0.9))
        assert cache.exists()
