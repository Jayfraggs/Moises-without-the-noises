"""Pure unit tests for harmonic context and key-aware pitch spelling."""

import json

import pytest

from backend.audio.harmonic_context import (
    KeyMap,
    KeyMapEntry,
    SCALE_INTERVALS,
    get_scale_degrees,
    is_chromatic,
    note_name_to_pitch_class,
    spell_pitch,
)


pytestmark = pytest.mark.unit


class TestNoteNameToPitchClass:
    def test_c_is_0(self):
        assert note_name_to_pitch_class("C") == 0

    def test_c_sharp_is_1(self):
        assert note_name_to_pitch_class("C#") == 1

    def test_db_is_1(self):
        assert note_name_to_pitch_class("Db") == 1

    def test_f_sharp_is_6(self):
        assert note_name_to_pitch_class("F#") == 6

    def test_bb_is_10(self):
        assert note_name_to_pitch_class("Bb") == 10

    def test_b_is_11(self):
        assert note_name_to_pitch_class("B") == 11

    def test_unknown_raises(self):
        with pytest.raises(ValueError):
            note_name_to_pitch_class("X")

    def test_all_12_pitch_classes_covered(self):
        pitch_classes = {
            note_name_to_pitch_class(name)
            for name in ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
        }
        assert pitch_classes == set(range(12))


class TestSpellPitch:
    def test_c_major_uses_sharps(self):
        assert spell_pitch(61, "G", "major") == "C#"

    def test_f_major_uses_flats(self):
        assert spell_pitch(70, "F", "major") == "Bb"

    def test_b_major_uses_sharps(self):
        assert spell_pitch(70, "B", "major") == "A#"

    def test_unambiguous_pitch_unchanged(self):
        assert spell_pitch(60, "C", "major") == "C"

    def test_natural_notes_unchanged(self):
        expected = {"D": 62, "E": 64, "F": 65, "G": 67, "A": 69, "B": 71}
        for name, midi_pitch in expected.items():
            assert spell_pitch(midi_pitch, "F", "major") == name
            assert spell_pitch(midi_pitch, "B", "major") == name


class TestGetScaleDegrees:
    def test_c_major_scale_degrees(self):
        assert get_scale_degrees("C", "major") == [0, 2, 4, 5, 7, 9, 11]

    def test_a_minor_scale_degrees(self):
        assert get_scale_degrees("A", "minor") == [9, 11, 0, 2, 4, 5, 7]

    def test_g_major_includes_f_sharp(self):
        assert 6 in get_scale_degrees("G", "major")

    def test_scale_always_7_degrees(self):
        for tonic in ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"):
            for mode in SCALE_INTERVALS:
                assert len(get_scale_degrees(tonic, mode)) == 7


class TestIsChromatic:
    def test_c_in_c_major_not_chromatic(self):
        assert is_chromatic(60, "C", "major") is False

    def test_c_sharp_in_c_major_is_chromatic(self):
        assert is_chromatic(61, "C", "major") is True

    def test_f_sharp_in_g_major_not_chromatic(self):
        assert is_chromatic(66, "G", "major") is False


class TestKeyMapEntry:
    @pytest.fixture
    def bounded_entry(self):
        return KeyMapEntry("C", "major", 0.9, 0.0, 60.0)

    def test_covers_time_within_range(self, bounded_entry):
        assert bounded_entry.covers_time(30.0) is True

    def test_covers_time_at_start(self, bounded_entry):
        assert bounded_entry.covers_time(0.0) is True

    def test_covers_time_at_end_exclusive(self, bounded_entry):
        assert bounded_entry.covers_time(60.0) is False

    def test_covers_time_open_end(self):
        assert KeyMapEntry("C", "major", 0.9, 0.0, None).covers_time(9999.0) is True

    def test_to_dict_serializable(self, bounded_entry):
        json.dumps(bounded_entry.to_dict())


class TestKeyMap:
    def test_from_single_key_creates_one_entry(self):
        assert len(KeyMap.from_single_key("C", "major", 0.9).entries) == 1

    def test_get_key_at_returns_correct_entry(self):
        key_map = KeyMap([
            KeyMapEntry("C", "major", 0.9, 0.0, 60.0),
            KeyMapEntry("A", "minor", 0.8, 60.0, None),
        ])
        assert key_map.get_key_at(30.0).tonic == "C"
        assert key_map.get_key_at(60.0).tonic == "A"

    def test_get_key_at_before_first_returns_first(self):
        key_map = KeyMap([KeyMapEntry("C", "major", 0.9, 10.0, None)])
        assert key_map.get_key_at(-1.0).tonic == "C"

    def test_spell_pitch_at_uses_active_key(self):
        key_map = KeyMap([
            KeyMapEntry("C", "major", 0.9, 0.0, 60.0),
            KeyMapEntry("A", "minor", 0.8, 60.0, None),
        ])
        assert key_map.spell_pitch_at(70, 30.0) in {"A#", "Bb"}
        assert key_map.spell_pitch_at(70, 65.0) in {"A#", "Bb"}

    def test_from_dict_roundtrip(self):
        original = KeyMap([
            KeyMapEntry("C", "major", 0.9, 0.0, 60.0),
            KeyMapEntry("A", "minor", 0.8, 60.0, None, "user", True),
        ])
        restored = KeyMap.from_dict(original.to_dict())
        assert restored.entries == original.entries
        assert restored.schema_version == original.schema_version

    def test_from_dict_legacy_format(self):
        key_map = KeyMap.from_dict({"key": "G major", "confidence": 0.8})
        assert len(key_map.entries) == 1
        assert key_map.entries[0].tonic == "G"
        assert key_map.entries[0].mode == "major"
        assert key_map.entries[0].confidence == pytest.approx(0.8)
