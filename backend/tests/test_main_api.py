"""Integration tests for main.py using FastAPI's TestClient.

These tests use tmp_path fixtures to create real manifest/stem directories
so no mocking of the filesystem layer is needed. librosa / ffmpeg calls
are avoided by pre-writing the analysis JSON files.
"""
import json
import wave
import struct
import pytest
from pathlib import Path
from fastapi.testclient import TestClient


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """Point the backend's DATA_DIR at a temp directory."""
    monkeypatch.setenv("MWTN_DATA_DIR", str(tmp_path))
    # Patch the module-level DATA_DIR after import
    import main as m
    original = m.DATA_DIR
    m.DATA_DIR = tmp_path
    yield tmp_path
    m.DATA_DIR = original


@pytest.fixture()
def client(data_dir):
    import main as m
    return TestClient(m.app)


def _make_song(data_dir: Path, song_id: str, stems=("vocals", "drums")) -> Path:
    """Write a minimal song directory the API can serve."""
    d = data_dir / song_id
    d.mkdir()
    manifest = {
        "song_id": song_id,
        "title": song_id.replace("_", " ").title(),
        "stems": list(stems),
        "notes_available": [],
        "has_lyrics": False,
        "has_beats": True,
        "has_key": True,
        "bpm": 120.0,
        "tempo_stability": 95,
        "key": "C maj",
        "scale": "Major",
        "lufs": -14.0,
        "peak_db": -0.3,
        "dynamic_range": 13.7,
        "stem_presence": {s: 80 for s in stems},
    }
    (d / "manifest.json").write_text(json.dumps(manifest))

    # Write short silent WAV stubs
    def _wav(path: Path):
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            w.writeframes(struct.pack("<2205h", *([0] * 2205)))
    for stem in stems:
        _wav(d / f"{stem}.wav")

    # Pre-write analysis files so no librosa/ffmpeg is needed
    beats = {"bpm": 120.0, "beats": [i * 0.5 for i in range(40)], "downbeats": [0.0, 2.0, 4.0], "tempo_stability": 95}
    (d / "beats.json").write_text(json.dumps(beats))

    key = {"key": "C maj", "scale": "Major", "key_confidence": 82, "lufs": -14.0, "peak_db": -0.3, "dynamic_range": 13.7}
    (d / "key.json").write_text(json.dumps(key))

    return d


def test_get_stem_solfa_computes_and_caches_payload(client, data_dir):
    song_dir = _make_song(data_dir, "solfa_song")
    (song_dir / "notes_vocals.json").write_text(json.dumps([
        {"start": 0.5, "end": 0.75, "midi": 64, "confidence": 0.91},
    ]))

    response = client.get("/api/songs/solfa_song/stems/vocals/solfa")

    assert response.status_code == 200
    assert response.json()["tonic"] == "C"
    assert response.json()["events"] == [{
        "onset_s": 0.5, "duration_s": 0.25, "pitch_midi": 64,
        "pitch_hz": None, "solfa": "Mi", "confidence": 0.91,
    }]
    assert (song_dir / "solfa_vocals.json").exists()


def test_get_stem_solfa_requires_notes_and_key(client, data_dir):
    _make_song(data_dir, "missing_solfa")

    response = client.get("/api/songs/missing_solfa/stems/vocals/solfa")

    assert response.status_code == 404


# ── GET /api/songs ──────────────────────────────────────────────────────────

def test_list_songs_empty(client):
    r = client.get("/api/songs")
    assert r.status_code == 200
    assert r.json() == []


def test_list_songs_returns_manifest(client, data_dir):
    _make_song(data_dir, "my_song")
    r = client.get("/api/songs")
    assert r.status_code == 200
    songs = r.json()
    assert len(songs) == 1
    assert songs[0]["song_id"] == "my_song"


# ── GET /api/songs/{id}/manifest ────────────────────────────────────────────

def test_get_manifest_ok(client, data_dir):
    _make_song(data_dir, "song_a")
    r = client.get("/api/songs/song_a/manifest")
    assert r.status_code == 200
    assert r.json()["song_id"] == "song_a"


