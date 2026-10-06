"""Pure unit tests for chord-label parsing, merging, and beat alignment."""

import pytest

from backend.audio.chord_detection import (
    _merge_consecutive_chords,
    align_chords_to_beat_grid,
    parse_chord_label,
)
from backend.audio.harmonic_context import KeyMap
from backend.audio.meter import TimeSig, build_beat_grid
from backend.schema.events import ChordEvent


pytestmark = pytest.mark.unit
pytestmark_integration = pytest.mark.integration


def _grid():
    beat_times = [index * 0.5 for index in range(16)]
    downbeats = beat_times[::4]
    return build_beat_grid(beat_times, downbeats, TimeSig(4, 4))


class TestParseChordLabel:
    def test_major_triad(self):
        assert parse_chord_label("C:maj") == ("C", "major", [])

    def test_minor_triad(self):
        assert parse_chord_label("G:min") == ("G", "minor", [])

    def test_dominant_seventh(self):
        root, quality, extensions = parse_chord_label("F:7")
        assert root == "F"
        assert quality in {"dominant7", "7"}
        assert "7" in extensions

    def test_major_seventh(self):
        root, quality, _ = parse_chord_label("Bb:maj7")
        assert root == "Bb"
        assert quality == "major7"

    def test_no_chord_silence(self):
        root, quality, _ = parse_chord_label("N")
        assert root == "N"
        assert quality in {"none", "no_chord"}

    def test_root_name_preserved(self):
        assert parse_chord_label("Db:min")[0] == "Db"

    def test_unknown_quality_has_fallback(self):
        root, quality, extensions = parse_chord_label("C:unknown")
        assert root == "C"
        assert quality
        assert isinstance(extensions, list)


class TestMergeConsecutiveChords:
    def test_same_chord_merges(self):
        result = _merge_consecutive_chords([(0.0, 1.0, "C:maj", 0.8), (1.0, 2.0, "C:maj", 0.7)])
        assert result == [(0.0, 2.0, "C:maj", 0.8)]

    def test_different_chords_not_merged(self):
        result = _merge_consecutive_chords([(0.0, 1.0, "C:maj", 0.8), (1.0, 2.0, "G:maj", 0.7)])
        assert len(result) == 2

    def test_empty_list_returns_empty(self):
        assert _merge_consecutive_chords([]) == []

    def test_merged_duration_covers_both(self):
        result = _merge_consecutive_chords([(0.0, 1.0, "C:maj", 0.8), (1.0, 3.5, "C:maj", 0.7)])
        assert result[0][1] == 3.5

    def test_three_same_merges_to_one(self):
        result = _merge_consecutive_chords([(0.0, 1.0, "C:maj", 0.8), (1.0, 2.0, "C:maj", 0.7), (2.0, 4.0, "C:maj", 0.9)])
        assert len(result) == 1
        assert result[0][1] == 4.0


class TestAlignChordsToGrid:
    def test_chord_gets_beat_aligned_start(self):
        events = align_chords_to_beat_grid([(2.1, 3.0, "C:maj", 0.8)], _grid(), KeyMap.from_single_key("C", "major", 0.9), "test")
        assert events[0].beat_aligned_start == {"measure": 2, "beat": 1}

    def test_silence_segments_filtered(self):
        events = align_chords_to_beat_grid([(0.0, 1.0, "N", 1.0)], _grid(), KeyMap.from_single_key("C", "major", 0.9), "test")
        assert events == []

    def test_output_is_chord_events(self):
        events = align_chords_to_beat_grid([(0.0, 1.0, "C:maj", 0.8)], _grid(), KeyMap.from_single_key("C", "major", 0.9), "test")
        assert all(isinstance(event, ChordEvent) for event in events)

    def test_confidence_preserved(self):
        events = align_chords_to_beat_grid([(0.0, 1.0, "C:maj", 0.73)], _grid(), KeyMap.from_single_key("C", "major", 0.9), "test")
        assert events[0].confidence == pytest.approx(0.73)


@pytestmark_integration
def test_detect_chords_autochord_returns_list(c_major_scale_path):
    autochord = pytest.importorskip("autochord", reason="autochord not installed")
    del autochord
    from backend.audio.chord_detection import detect_chords_autochord

    assert isinstance(detect_chords_autochord(c_major_scale_path), list)


@pytestmark_integration
def test_detect_chords_librosa_fallback(c_major_scale_path):
    from backend.audio.chord_detection import detect_chords_librosa

    assert detect_chords_librosa(c_major_scale_path)
