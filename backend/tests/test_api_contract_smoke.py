import json
import struct
import wave
from pathlib import Path

from fastapi.testclient import TestClient

import main as m


def _make_song(data_dir: Path, song_id: str, stems=("vocals", "drums")) -> Path:
    d = data_dir / song_id
    d.mkdir(parents=True, exist_ok=True)
    manifest = {
        "song_id": song_id,
        "title": song_id.replace("_", " ").title(),
        "stems": list(stems),
        "notes_available": [],
        "has_lyrics": False,
        "has_beats": True,
        "has_key": True,
        "bpm": 120.0,
        "key": "C maj",
        "stem_presence": {s: 80 for s in stems},
    }
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def _wav(path: Path):
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            w.writeframes(struct.pack("<2205h", *([0] * 2205)))

    for stem in stems:
        _wav(d / f"{stem}.wav")

    (d / "beats.json").write_text(json.dumps({"bpm": 120.0, "beats": [0.0, 0.5, 1.0, 1.5], "edited": False}), encoding="utf-8")
    return d


def test_beats_patch_and_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("MWTN_DATA_DIR", str(tmp_path))
    original = m.DATA_DIR
    m.DATA_DIR = tmp_path
    try:
        client = TestClient(m.app)
        _make_song(tmp_path, "smoke_beats")

        r = client.patch("/api/songs/smoke_beats/beats", json={"beats": [0.0, 0.5, 1.0, 1.5, 2.0], "bars": []})
        assert r.status_code == 200
        assert r.json()["edited"] is True

        r2 = client.get("/api/songs/smoke_beats/beats")
        assert r2.status_code == 200
        assert r2.json()["beats"][:5] == [0.0, 0.5, 1.0, 1.5, 2.0]
    finally:
        m.DATA_DIR = original


def test_waveform_shape_and_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("MWTN_DATA_DIR", str(tmp_path))
    original = m.DATA_DIR
    m.DATA_DIR = tmp_path
    try:
        client = TestClient(m.app)
        _make_song(tmp_path, "smoke_waveform")

        r = client.get("/api/songs/smoke_waveform/stems/vocals/waveform")
        assert r.status_code == 200
        data = r.json()
        assert "peaks" in data
        assert "rms" in data
        assert isinstance(data["peaks"], list)

        r2 = client.get("/api/songs/smoke_waveform/stems/vocals/waveform")
        assert r2.status_code == 200
        assert r2.json()["rms"] == data["rms"]
    finally:
        m.DATA_DIR = original


def test_scan_handles_empty_root_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("MWTN_DATA_DIR", str(tmp_path / "data"))
    original = m.DATA_DIR
    m.DATA_DIR = tmp_path / "data"
    m.DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        client = TestClient(m.app)
        r = client.post("/api/scan", json={"path": str(tmp_path)})
        assert r.status_code == 200
        body = r.json()
        assert body["scanned"] == 0
        assert body["ingested"] == []
        assert body["errors"] == []
    finally:
        m.DATA_DIR = original


def test_soundfile_runtime_error_compatibility():
    import soundfile

    assert hasattr(soundfile, "SoundFileRuntimeError")
    assert hasattr(soundfile, "SoundFileError")