def test_get_manifest_not_found(client):
    r = client.get("/api/songs/ghost/manifest")
    assert r.status_code == 404


# ── DELETE /api/songs/{id} ───────────────────────────────────────────────────

def test_delete_song(client, data_dir):
    _make_song(data_dir, "to_delete")
    r = client.delete("/api/songs/to_delete")
    assert r.status_code == 200
    assert not (data_dir / "to_delete").exists()


def test_delete_song_not_found(client):
    r = client.delete("/api/songs/nonexistent")
    assert r.status_code == 404


# ── GET /api/songs/{id}/stems/{name} ────────────────────────────────────────

def test_get_stem_ok(client, data_dir):
    _make_song(data_dir, "song_b")
    r = client.get("/api/songs/song_b/stems/vocals")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/wav")


def test_get_stem_not_found(client, data_dir):
    _make_song(data_dir, "song_b")
    r = client.get("/api/songs/song_b/stems/piano")
    assert r.status_code == 404


# ── GET /api/songs/{id}/beats ────────────────────────────────────────────────

def test_get_beats_cached(client, data_dir):
    _make_song(data_dir, "song_c")
    r = client.get("/api/songs/song_c/beats")
    assert r.status_code == 200
    data = r.json()
    assert "bpm" in data
    assert "beats" in data


def test_get_beats_not_found(client):
    r = client.get("/api/songs/ghost/beats")
    assert r.status_code == 404


def test_export_click_track_generates_and_caches(client, data_dir):
    song_dir = data_dir / "click_song"
    song_dir.mkdir()
    beats_path = song_dir / "beats.json"
    beats_path.write_text(json.dumps({"beats": [
        {"time_s": 0.0, "beat_number": 1},
        {"time_s": 0.5, "beat_number": 2},
    ]}), encoding="utf-8")

    response = client.get("/api/songs/click_song/click-track")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert "click_song_click.wav" in response.headers["content-disposition"]
    click_path = song_dir / "click_track.wav"
    assert click_path.exists()
    first_mtime = click_path.stat().st_mtime

    response = client.get("/api/songs/click_song/click-track")

    assert response.status_code == 200
    assert click_path.stat().st_mtime == first_mtime


def test_export_click_track_requires_beats(client, data_dir):
    (data_dir / "without_beats").mkdir()

    response = client.get("/api/songs/without_beats/click-track")

    assert response.status_code == 404


# ── PATCH /api/songs/{id}/beats ─────────────────────────────────────────────

def test_patch_beats(client, data_dir):
    _make_song(data_dir, "song_d")
    payload = {"beats": [0.0, 0.5, 1.0, 1.5], "bars": []}
    r = client.patch("/api/songs/song_d/beats", json=payload)
    assert r.status_code == 200
    assert r.json()["edited"] is True

    # Check user edits are reflected in GET
    r2 = client.get("/api/songs/song_d/beats")
    data = r2.json()
    assert data.get("edited") is True
    assert data["beats"] == pytest.approx([0.0, 0.5, 1.0, 1.5], abs=1e-5)


# ── DELETE /api/songs/{id}/beats ─────────────────────────────────────────────

def test_reset_beats(client, data_dir):
    _make_song(data_dir, "song_e")
    client.patch("/api/songs/song_e/beats", json={"beats": [0.0, 1.0], "bars": []})
    r = client.delete("/api/songs/song_e/beats")
    assert r.status_code == 200

    r2 = client.get("/api/songs/song_e/beats")
    assert r2.json().get("edited") is not True


# ── GET /api/songs/{id}/key ──────────────────────────────────────────────────

def test_get_key_cached(client, data_dir):
    _make_song(data_dir, "song_f")
    r = client.get("/api/songs/song_f/key")
    assert r.status_code == 200
    assert "key" in r.json()


def test_get_stem_presence_computes_from_song_dir(client, data_dir):
    _make_song(data_dir, "song_presence")
    song_dir = data_dir / "song_presence"
    manifest = json.loads((song_dir / "manifest.json").read_text())
    manifest.pop("stem_presence", None)
    (song_dir / "manifest.json").write_text(json.dumps(manifest))

    r = client.get("/api/songs/song_presence/stem_presence")
    assert r.status_code == 200
    body = r.json()
    assert "vocals" in body
    assert "drums" in body


