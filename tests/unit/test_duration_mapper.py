"""Deterministic unit coverage for tick-based duration conversion helpers."""

import pytest

from backend.audio.duration_mapper import (
    DURATION_TABLE,
    TICKS_PER_BEAT,
    TICKS_PER_WHOLE,
    TRIPLET_TABLE,
    duration_name_to_ticks,
    quarter_length_to_ticks,
    seconds_to_ticks,
    ticks_to_duration_name,
    ticks_to_quarter_length,
    ticks_to_seconds,
)


pytestmark = pytest.mark.unit


class TestDurationConstants:
    def test_ticks_per_beat(self) -> None:
        assert TICKS_PER_BEAT == 24

    def test_ticks_per_whole(self) -> None:
        assert TICKS_PER_WHOLE == 96

    def test_duration_table_sorted_descending(self) -> None:
        ticks = [entry[0] for entry in DURATION_TABLE]
        assert all(current > following for current, following in zip(ticks, ticks[1:]))

    def test_no_negative_ticks_in_table(self) -> None:
        assert all(ticks > 0 for ticks, _, _ in DURATION_TABLE)


class TestTicksToDurationName:
    @pytest.mark.parametrize(
        ("ticks", "expected"),
        [
            (96, ("whole", False, None)),
            (48, ("half", False, None)),
            (72, ("half", True, None)),
            (24, ("quarter", False, None)),
            (36, ("quarter", True, None)),
            (12, ("eighth", False, None)),
            (18, ("eighth", True, None)),
            (6, ("sixteenth", False, None)),
            (3, ("thirty-second", False, None)),
        ],
    )
    def test_standard_duration_names(
        self, ticks: int, expected: tuple[str, bool, str | None]
    ) -> None:
        assert ticks_to_duration_name(ticks) == expected

    def test_quarter_triplet(self) -> None:
        name, dotted, tuplet = ticks_to_duration_name(16)

        assert name != "unknown"
        assert (name, dotted, tuplet) == ("eighth", False, "triplet")

    def test_unknown_returns_unknown(self) -> None:
        assert ticks_to_duration_name(97)[0] == "unknown"

    def test_never_raises_on_any_int(self) -> None:
        for ticks in range(201):
            ticks_to_duration_name(ticks)

    def test_tolerance_accepts_near_match(self) -> None:
        assert ticks_to_duration_name(25, tolerance=2) == ("quarter", False, None)

    def test_tolerance_zero_strict(self) -> None:
        assert ticks_to_duration_name(25, tolerance=0)[0] == "unknown"


class TestDurationNameToTicks:
    def test_quarter_to_ticks(self) -> None:
        assert duration_name_to_ticks("quarter") == 24

    def test_dotted_quarter(self) -> None:
        assert duration_name_to_ticks("quarter", dotted=True) == 36

    def test_whole_to_ticks(self) -> None:
        assert duration_name_to_ticks("whole") == 96

    def test_unknown_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown duration name"):
            duration_name_to_ticks("hundredth")

    def test_roundtrip_all_durations(self) -> None:
        for ticks, expected_name, expected_dotted in DURATION_TABLE:
            name, dotted, tuplet = ticks_to_duration_name(ticks)

            assert (name, dotted, tuplet) == (expected_name, expected_dotted, None)
            assert duration_name_to_ticks(name, dotted=dotted, tuplet=tuplet) == ticks

        for ticks, expected_name, expected_tuplet in TRIPLET_TABLE:
            name, dotted, tuplet = ticks_to_duration_name(ticks)

            assert (name, dotted, tuplet) == (expected_name, False, expected_tuplet)
            assert duration_name_to_ticks(name, dotted=dotted, tuplet=tuplet) == ticks


class TestConversionFunctions:
    def test_ticks_to_quarter_length_quarter(self) -> None:
        assert ticks_to_quarter_length(24) == 1.0

    def test_ticks_to_quarter_length_half(self) -> None:
        assert ticks_to_quarter_length(48) == 2.0

    def test_quarter_length_to_ticks(self) -> None:
        assert quarter_length_to_ticks(1.0) == 24

    def test_seconds_to_ticks_120bpm_quarter(self) -> None:
        assert seconds_to_ticks(0.5, 120.0) == 24

    def test_seconds_to_ticks_60bpm_whole(self) -> None:
        assert seconds_to_ticks(4.0, 60.0) == 96

    def test_ticks_to_seconds_120bpm(self) -> None:
        assert abs(ticks_to_seconds(24, 120.0) - 0.5) < 0.001

    def test_roundtrip_seconds_at_120bpm(self) -> None:
        assert seconds_to_ticks(ticks_to_seconds(24, 120.0), 120.0) == 24
