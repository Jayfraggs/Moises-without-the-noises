import json

import pytest

from audio.harmonic_context import KeyMap, KeyMapEntry, get_scale_degrees, is_chromatic, load_or_build_key_map, note_name_to_pitch_class, spell_pitch


def test_note_names_and_enharmonic_spelling_are_key_aware():
    assert note_name_to_pitch_class("Db") == 1
    assert spell_pitch(70, "F", "major") == "Bb"
    assert spell_pitch(70, "B", "major") == "A#"
    with pytest.raises(ValueError):
        note_name_to_pitch_class("H")


def test_scale_and_chromatic_checks():
    assert get_scale_degrees("C", "major") == [0, 2, 4, 5, 7, 9, 11]
    assert not is_chromatic(60, "C", "major")
    assert is_chromatic(61, "C", "major")


def test_key_map_reads_legacy_payload_and_selects_by_time():
    legacy = KeyMap.from_dict({"key": "A min", "key_confidence": 83})
    assert legacy.entries[0].mode == "minor"
    assert legacy.entries[0].confidence == pytest.approx(0.83)
    key_map = KeyMap([KeyMapEntry("C", "major", 0.9, 0.0, 10.0), KeyMapEntry("F", "major", 0.8, 10.0, None)])
    assert key_map.get_key_at(10.0).tonic == "F"
    assert key_map.spell_pitch_at(70, 11.0) == "Bb"


def test_legacy_cache_is_migrated_in_place(tmp_path):
    cache_path = tmp_path / "key.json"
    cache_path.write_text(json.dumps({"key": "C major", "key_confidence": 91}), encoding="utf-8")
    key_map = load_or_build_key_map(tmp_path / "unused.wav", cache_path)
    migrated = json.loads(cache_path.read_text(encoding="utf-8"))
    assert key_map.entries[0].confidence == pytest.approx(0.91)
    assert migrated["schema_version"] == "2.0"
    assert migrated["key_map"][0]["tonic"] == "C"
