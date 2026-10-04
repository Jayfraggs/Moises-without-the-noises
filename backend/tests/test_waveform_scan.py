"""Tests for audio/waveform_scan.py"""
import struct
import wave
import math
import pytest
from pathlib import Path
from audio.waveform_scan import scan_stem


def _write_wav(path: Path, samples: list[int], sr: int = 22050):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def _silence(n: int) -> list[int]:
    return [0] * n


def _sine(n: int, amplitude: int = 16383) -> list[int]:
    return [int(amplitude * math.sin(2 * math.pi * i / 100)) for i in range(n)]


# ── basic contracts ────────────────────────────────────────────────────────

def test_returns_peaks_and_rms(tmp_path):
    wav = tmp_path / "test.wav"
    _write_wav(wav, _sine(22050))
    peaks, rms = scan_stem(wav)
    assert isinstance(peaks, list)
    assert isinstance(rms, float)


def test_peaks_are_pairs(tmp_path):
    wav = tmp_path / "test.wav"
    _write_wav(wav, _sine(22050))
    peaks, _ = scan_stem(wav)
    assert all(len(p) == 2 for p in peaks)
    assert all(p[0] <= p[1] for p in peaks)


def test_silence_rms_zero(tmp_path):
    wav = tmp_path / "silence.wav"
    _write_wav(wav, _silence(22050))
    _, rms = scan_stem(wav)
    assert rms == pytest.approx(0.0, abs=1e-6)


def test_silence_peaks_near_zero(tmp_path):
    wav = tmp_path / "silence.wav"
    _write_wav(wav, _silence(22050))
    peaks, _ = scan_stem(wav)
    for lo, hi in peaks:
        assert abs(lo) < 1e-5
        assert abs(hi) < 1e-5


def test_bucket_count_respected(tmp_path):
    wav = tmp_path / "test.wav"
    _write_wav(wav, _sine(44100))
    peaks, _ = scan_stem(wav, buckets=500)
    # May be less than 500 but never more
    assert len(peaks) <= 500
    assert len(peaks) > 0


def test_large_bucket_count(tmp_path):
    wav = tmp_path / "test.wav"
    _write_wav(wav, _sine(22050))
    peaks, _ = scan_stem(wav, buckets=3000)
    assert len(peaks) <= 3000


def test_sine_rms_nonzero(tmp_path):
    wav = tmp_path / "sine.wav"
    _write_wav(wav, _sine(22050))
    _, rms = scan_stem(wav)
    assert rms > 0.05


def test_short_file(tmp_path):
    """Very short file (100 samples) should not crash."""
    wav = tmp_path / "short.wav"
    _write_wav(wav, _sine(100))
    peaks, rms = scan_stem(wav, buckets=1500)
    assert isinstance(peaks, list)
    assert rms >= 0.0


def test_nonexistent_file_raises(tmp_path):
    with pytest.raises(Exception):
        scan_stem(tmp_path / "ghost.wav")
