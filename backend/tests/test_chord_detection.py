from audio.chord_detection import _merge_consecutive_chords, parse_chord_label


def test_parse_chord_label_normalizes_supported_qualities():
    assert parse_chord_label("C:maj") == ("C", "major", [])
    assert parse_chord_label("G:min") == ("G", "minor", [])
    assert parse_chord_label("F:7") == ("F", "dominant7", ["7"])
    assert parse_chord_label("Bb:maj7") == ("Bb", "major7", ["7"])
    assert parse_chord_label("N") == ("N", "none", [])


def test_merge_consecutive_chords_preserves_changes():
    merged = _merge_consecutive_chords([(0.0, 1.0, "C:maj", 0.8), (1.0, 2.0, "C:maj", 0.7), (2.0, 3.0, "G:maj", 0.9)])
    assert merged == [(0.0, 2.0, "C:maj", 0.8), (2.0, 3.0, "G:maj", 0.9)]
