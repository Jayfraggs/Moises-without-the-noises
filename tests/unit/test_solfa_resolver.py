"""Unit tests for pure movable-do solfège resolution."""

import pytest

from backend.schema.events import NoteEvent, RestEvent
from backend.solfa.solfa_resolver import resolve_solfa

pytestmark = pytest.mark.unit


def make_note(midi_pitch: int) -> NoteEvent:
    return NoteEvent(track_id="vocals", start_time=0.0, end_time=0.5, midi_pitch=midi_pitch, confidence=0.9, source_model="test")


class TestResolveSolfa:
    def test_major_diatonic_scale_is_movable_do(self) -> None:
        result = resolve_solfa([make_note(pitch) for pitch in (60, 62, 64, 65, 67, 69, 71)], 60, "major")

        assert [event.solfa for event in result.events] == ["Do", "Re", "Mi", "Fa", "Sol", "La", "Ti"]

    def test_major_chromatic_degree_uses_standard_syllable(self) -> None:
        assert resolve_solfa([make_note(61)], 60, "major").events[0].solfa == "Ra"

    def test_minor_as_la_maps_tonic_to_la(self) -> None:
        result = resolve_solfa([make_note(pitch) for pitch in (57, 59, 60, 62, 64, 65, 67)], 57, "minor")

        assert [event.solfa for event in result.events] == ["La", "Ti", "Do", "Re", "Mi", "Fa", "Sol"]

    def test_minor_can_use_do_based_mapping(self) -> None:
        assert resolve_solfa([make_note(57)], 57, "minor", minor_as_la=False).events[0].solfa == "Do"

    def test_rest_has_no_solfa(self) -> None:
        rest = RestEvent(track_id="vocals", start_time=0.0, end_time=0.5, duration_s=0.5, confidence=1.0, source_model="test")

        assert resolve_solfa([rest], 60, "major").events[0].solfa is None

    def test_input_events_are_not_mutated(self) -> None:
        event = make_note(60)

        result = resolve_solfa([event], 60, "major")

        assert event.solfa is None
        assert result.events[0] is not event
        assert result.events[0].solfa == "Do"

    def test_result_includes_normalized_key_context(self) -> None:
        result = resolve_solfa([make_note(61)], 61, "MAJOR")

        assert (result.tonic_midi, result.tonic_name, result.mode) == (61, "C#", "major")

    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="mode"):
            resolve_solfa([], 60, "dorian")