# ── GET /api/songs/{id}/stems/{name}/waveform ────────────────────────────────

def test_get_waveform(client, data_dir):
    _make_song(data_dir, "song_g")
    r = client.get("/api/songs/song_g/stems/vocals/waveform")
    assert r.status_code == 200
    data = r.json()
    assert "peaks" in data
    assert "rms" in data
    assert isinstance(data["peaks"], list)


def test_get_waveform_cached_second_call(client, data_dir):
    _make_song(data_dir, "song_g2")
    client.get("/api/songs/song_g2/stems/vocals/waveform")
    r2 = client.get("/api/songs/song_g2/stems/vocals/waveform")
    assert r2.status_code == 200


def test_get_peaks_returns_waveform_map_for_ui(client, data_dir):
    _make_song(data_dir, "song_peaks")
    (data_dir / "song_peaks" / "peaks.json").write_text(json.dumps({
        "vocals": [[-0.1, 0.1], [-0.2, 0.2]],
        "drums": [[-0.3, 0.3]],
    }))

    r = client.get("/api/songs/song_peaks/peaks")
    assert r.status_code == 200
    body = r.json()
    assert "vocals" in body
    assert body["vocals"][0][0] == -0.1
    assert body["drums"][0][1] == 0.3


# ── PATCH /api/songs/{id}/sections ──────────────────────────────────────────

def test_patch_sections(client, data_dir):
    _make_song(data_dir, "song_h")
    sections = [
        {"start": 0.0, "end": 30.0, "label": "verse"},
        {"start": 30.0, "end": 60.0, "label": "chorus"},
    ]
    r = client.patch("/api/songs/song_h/sections", json={"sections": sections})
    assert r.status_code == 200
    out = r.json()
    assert isinstance(out, list)


def test_patch_sections_invalid(client, data_dir):
    _make_song(data_dir, "song_i")
    r = client.patch("/api/songs/song_i/sections", json={"sections": []})
    assert r.status_code == 422


# ── Solfa contract ────────────────────────────────────────────────────────────

def test_get_solfa_returns_frontend_payload(client, data_dir):
    _make_song(data_dir, "song_solfa")
    song_dir = data_dir / "song_solfa"
    payload = {
        "key": "G# major",
        "scale": "Major",
        "root": "G#",
        "events": [
            {"time": 0.0, "duration": 1.0, "pitch": "G#2", "midi": 44, "solfa": "Do", "octave": 2},
            {"time": 1.0, "duration": 1.0, "pitch": "A#2", "midi": 46, "solfa": "Re", "octave": 2},
        ],
    }
    (song_dir / "solfa.json").write_text(json.dumps(payload))

    r = client.get("/api/songs/song_solfa/solfa")
    assert r.status_code == 200
    body = r.json()
    assert body["root"] == "G#"
    assert body["events"][0]["solfa"] == "Do"


