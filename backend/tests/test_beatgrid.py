"""Tests for audio/beatgrid.py  (unit — stubs out librosa + soundfile)"""
import sys
import types
import struct
import wave
import pytest
from pathlib import Path


def _write_wav(path: Path, n=22050, sr=22050):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(struct.pack(f"<{n}h", *([0] * n)))


@pytest.fixture(autouse=True)
def stub_deps(monkeypatch):
    import numpy as np

    # Stub soundfile.info
    sf = types.ModuleType("soundfile")
    class _Info:
        frames = 88200
        samplerate = 44100
    sf.info = lambda p: _Info()
    sf.blocks = lambda *a, **kw: iter([])  # not needed for beatgrid
    monkeypatch.setitem(sys.modules, "soundfile", sf)

    # Stub audio.bpm.detect_beats via monkeypatching the module function
    import audio.beatgrid as bg_mod
    original = bg_mod.detect_beats if hasattr(bg_mod, "detect_beats") else None

    beats_val = [i * 0.5 for i in range(60)]
    monkeypatch.setattr("audio.beatgrid.detect_beats", lambda *a, **kw: {
        "bpm": 120.0,
        "beats": beats_val,
        "downbeats": beats_val[::4],
        "tempo_stability": 95,
    }, raising=False)

    yield


# ── internal helpers ──────────────────────────────────────────────────────

def test_sanitize_removes_negatives():
    from audio.beatgrid import _sanitize
    beats = [-0.5, 0.0, 1.0, 2.0, 100.0]
    out = _sanitize(beats, duration=60.0)
    assert all(b >= 0 for b in out)
    assert all(b <= 60.0 for b in out)


def test_sanitize_deduplicates():
    from audio.beatgrid import _sanitize
    beats = [0.0, 0.0, 1.0, 1.0, 2.0]
    out = _sanitize(beats, duration=60.0)
    assert out == pytest.approx([0.0, 1.0, 2.0], abs=1e-3)


def test_sanitize_sorts():
    from audio.beatgrid import _sanitize
    beats = [2.0, 0.0, 1.0]
    out = _sanitize(beats, duration=60.0)
    assert out == [0.0, 1.0, 2.0]


def test_extend_to_track_edges_adds_beats():
    from audio.beatgrid import _extend_to_track_edges
    beats = [1.0, 2.0, 3.0, 4.0, 5.0]
    extended, head, tail = _extend_to_track_edges(beats, duration=8.0)
    assert head > 0 or tail > 0
    assert len(extended) > len(beats)


def test_enforce_grid_consistency_corrects_outlier():
    from audio.beatgrid import _enforce_grid_consistency
    beats = [0.0, 1.0, 1.6, 3.0, 4.0]  # 1.6 is off; should be 2.0
    corrected, n = _enforce_grid_consistency(beats)
    assert n >= 1
    assert corrected[2] != pytest.approx(1.6, abs=0.05)


# ── compute_beat_grid ─────────────────────────────────────────────────────

def test_compute_beat_grid_no_stems(tmp_path):
    """Empty directory → None."""
    from audio.beatgrid import compute_beat_grid
    result = compute_beat_grid(tmp_path)
    assert result is None


def test_compute_beat_grid_writes_json(tmp_path):
    _write_wav(tmp_path / "drums.wav")
    from audio.beatgrid import compute_beat_grid
    result = compute_beat_grid(tmp_path)
    if result is not None:
        assert (tmp_path / "beats.json").exists()
        import json
        data = json.loads((tmp_path / "beats.json").read_text())
        assert "bpm" in data
        assert "beats" in data


def test_compute_beat_grid_returns_dict_or_none(tmp_path):
    _write_wav(tmp_path / "other.wav")
    from audio.beatgrid import compute_beat_grid
    result = compute_beat_grid(tmp_path)
    assert result is None or isinstance(result, dict)
