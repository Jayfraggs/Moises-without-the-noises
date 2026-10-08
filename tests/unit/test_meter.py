"""Synthetic unit tests for beat-grid and meter-analysis logic."""

import json

import pytest

from backend.audio.meter import (
    TimeSig,
    build_beat_grid,
    detect_time_signature,
)


pytestmark = pytest.mark.unit


def make_beat_times(bpm: float, duration_s: float, start_s: float = 0.0) -> list[float]:
    """Generate synthetic beat times at a given BPM."""
    beat_interval = 60.0 / bpm
    times = []
    time_s = start_s
    while time_s < start_s + duration_s:
        times.append(round(time_s, 6))
        time_s += beat_interval
    return times


def make_downbeat_times(beat_times: list[float], beats_per_measure: int) -> list[float]:
    """Every Nth beat is a downbeat."""
    return [beat_times[index] for index in range(0, len(beat_times), beats_per_measure)]


class TestTimeSig:
    def test_4_4_beats_per_measure(self) -> None:
        assert TimeSig(4, 4).beats_per_measure() == 4

    def test_3_4_ticks_per_measure(self) -> None:
        assert TimeSig(3, 4).ticks_per_measure() == 72

    def test_6_8_ticks_per_measure(self) -> None:
        assert TimeSig(6, 8).ticks_per_measure() == 144


class TestDetectTimeSignature:
    def test_4_4_from_clean_downbeats(self) -> None:
        beats = make_beat_times(120.0, 8.0)

        time_sig, assumed = detect_time_signature(beats, make_downbeat_times(beats, 4))

        assert time_sig == TimeSig(4, 4)
        assert assumed is False

    def test_3_4_from_clean_downbeats(self) -> None:
        beats = make_beat_times(120.0, 6.0)

        time_sig, assumed = detect_time_signature(beats, make_downbeat_times(beats, 3))

        assert time_sig == TimeSig(3, 4)
        assert assumed is False

    def test_no_downbeats_assumes_4_4(self) -> None:
        time_sig, assumed = detect_time_signature(make_beat_times(120.0, 8.0), [])

        assert time_sig == TimeSig(4, 4)
        assert assumed is True

    def test_one_downbeat_assumes_4_4(self) -> None:
        time_sig, assumed = detect_time_signature(make_beat_times(120.0, 8.0), [0.0])

        assert time_sig == TimeSig(4, 4)
        assert assumed is True

    def test_noisy_downbeats_still_detects(self) -> None:
        beats = make_beat_times(120.0, 8.0)
        downbeats = [beats[index] + jitter for index, jitter in zip(range(0, 16, 4), (0.02, -0.02, 0.02, -0.02))]

        time_sig, assumed = detect_time_signature(beats, downbeats)

        assert time_sig == TimeSig(4, 4)
        assert assumed is False


class TestBuildBeatGrid:
    @staticmethod
    def build_grid(beats_per_measure: int = 4):
        beats = make_beat_times(120.0, 8.0)
        return build_beat_grid(
            beats,
            make_downbeat_times(beats, beats_per_measure),
            TimeSig(beats_per_measure, 4),
        )

    def test_grid_entry_count_matches_beats(self) -> None:
        assert len(self.build_grid().entries) == 16

    def test_measure_numbers_correct_4_4(self) -> None:
        assert [entry.measure_number for entry in self.build_grid().entries] == [
            1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4
        ]

    def test_measure_numbers_correct_3_4(self) -> None:
        grid = self.build_grid(beats_per_measure=3)

        assert [entry.measure_number for entry in grid.entries[:6]] == [1, 1, 1, 2, 2, 2]

    def test_beat_in_measure_cycles(self) -> None:
        assert [entry.beat_in_measure for entry in self.build_grid().entries] == [1, 2, 3, 4] * 4

    def test_downbeat_flag_set_correctly(self) -> None:
        for entry in self.build_grid().entries:
            assert entry.is_downbeat is (entry.beat_in_measure == 1)

    def test_tempo_bpm_roughly_correct(self) -> None:
        assert all(abs(entry.tempo_bpm - 120.0) <= 5 for entry in self.build_grid().entries)

    def test_tempo_map_has_at_least_one_entry(self) -> None:
        assert len(self.build_grid().tempo_map) >= 1

    def test_tempo_map_detects_change(self) -> None:
        beats = make_beat_times(120.0, 4.0) + make_beat_times(160.0, 3.0, start_s=4.0)
        grid = build_beat_grid(beats, make_downbeat_times(beats, 4), TimeSig(4, 4))

        assert len(grid.tempo_map) >= 2


class TestBeatGridMethods:
    @staticmethod
    def build_grid():
        beats = make_beat_times(120.0, 8.0)
        return build_beat_grid(beats, make_downbeat_times(beats, 4), TimeSig(4, 4))

    def test_get_beat_at_time_exact(self) -> None:
        grid = self.build_grid()

        assert grid.get_beat_at_time(1.0) == grid.entries[2]

    def test_get_beat_at_time_between_beats(self) -> None:
        grid = self.build_grid()

        assert grid.get_beat_at_time(1.25) == grid.entries[2]

    def test_get_beat_at_time_before_first(self) -> None:
        grid = self.build_grid()

        assert grid.get_beat_at_time(-1.0) == grid.entries[0]

    def test_get_beat_at_time_after_last(self) -> None:
        grid = self.build_grid()

        assert grid.get_beat_at_time(99.0) == grid.entries[-1]

    def test_get_measure_range_valid(self) -> None:
        measure_range = self.build_grid().get_measure_range(1)

        assert measure_range is not None
        assert measure_range[0] == pytest.approx(0.0)
        assert measure_range[1] == pytest.approx(2.0)

    def test_get_measure_range_invalid(self) -> None:
        assert self.build_grid().get_measure_range(9999) is None

    def test_to_dict_is_json_serializable(self) -> None:
        json.dumps(self.build_grid().to_dict())

    def test_to_dict_contains_legacy_fields(self) -> None:
        serialized = self.build_grid().to_dict()

        assert "beats" in serialized
        assert "bpm" in serialized
