"""Tests for audio/sections.py"""
import tempfile
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from audio import section_detection
from audio.section_detection import _detect_with_librosa
from audio.sections import normalize_sections, validate_sections, SECTION_COLORS, SECTION_NAMES


def _seg(start, end, kind="verse"):
    return {"start": start, "end": end, "label": kind}


# ── normalize_sections ──────────────────────────────────────────────────────

def test_basic_two_sections():
    raw = [_seg(0, 30, "verse"), _seg(30, 60, "chorus")]
    out = normalize_sections(raw, duration=60.0)
    assert len(out) == 2
    assert out[0]["kind"] == "verse"
    assert out[1]["kind"] == "chorus"
    assert out[0]["start"] == 0.0
    assert out[-1]["end"] == 60.0

def test_start_end_sentinels_stripped():
    raw = [
        _seg(0, 0.1, "start"),
        _seg(0.1, 30, "verse"),
        _seg(30, 60, "chorus"),
        _seg(60, 60.1, "end"),
    ]
    out = normalize_sections(raw, duration=60.1)
    kinds = [s["kind"] for s in out]
    assert "start" not in kinds
    assert "end" not in kinds

def test_gaps_within_tolerance_closed():
    raw = [_seg(0, 29.9, "verse"), _seg(30.1, 60, "chorus")]
    out = normalize_sections(raw, duration=60.0)
    assert len(out) == 2
    assert out[0]["end"] == out[1]["start"]

def test_gap_beyond_tolerance_returns_empty():
    raw = [_seg(0, 20, "verse"), _seg(25, 60, "chorus")]
    out = normalize_sections(raw, duration=60.0)
    assert out == []

def test_very_short_section_merged():
    raw = [_seg(0, 30, "verse"), _seg(30, 30.1, "bridge"), _seg(30.1, 60, "chorus")]
    out = normalize_sections(raw, duration=60.0)
    kinds = [s["kind"] for s in out]
    assert "bridge" not in kinds

def test_empty_input_returns_empty():
    assert normalize_sections([], duration=60.0) == []

def test_single_section_too_few_returns_empty():
    assert normalize_sections([_seg(0, 60, "verse")], duration=60.0) == []

def test_ids_assigned():
    raw = [_seg(0, 30, "verse"), _seg(30, 60, "chorus")]
    out = normalize_sections(raw, duration=60.0)
    assert all("id" in s for s in out)

def test_colors_assigned():
    raw = [_seg(0, 30, "verse"), _seg(30, 60, "chorus")]
    out = normalize_sections(raw, duration=60.0)
    assert out[0]["color"] == SECTION_COLORS["verse"]
    assert out[1]["color"] == SECTION_COLORS["chorus"]

def test_names_assigned():
    raw = [_seg(0, 30, "verse"), _seg(30, 60, "chorus")]
    out = normalize_sections(raw, duration=60.0)
    assert out[0]["name"] == SECTION_NAMES["verse"]
    assert out[1]["name"] == SECTION_NAMES["chorus"]

def test_invalid_kind_returns_empty():
    raw = [_seg(0, 30, "UNKNOWN_KIND"), _seg(30, 60, "chorus")]
    out = normalize_sections(raw, duration=60.0)
    assert out == []

def test_non_dict_item_returns_empty():
    out = normalize_sections(["not a dict"], duration=60.0)
    assert out == []

def test_all_known_kinds_accepted():
    kinds = ["intro", "verse", "chorus", "bridge", "break", "inst", "solo", "outro", "part"]
    raw = [{"start": i * 10, "end": (i + 1) * 10, "label": k} for i, k in enumerate(kinds)]
    out = normalize_sections(raw, duration=len(kinds) * 10.0)
    assert len(out) == len(kinds)


def test_librosa_fallback_returns_segments_for_synthetic_track():
    sr = 22050
    dur = 24.0
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    left = np.sin(2 * np.pi * 220 * t)
    middle = np.sin(2 * np.pi * 330 * t)
    right = np.sin(2 * np.pi * 440 * t)
    y = np.concatenate([
        left[: int(sr * 8)],
        middle[int(sr * 8): int(sr * 16)],
        right[int(sr * 16):],
    ]).astype(np.float32)

    with tempfile.TemporaryDirectory(prefix="mwtn-sections-") as tmpdir:
        path = Path(tmpdir) / "synthetic.wav"
        sf.write(path, y, sr)

        sections = _detect_with_librosa(path, dur)

    assert sections is not None
    assert len(sections) >= 2
    assert sections[0]["start"] == pytest.approx(0.0, abs=1.0)
    assert sections[-1]["end"] >= dur - 1.0


def test_allin1_timeout_falls_back_to_none(monkeypatch):
    import sys
    import types

    def hung_analyze(path):
        time.sleep(1.0)
        return None

    fake_module = types.SimpleNamespace(analyze=hung_analyze)
    monkeypatch.setattr(section_detection, 'ALLIN1_TIMEOUT_SECONDS', 0.15, raising=False)
    monkeypatch.setitem(sys.modules, 'allin1', fake_module)

    start = time.monotonic()
    result = section_detection._detect_with_allin1(Path('dummy.wav'), duration=30.0)
    elapsed = time.monotonic() - start

    assert result is None
    assert elapsed < 0.5


# ── validate_sections ──────────────────────────────────────────────────────

def test_validate_raises_on_empty():
    with pytest.raises(ValueError, match="empty"):
        validate_sections([])

def test_validate_raises_on_bad_data():
    with pytest.raises(ValueError):
        validate_sections([_seg(0, 20, "verse")])  # only 1 → can't be valid

def test_validate_returns_normalised():
    raw = [_seg(0, 30, "verse"), _seg(30, 60, "chorus")]
    out = validate_sections(raw, duration=60.0)
    assert len(out) == 2
    assert all("color" in s for s in out)

def test_validate_infers_duration():
    raw = [_seg(0, 30, "verse"), _seg(30, 60, "chorus")]
    out = validate_sections(raw)  # no explicit duration
    assert out[-1]["end"] == pytest.approx(60.0, abs=0.1)
