"""Tests for audio/click_render.py"""
import pytest
from audio.click_render import (
    default_grouping,
    normalise_grouping,
    group_offsets,
    rescale_beats,
    source_index,
    is_downbeat,
    beat_level,
    count_in_beats,
    cache_key,
    LEVEL_WEAK,
    LEVEL_GROUP,
    LEVEL_DOWNBEAT,
    ACCENT_AUTO,
    ACCENT_OFF,
)


# ── default_grouping ──────────────────────────────────────────────────────

@pytest.mark.parametrize("bpb,expected", [
    (4, [4]),
    (3, [3]),
    (6, [3, 3]),
    (9, [3, 3, 3]),
    (5, [3, 2]),
    (7, [3, 2, 2]),
])
def test_default_grouping(bpb, expected):
    assert default_grouping(bpb) == expected

def test_default_grouping_zero():
    assert default_grouping(0) == []


# ── normalise_grouping ────────────────────────────────────────────────────

def test_normalise_grouping_valid():
    assert normalise_grouping([3, 3], 6) == [3, 3]

def test_normalise_grouping_wrong_sum():
    # sum([3,2]) == 5 but bpb == 4 → falls back to default
    assert normalise_grouping([3, 2], 4) == [4]

def test_normalise_grouping_none():
    assert normalise_grouping(None, 4) == [4]

def test_normalise_grouping_non_ints():
    assert normalise_grouping([1.5, 2.5], 4) == [4]


# ── group_offsets ─────────────────────────────────────────────────────────

def test_group_offsets_four():
    # [4] → no sub-beats
    assert group_offsets([4]) == set()

def test_group_offsets_six():
    # [3,3] → offset 3
    assert group_offsets([3, 3]) == {3}

def test_group_offsets_five():
    # [3,2] → offset 3
    assert group_offsets([3, 2]) == {3}


# ── rescale_beats ─────────────────────────────────────────────────────────

def test_rescale_2x():
    beats = [0.0, 1.0, 2.0]
    out = rescale_beats(beats, 2.0)
    assert len(out) == 5
    assert out[0] == pytest.approx(0.0)
    assert out[1] == pytest.approx(0.5)
    assert out[-1] == pytest.approx(2.0)

def test_rescale_half():
    beats = [0.0, 0.5, 1.0, 1.5, 2.0]
    out = rescale_beats(beats, 0.5)
    assert out == [0.0, 1.0, 2.0]

def test_rescale_1x():
    beats = [0.0, 1.0, 2.0]
    assert rescale_beats(beats, 1.0) == beats


# ── source_index ──────────────────────────────────────────────────────────

def test_source_index_1x():
    for i in range(6):
        assert source_index(i, 1.0) == i

def test_source_index_2x_even():
    assert source_index(0, 2.0) == 0
    assert source_index(2, 2.0) == 1

def test_source_index_2x_odd_returns_none():
    assert source_index(1, 2.0) is None

def test_source_index_half():
    assert source_index(0, 0.5) == 0
    assert source_index(2, 0.5) == 4


# ── is_downbeat ───────────────────────────────────────────────────────────

def test_is_downbeat_accent_off():
    assert not is_downbeat(0, [], ACCENT_OFF)

def test_is_downbeat_accent_4():
    assert is_downbeat(0, [], 4)
    assert is_downbeat(4, [], 4)
    assert not is_downbeat(2, [], 4)


# ── beat_level ────────────────────────────────────────────────────────────

def test_beat_level_accent_off():
    assert beat_level(0, [], ACCENT_OFF) == LEVEL_WEAK
    assert beat_level(2, [], ACCENT_OFF) == LEVEL_WEAK

def test_beat_level_downbeat():
    assert beat_level(0, [], 4) == LEVEL_DOWNBEAT
    assert beat_level(4, [], 4) == LEVEL_DOWNBEAT

def test_beat_level_weak():
    assert beat_level(1, [], 4) == LEVEL_WEAK
    assert beat_level(3, [], 4) == LEVEL_WEAK

def test_beat_level_group_6_8():
    # In 6/8 with default grouping [3,3], beat 3 is a group beat
    assert beat_level(3, [], 6) == LEVEL_GROUP
    assert beat_level(0, [], 6) == LEVEL_DOWNBEAT
    assert beat_level(1, [], 6) == LEVEL_WEAK

def test_beat_level_none_index():
    assert beat_level(None, [], 4) == LEVEL_WEAK


# ── count_in_beats ────────────────────────────────────────────────────────

def test_count_in_basic():
    beats = [float(i) for i in range(20)]
    lead_in, clicks = count_in_beats(beats, [], count_bars=1, multiplier=1.0, accent_mode=4)
    assert lead_in > 0
    assert len(clicks) == 4

def test_count_in_two_bars():
    beats = [float(i) for i in range(20)]
    lead_in, clicks = count_in_beats(beats, [], count_bars=2, multiplier=1.0, accent_mode=4)
    assert len(clicks) == 8

def test_count_in_zero_bars():
    beats = [float(i) for i in range(20)]
    lead_in, clicks = count_in_beats(beats, [], count_bars=0)
    assert lead_in == 0.0
    assert clicks == []

def test_count_in_empty_beats():
    lead_in, clicks = count_in_beats([], [], count_bars=1)
    assert lead_in == 0.0
    assert clicks == []


# ── cache_key ─────────────────────────────────────────────────────────────

def test_cache_key_deterministic():
    beats = [0.0, 1.0, 2.0]
    k1 = cache_key("song1", beats, [], 60.0, 44100, 1.0, ACCENT_AUTO)
    k2 = cache_key("song1", beats, [], 60.0, 44100, 1.0, ACCENT_AUTO)
    assert k1 == k2

def test_cache_key_different_songs():
    beats = [0.0, 1.0, 2.0]
    k1 = cache_key("song1", beats, [], 60.0, 44100, 1.0, ACCENT_AUTO)
    k2 = cache_key("song2", beats, [], 60.0, 44100, 1.0, ACCENT_AUTO)
    assert k1 != k2

def test_cache_key_different_beats():
    k1 = cache_key("song1", [0.0, 1.0], [], 60.0, 44100, 1.0, ACCENT_AUTO)
    k2 = cache_key("song1", [0.0, 0.5], [], 60.0, 44100, 1.0, ACCENT_AUTO)
    assert k1 != k2

def test_cache_key_multiplier_matters():
    beats = [0.0, 1.0, 2.0]
    k1 = cache_key("s", beats, [], 60.0, 44100, 1.0, ACCENT_AUTO)
    k2 = cache_key("s", beats, [], 60.0, 44100, 2.0, ACCENT_AUTO)
    assert k1 != k2
