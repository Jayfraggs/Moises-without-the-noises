"""
tests/test_ingest.py

Tests for ingest.py — both Colab-pipeline ZIPs and raw-stems ZIPs.

Run with: pytest backend/tests/test_ingest.py -v
"""
import io
import json
import zipfile
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from ingest import ingest_zip, _normalise_stem_name, _normalise_zip_path, STEM_NAME_ALIASES


# ── _normalise_stem_name ─────────────────────────────────────────────────────

class TestNormaliseStemName:
    def test_exact_canonical_pass_through(self):
        assert _normalise_stem_name("vocals") == "vocals"
        assert _normalise_stem_name("drums") == "drums"
        assert _normalise_stem_name("bass") == "bass"
        assert _normalise_stem_name("guitar") == "guitar"
        assert _normalise_stem_name("piano") == "piano"

    def test_alias_mapping(self):
        assert _normalise_stem_name("vox") == "vocals"
        assert _normalise_stem_name("Vox") == "vocals"
        assert _normalise_stem_name("VOX") == "vocals"
        assert _normalise_stem_name("gtr") == "guitar"
        assert _normalise_stem_name("beat") == "drums"
        assert _normalise_stem_name("keys") == "piano"
        assert _normalise_stem_name("accompaniment") == "instrumental"
        assert _normalise_stem_name("backing") == "instrumental"
        assert _normalise_stem_name("bass_guitar") == "bass"

    def test_unknown_name_passes_through_lowercased(self):
        assert _normalise_stem_name("my_weird_part") == "my_weird_part"
        assert _normalise_stem_name("SynthLead") == "synthlead"

    def test_spaces_and_hyphens_normalised(self):
        assert _normalise_stem_name("lead vocals") == "vocals"
        assert _normalise_stem_name("lead-vocals") == "vocals"



class TestNormaliseZipPath:
    def test_forward_slash_unchanged(self):
        assert _normalise_zip_path("folder/file.wav") == "folder/file.wav"

    def test_backslash_converted(self):
        assert _normalise_zip_path("folder\\file.wav") == "folder/file.wav"

    def test_leading_slash_stripped(self):
        assert _normalise_zip_path("/folder/file.wav") == "folder/file.wav"

    def test_trailing_slash_stripped(self):
        assert _normalise_zip_path("folder/file.wav/") == "folder/file.wav"

    def test_mixed_separators(self):
        result = _normalise_zip_path("top\\sub/file.wav")
        assert "/" in result
        assert "\\" not in result



# ── Helper — build in-memory ZIPs ────────────────────────────────────────────

def _make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


DUMMY_WAV = b"RIFF\x00\x00\x00\x00WAVEfmt "  # minimal header, not real audio


# ── Colab-pipeline ZIP ───────────────────────────────────────────────────────

class TestIngestColabZip:
    def test_basic_colab_zip(self, tmp_path):
        manifest = {
            "song_id": "my_song",
            "stems": ["vocals", "drums"],
            "title": "My Song",
        }
        zip_bytes = _make_zip({
            "my_song/manifest.json": json.dumps(manifest).encode(),
            "my_song/vocals.wav": DUMMY_WAV,
            "my_song/drums.wav": DUMMY_WAV,
        })
        zip_path = tmp_path / "my_song.zip"
        zip_path.write_bytes(zip_bytes)

        result = ingest_zip(zip_path, tmp_path / "data")

        assert result["song_id"] == "my_song"
        assert "vocals" in result["stems"]
        assert (tmp_path / "data" / "my_song" / "manifest.json").exists()
        assert (tmp_path / "data" / "my_song" / "vocals.wav").exists()

    def test_colab_zip_idempotent(self, tmp_path):
        """Re-ingesting an already-present song returns existing manifest."""
        manifest = {"song_id": "song2", "stems": ["bass"]}
        song_dir = tmp_path / "data" / "song2"
        song_dir.mkdir(parents=True)
        (song_dir / "manifest.json").write_text(json.dumps(manifest))

        zip_bytes = _make_zip({
            "song2/manifest.json": json.dumps(manifest).encode(),
            "song2/bass.wav": DUMMY_WAV,
        })
        zip_path = tmp_path / "song2.zip"
        zip_path.write_bytes(zip_bytes)

        result = ingest_zip(zip_path, tmp_path / "data")
        assert result["song_id"] == "song2"

    def test_missing_manifest_raises(self, tmp_path):
        zip_bytes = _make_zip({"my_song/vocals.wav": DUMMY_WAV})
        zip_path = tmp_path / "no_manifest.zip"
        zip_path.write_bytes(zip_bytes)

        # No manifest → treated as raw-stems ZIP, not an error
        result = ingest_zip(zip_path, tmp_path / "data")
        # Raw path auto-generates manifest
        assert "stems" in result

    def test_invalid_zip_raises(self, tmp_path):
        zip_path = tmp_path / "bad.zip"
        zip_path.write_bytes(b"not a zip file")
        with pytest.raises(ValueError, match="Not a valid ZIP"):
            ingest_zip(zip_path, tmp_path / "data")

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(ValueError, match="does not exist"):
            ingest_zip(tmp_path / "ghost.zip", tmp_path / "data")


