"""Tests for audio/errors.py"""
import pytest
from audio.errors import SeparationError, classify_failure


def test_classify_oom():
    assert classify_failure("CUDA out of memory. Tried to allocate 2.50 GiB") == "out-of-memory"

def test_classify_oom_mps():
    assert classify_failure("MPS backend out of memory (MPS allocated: 5.12 GB)") == "out-of-memory"

def test_classify_unsupported_device():
    assert classify_failure("no kernel image is available for execution on the device") == "unsupported-device"
    assert classify_failure("torch not compiled with cuda enabled") == "unsupported-device"

def test_classify_disk_full():
    assert classify_failure("OSError: [Errno 28] No space left on device") == "disk-full"
    assert classify_failure("errno 28 write error") == "disk-full"

def test_classify_bad_input():
    assert classify_failure("Invalid data found when processing input") == "bad-input"
    assert classify_failure("Could not open file: /tmp/foo.mp3") == "bad-input"
    assert classify_failure("FFmpeg transcode failed with code -1") == "bad-input"

def test_classify_unknown():
    assert classify_failure("something totally unexpected happened") == "unknown"

def test_classify_case_insensitive():
    assert classify_failure("CUDA OUT OF MEMORY") == "out-of-memory"

def test_classify_empty():
    assert classify_failure("") == "unknown"

def test_separation_error_fields():
    err = SeparationError("boom", tail=["line1", "line2"], device="cpu")
    assert str(err) == "boom"
    assert err.tail == ["line1", "line2"]
    assert err.device == "cpu"

def test_separation_error_defaults():
    err = SeparationError("boom")
    assert err.tail == []
    assert err.device is None