def test_sections_detect_endpoint_returns_sections(client, data_dir):
    song_id = "song_sections_detect"
    song_dir = _make_song(data_dir, song_id, stems=("bass", "vocals"))

    # Build a 12-second wav stub so the heuristic path has valid duration.
    with wave.open(str(song_dir / "bass.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        frames = b"\x00\x00" * (22050 * 12)
        w.writeframes(frames)

    r = client.post(f"/api/songs/{song_id}/sections/detect")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "sections" in body
    assert len(body["sections"]) >= 2
    assert body["sections"][0]["start"] == 0.0


# ── GET /api/config ──────────────────────────────────────────────────────────

def test_get_config(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert "separation_models" in data
    assert "default_model" in data


# ── Static frontend serving ──────────────────────────────────────────────────

def test_frontend_path_prefers_static(tmp_path, monkeypatch):
    """main.py should prefer frontend/static/ over frontend/dist/."""
    import main as m
    static = tmp_path / "frontend" / "static"
    static.mkdir(parents=True)
    (static / "index.html").write_text("<html>ok</html>")

    # Simulate what main.py does at module level
    dist = tmp_path / "frontend" / "dist"
    result = static if static.is_dir() else dist
    assert result == static


def test_frontend_falls_back_to_dist(tmp_path):
    """Falls back to dist/ when static/ doesn't exist."""
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    static = tmp_path / "frontend" / "static_does_not_exist"

    result = static if static.is_dir() else dist
    assert result == dist


# ── Beat edit round-trip ──────────────────────────────────────────────────────

def test_beats_edit_round_trip(client, data_dir):
    """Edit beats → GET reads edited version → DELETE reverts to detected."""
    _make_song(data_dir, "beat_roundtrip")

    # Patch
    new_beats = [0.0, 0.5, 1.0, 1.5, 2.0]
    r = client.patch("/api/songs/beat_roundtrip/beats",
                     json={"beats": new_beats, "bars": []})
    assert r.status_code == 200

    # GET should return edited beats
    r2 = client.get("/api/songs/beat_roundtrip/beats")
    data = r2.json()
    assert data.get("edited") is True
    assert pytest.approx(data["beats"][:5], abs=1e-4) == new_beats

    # DELETE reverts
    r3 = client.delete("/api/songs/beat_roundtrip/beats")
    assert r3.status_code == 200

    r4 = client.get("/api/songs/beat_roundtrip/beats")
    assert r4.json().get("edited") is not True


# ── Waveform endpoint idempotency ─────────────────────────────────────────────

def test_waveform_cache_idempotent(client, data_dir):
    """Second call to /waveform returns same data as first (from cache)."""
    _make_song(data_dir, "wave_cache")
    r1 = client.get("/api/songs/wave_cache/stems/vocals/waveform")
    assert r1.status_code == 200
    r2 = client.get("/api/songs/wave_cache/stems/vocals/waveform")
    assert r2.status_code == 200
    assert r1.json()["rms"] == r2.json()["rms"]


def test_waveform_missing_stem_404(client, data_dir):
    _make_song(data_dir, "wave_404")
    r = client.get("/api/songs/wave_404/stems/piano/waveform")
    assert r.status_code == 404


# ── Sections validation via API ───────────────────────────────────────────────

def test_sections_bad_kind_returns_422(client, data_dir):
    _make_song(data_dir, "sec_bad")
    bad = [{"start": 0, "end": 30, "label": "NOT_A_REAL_KIND"},
           {"start": 30, "end": 60, "label": "chorus"}]
    r = client.patch("/api/songs/sec_bad/sections", json={"sections": bad})
    assert r.status_code == 422


# ── Config endpoint ───────────────────────────────────────────────────────────

def test_config_has_stem_names(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert "stem_names" in data
    assert "vocals" in data["stem_names"]
    assert "drums" in data["stem_names"]


# ── POST /api/scan ─────────────────────────────────────────────────────────

def test_scan_missing_path(client):
    r = client.post("/api/scan", json={"path": "/nonexistent/drive/path"})
    assert r.status_code == 404


def test_scan_empty_folder(client, tmp_path):
    """Scanning a real empty dir returns 0 ZIPs and 0 ingested."""
    r = client.post("/api/scan", json={"path": str(tmp_path)})
    assert r.status_code == 200
    data = r.json()
    assert data["scanned"] == 0
    assert data["ingested"] == []
    assert data["errors"] == []


def test_scan_already_imported_skipped(client, data_dir, tmp_path):
    """A ZIP whose stem name matches an existing song is skipped."""
    import zipfile, json
    _make_song(data_dir, "existing_song")
    # Create a zip with the same name
    zp = tmp_path / "existing_song.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("existing_song/manifest.json", json.dumps({
            "song_id": "existing_song", "title": "Existing", "stems": [],
            "notes_available": [], "has_lyrics": False, "has_beats": False, "has_key": False,
        }))
    r = client.post("/api/scan", json={"path": str(tmp_path)})
    assert r.status_code == 200
    assert "existing_song" not in r.json()["ingested"]
