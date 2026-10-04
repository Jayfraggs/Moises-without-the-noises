"""Tests for audio/bpm.py  (unit — no real audio, mocks librosa)"""
import sys
import types
import pytest


def _make_librosa_stub(bpm=120.0, beat_frames=None):
    """
    Minimal librosa stub that makes detect_beats testable without a real WAV.
    """
    import numpy as np

    if beat_frames is None:
        beat_frames = np.arange(0, 200, 10, dtype=int)

    lib = types.ModuleType("librosa")
    lib.load = lambda *a, **kw: (np.zeros(22050), 22050)
    lib.beat = types.SimpleNamespace(
        beat_track=lambda y, sr, units, trim: (
            np.array([bpm]),
            beat_frames,
        )
    )
    lib.effects = types.SimpleNamespace(
        hpss=lambda y: (y * 0.5, y * 0.5),
    )
    lib.frames_to_time = lambda frames, sr: (frames / sr).astype(float)
    return lib


@pytest.fixture(autouse=True)
def stub_librosa(monkeypatch):
    lib = _make_librosa_stub()
    monkeypatch.setitem(sys.modules, "librosa", lib)
    # Remove cached import if already loaded
    if "audio.bpm" in sys.modules:
        del sys.modules["audio.bpm"]
    yield
    if "audio.bpm" in sys.modules:
        del sys.modules["audio.bpm"]


def test_returns_bpm(tmp_path):
    wav = tmp_path / "drums.wav"
    wav.touch()
    from audio.bpm import detect_beats
    result = detect_beats(str(wav))
    assert "bpm" in result
    assert result["bpm"] == pytest.approx(120.0, abs=1.0)


def test_returns_beats_list(tmp_path):
    wav = tmp_path / "drums.wav"
    wav.touch()
    from audio.bpm import detect_beats
    result = detect_beats(str(wav))
    assert isinstance(result["beats"], list)
    assert len(result["beats"]) > 0


def test_returns_downbeats(tmp_path):
    wav = tmp_path / "drums.wav"
    wav.touch()
    from audio.bpm import detect_beats
    result = detect_beats(str(wav))
    assert "downbeats" in result
    assert isinstance(result["downbeats"], list)
    # Downbeats are every 4th beat
    assert len(result["downbeats"]) <= len(result["beats"])


def test_returns_tempo_stability(tmp_path):
    wav = tmp_path / "drums.wav"
    wav.touch()
    from audio.bpm import detect_beats
    result = detect_beats(str(wav))
    assert "tempo_stability" in result
    # Either None or 0-100
    ts = result["tempo_stability"]
    if ts is not None:
        assert 0 <= ts <= 100


def test_perfectly_regular_beats_high_stability(tmp_path, monkeypatch):
    """Perfectly evenly spaced beats → tempo_stability should be near 100."""
    import numpy as np
    lib = _make_librosa_stub(bpm=120.0, beat_frames=np.arange(0, 4800, 240, dtype=int))
    monkeypatch.setitem(sys.modules, "librosa", lib)
    if "audio.bpm" in sys.modules:
        del sys.modules["audio.bpm"]

    wav = tmp_path / "drums.wav"
    wav.touch()
    from audio.bpm import detect_beats
    result = detect_beats(str(wav))
    ts = result.get("tempo_stability")
    if ts is not None:
        assert ts >= 90, f"Expected near-100 stability, got {ts}"
