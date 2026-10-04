"""Tests for audio/key_detection.py"""
import pytest
from audio.key_detection import _correlate, _detect_key, _MAJOR_PROFILE, _MINOR_PROFILE


# ── _correlate ─────────────────────────────────────────────────────────────

def test_correlate_perfect_match():
    profile = _MAJOR_PROFILE
    chroma  = list(profile)  # perfect match, no shift
    r = _correlate(profile, chroma, shift=0)
    assert r == pytest.approx(1.0, abs=1e-6)


def test_correlate_returns_float():
    chroma = [0.5] * 12
    r = _correlate(_MAJOR_PROFILE, chroma, shift=0)
    assert isinstance(r, float)


def test_correlate_zero_variance_chroma():
    # Constant chroma → denom_c = 0 → should return 0 without crash
    chroma = [0.5] * 12
    r = _correlate(_MAJOR_PROFILE, chroma, shift=0)
    assert r == 0.0


def test_correlate_shift_wraps():
    chroma = [1.0] + [0.0] * 11
    # Shifting by 1 should give different result than shift 0
    r0 = _correlate(_MAJOR_PROFILE, chroma, shift=0)
    r1 = _correlate(_MAJOR_PROFILE, chroma, shift=1)
    assert r0 != r1


# ── _detect_key ────────────────────────────────────────────────────────────

def test_detect_key_c_major():
    """C-major chroma emphasises C, E, G (indices 0, 4, 7)."""
    chroma = [0.0] * 12
    for i in (0, 4, 7):
        chroma[i] = 1.0
    key, scale, confidence = _detect_key(chroma)
    assert "C" in key
    assert scale == "Major"
    assert 0 <= confidence <= 100


def test_detect_key_a_minor():
    """A-minor chroma emphasises A, C, E (indices 9, 0, 4)."""
    chroma = [0.0] * 12
    for i in (9, 0, 4):
        chroma[i] = 1.0
    key, scale, confidence = _detect_key(chroma)
    assert "A" in key
    assert scale == "Natural Minor"


def test_detect_key_returns_tuple():
    chroma = [1.0 / 12] * 12  # flat chroma — result ambiguous but should not crash
    result = _detect_key(chroma)
    assert len(result) == 3


def test_detect_key_confidence_range():
    chroma = [0.0] * 12
    chroma[0] = 1.0  # pure C
    _, _, conf = _detect_key(chroma)
    assert 0 <= conf <= 100


def test_detect_key_all_pitches():
    """Smoke test all 12 roots in both modes — none should raise."""
    for root in range(12):
        chroma = [0.0] * 12
        chroma[root] = 1.0
        chroma[(root + 4) % 12] = 0.8
        chroma[(root + 7) % 12] = 0.6
        key, scale, conf = _detect_key(chroma)
        assert key is not None
        assert scale in ("Major", "Natural Minor")
