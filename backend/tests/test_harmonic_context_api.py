"""API coverage for Plan 05's additive harmonic-context routes."""

import json
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import main as backend_main

    monkeypatch.setattr(backend_main, "DATA_DIR", tmp_path)
    return TestClient(backend_main.app)


def _create_song(data_dir: Path, song_id: str) -> Path:
    song_dir = data_dir / song_id
    song_dir.mkdir()
    with wave.open(str(song_dir / "vocals.wav"), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(22050)
        wav.writeframes(b"\x00\x00" * 2205)
    (song_dir / "key.json").write_text(json.dumps({"key": "C maj", "key_confidence": 82}), encoding="utf-8")
    return song_dir


def test_get_key_map_migrates_legacy_key_cache(client: TestClient, tmp_path: Path) -> None:
    _create_song(tmp_path, "key_map_song")

    response = client.get("/api/songs/key_map_song/keymap")

    assert response.status_code == 200
    assert response.json()["key_map"][0]["tonic"] == "C"


def test_override_key_persists_a_user_entry(client: TestClient, tmp_path: Path) -> None:
    song_dir = _create_song(tmp_path, "override_key_song")

    response = client.patch("/api/songs/override_key_song/key", json={"tonic": "F", "mode": "major", "start_s": 1.0})

    assert response.status_code == 200
    payload = json.loads((song_dir / "key.json").read_text(encoding="utf-8"))
    assert payload["key"] == "F major"
    assert any(entry["manually_overridden"] for entry in payload["key_map"])


def test_override_chord_writes_a_non_destructive_correction(client: TestClient, tmp_path: Path) -> None:
    song_dir = _create_song(tmp_path, "override_chord_song")

    response = client.patch("/api/songs/override_chord_song/chords/chord-1", json={"root": "Bb"})

    assert response.status_code == 200
    corrections = json.loads((song_dir / "corrections.json").read_text(encoding="utf-8"))
    assert corrections["corrections"][0]["corrected_value"] == {"root": "Bb", "quality": None}
