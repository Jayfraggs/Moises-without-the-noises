"""Synthetic unit tests for quantization, rests, tuplets, and barlines."""

import pytest

from backend.audio.meter import TimeSig, build_beat_grid
from backend.audio.quantizer import (
    QuantizationConfig, detect_triplets, generate_rests, quantize_event,
    quantize_events, quantize_time, split_at_barline, validate_measure,
)
from backend.schema.events import NoteEvent
from tests.unit.test_meter import make_beat_times, make_downbeat_times

pytestmark = pytest.mark.unit


def make_simple_grid(bpm: float = 120.0, measures: int = 4, time_sig: tuple = (4, 4)):
    beat_times = make_beat_times(bpm, measures * time_sig[0] * 60.0 / bpm)
    return build_beat_grid(beat_times, make_downbeat_times(beat_times, time_sig[0]), TimeSig(*time_sig))


def make_note(start_time: float, end_time: float, midi_pitch: int = 60, track_id: str = "vocals") -> NoteEvent:
    return NoteEvent(start_time=start_time, end_time=end_time, midi_pitch=midi_pitch, confidence=0.9, source_model="test", track_id=track_id)


class TestQuantizeTime:
    def test_snaps_to_beat_start_strict(self):
        position = quantize_time(0.0, make_simple_grid(), QuantizationConfig(mode="strict"))
        assert (position.measure, position.beat, position.subdivision) == (1, 1, 0)

    def test_snaps_to_beat_start_humanized(self):
        position = quantize_time(0.48, make_simple_grid(), QuantizationConfig(mode="humanized"))
        assert (position.measure, position.beat, position.subdivision) == (1, 2, 0)

    def test_humanized_does_not_snap_distant(self):
        position = quantize_time(0.3, make_simple_grid(), QuantizationConfig(mode="humanized"))
        assert position.subdivision not in (0, 24)

    def test_off_mode_no_snap(self):
        position = quantize_time(0.3, make_simple_grid(), QuantizationConfig(mode="off"))
        assert position.subdivision == 14

    def test_returns_last_entry_outside_grid(self):
        grid = make_simple_grid(measures=1)
        assert quantize_time(99.0, grid, QuantizationConfig()) is not None


class TestQuantizeEvent:
    @pytest.mark.parametrize(("end_time", "name", "ticks"), [(0.5, "quarter", 24), (1.0, "half", 48), (2.0, "whole", 96)])
    def test_standard_durations(self, end_time, name, ticks):
        result = quantize_event(make_note(0.0, end_time), make_simple_grid(), QuantizationConfig())
        assert (result["quantized_duration_name"], result["quantized_duration_ticks"]) == (name, ticks)

    def test_raw_timing_preserved_by_quantize_events(self):
        result = quantize_events([make_note(0.1, 0.6)], make_simple_grid(), QuantizationConfig(generate_rests=False))[0]
        assert (result["start_time"], result["end_time"]) == (0.1, 0.6)

    def test_confidence_and_mode(self):
        result = quantize_event(make_note(0.0, 0.5), make_simple_grid(), QuantizationConfig(mode="strict"))
        assert 0.0 <= result["quantization_confidence"] <= 1.0
        assert result["quantization_mode"] == "strict"
        assert result["quantization_confidence"] >= 0.9

    def test_off_beat_has_lower_confidence(self):
        result = quantize_event(make_note(0.2, 0.7), make_simple_grid(), QuantizationConfig())
        assert result["quantization_confidence"] < 0.7


class TestSplitAtBarline:
    def test_note_within_measure_no_split(self):
        result = split_at_barline(make_note(0.0, 0.5), make_simple_grid(), QuantizationConfig())
        assert len(result) == 1 and result[0]["tied_to_next"] is False

    def test_note_crossing_barline_splits_with_ties_and_preserved_ticks(self):
        event = make_note(1.5, 2.5)
        result = split_at_barline(event, make_simple_grid(), QuantizationConfig())
        original = quantize_event(event, make_simple_grid(), QuantizationConfig())
        assert len(result) == 2
        assert result[0]["tied_to_next"] is True and result[1]["tied_from_previous"] is True
        assert sum(item["quantized_duration_ticks"] for item in result) == original["quantized_duration_ticks"]


class TestDetectTriplets:
    def test_three_equal_notes_per_beat_are_triplets(self):
        events = [make_note(start, start + 1 / 6) for start in (0.0, 1 / 6, 2 / 6)]
        assert detect_triplets(events, make_simple_grid(), QuantizationConfig()) == [0, 1, 2]

    def test_four_notes_per_beat_not_triplets(self):
        events = [make_note(start, start + 0.125) for start in (0.0, 0.125, 0.25, 0.375)]
        assert detect_triplets(events, make_simple_grid(), QuantizationConfig()) == []

    def test_insufficient_notes_no_detection(self):
        assert detect_triplets([make_note(0, .1), make_note(.2, .3)], make_simple_grid(), QuantizationConfig()) == []


class TestGenerateRests:
    def test_gap_between_notes_generates_rest_with_correct_timing(self):
        rests = generate_rests([make_note(0, .5), make_note(1, 1.5)], make_simple_grid())
        assert len(rests) == 1
        assert rests[0].start_time == .5 and rests[0].duration_s == .5

    def test_no_gap_no_rest(self):
        assert generate_rests([make_note(0, .5), make_note(.5, 1)], make_simple_grid()) == []


class TestValidateMeasure:
    @pytest.mark.parametrize(("count", "valid"), [(4, True), (3, False), (5, False)])
    def test_measure_duration(self, count, valid):
        result = validate_measure([{"quantized_duration_ticks": 24}] * count, TimeSig(4, 4))
        assert result["valid"] is valid and result["expected_ticks"] == 96
        assert result["total_ticks"] == count * 24


class TestQuantizeEvents:
    def test_empty_list_returns_empty(self):
        assert quantize_events([], make_simple_grid()) == []

    def test_sorted_output_and_rests(self):
        events = [make_note(1, 1.5), make_note(0, .5)]
        result = quantize_events(events, make_simple_grid(), QuantizationConfig(detect_triplets=False))
        assert [item["start_time"] for item in result] == sorted(item["start_time"] for item in result)
        assert any(item["event_type"] == "rest" for item in result)

    def test_all_events_have_quantized_fields_and_validation(self):
        result = quantize_events([make_note(0, .5)], make_simple_grid(), QuantizationConfig(mode="off", generate_rests=False))[0]
        for key in ("quantized_start", "quantized_duration_ticks", "quantized_duration_name", "measure_validation"):
            assert key in result
        assert result["start_time"] == 0.0