# ── Raw-stems ZIP ─────────────────────────────────────────────────────────────

class TestIngestRawZip:
    def test_flat_wavs_auto_manifest(self, tmp_path):
        """Loose WAV files at root → canonical manifest generated."""
        zip_bytes = _make_zip({
            "vocals.wav": DUMMY_WAV,
            "drums.wav": DUMMY_WAV,
            "bass.wav": DUMMY_WAV,
        })
        zip_path = tmp_path / "flat_raw.zip"
        zip_path.write_bytes(zip_bytes)

        result = ingest_zip(zip_path, tmp_path / "data")

        assert set(result["stems"]) == {"vocals", "drums", "bass"}
        assert result["separation_engine"] == "external"
        assert (tmp_path / "data" / "flat_raw" / "manifest.json").exists()

    def test_alias_stems_normalised(self, tmp_path):
        """vox.wav → vocals.wav, gtr.wav → guitar.wav, etc."""
        zip_bytes = _make_zip({
            "vox.wav": DUMMY_WAV,
            "gtr.wav": DUMMY_WAV,
            "beat.wav": DUMMY_WAV,
        })
        zip_path = tmp_path / "alias_song.zip"
        zip_path.write_bytes(zip_bytes)

        result = ingest_zip(zip_path, tmp_path / "data")
        stems = result["stems"]

        assert "vocals" in stems
        assert "guitar" in stems
        assert "drums" in stems

        song_dir = tmp_path / "data" / "alias_song"
        assert (song_dir / "vocals.wav").exists()
        assert (song_dir / "guitar.wav").exists()
        assert (song_dir / "drums.wav").exists()

    def test_subfolder_stripped(self, tmp_path):
        """Single shared sub-folder prefix is stripped."""
        zip_bytes = _make_zip({
            "my_track/vocals.wav": DUMMY_WAV,
            "my_track/drums.wav": DUMMY_WAV,
        })
        zip_path = tmp_path / "subfolder.zip"
        zip_path.write_bytes(zip_bytes)

        result = ingest_zip(zip_path, tmp_path / "data")
        assert "vocals" in result["stems"]
        assert "drums" in result["stems"]

    def test_unknown_stem_kept_as_is(self, tmp_path):
        zip_bytes = _make_zip({"weird_instrument.wav": DUMMY_WAV})
        zip_path = tmp_path / "unknown.zip"
        zip_path.write_bytes(zip_bytes)

        result = ingest_zip(zip_path, tmp_path / "data")
        assert "weird_instrument" in result["stems"]

    def test_empty_zip_raises(self, tmp_path):
        zip_bytes = _make_zip({})
        zip_path = tmp_path / "empty.zip"
        zip_path.write_bytes(zip_bytes)
        with pytest.raises(ValueError, match="empty"):
            ingest_zip(zip_path, tmp_path / "data")

    def test_zip_with_no_wavs_raises(self, tmp_path):
        zip_bytes = _make_zip({"notes.txt": b"hello"})
        zip_path = tmp_path / "nowavs.zip"
        zip_path.write_bytes(zip_bytes)
        with pytest.raises(ValueError, match="no WAV files"):
            ingest_zip(zip_path, tmp_path / "data")

    def test_spleeter_naming_convention(self, tmp_path):
        """Spleeter outputs accompaniment.wav — should map to instrumental."""
        zip_bytes = _make_zip({
            "vocals.wav": DUMMY_WAV,
            "accompaniment.wav": DUMMY_WAV,
        })
        zip_path = tmp_path / "spleeter_2stem.zip"
        zip_path.write_bytes(zip_bytes)

        result = ingest_zip(zip_path, tmp_path / "data")
        assert "vocals" in result["stems"]
        assert "instrumental" in result["stems"]

    def test_uvr5_naming_convention(self, tmp_path):
        """UVR5 outputs like (Vocals).wav and (Instrumental).wav."""
        zip_bytes = _make_zip({
            "song_(Vocals).wav": DUMMY_WAV,
            "song_(Instrumental).wav": DUMMY_WAV,
        })
        zip_path = tmp_path / "uvr5.zip"
        zip_path.write_bytes(zip_bytes)

        result = ingest_zip(zip_path, tmp_path / "data")
        # Stem names should include vocal/instrumental after normalisation
        assert any("vocal" in s for s in result["stems"])
