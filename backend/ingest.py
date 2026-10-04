"""
ingest.py — ZIP ingestion for mwtn.

Two ZIP shapes are supported:

1. Colab-pipeline ZIP (preferred)
   Structure: <song_id>/manifest.json + <song_id>/<stem>.wav + optional *.json
   Already has a manifest — extracted as-is.

2. Raw-stems ZIP (new)
   Structure: loose WAV files at the top level OR inside one sub-folder,
   with NO manifest.json. We generate a manifest by matching filenames
   against STEM_NAME_ALIASES (see below).

   Naming conventions understood (case-insensitive):
     vocals.wav, vocal.wav, vox.wav, lead_vocals.wav, voice.wav
     drums.wav, drum.wav, beat.wav, percussion.wav, perc.wav
     bass.wav, bass_guitar.wav
     guitar.wav, gtr.wav, guitars.wav, electric_guitar.wav, acoustic_guitar.wav
     piano.wav, keys.wav, keyboard.wav, synth.wav
     other.wav, accompaniment.wav, instrumental.wav, backing.wav, music.wav

   Any WAV file whose name matches none of the aliases is kept as-is under
   its stem name (spaces → underscores, lowercased).

   This handles ZIPs from UVR5, audio-separator, Spleeter, and manual
   Audacity exports equally well.
"""

import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath

# ── Stem name normalisation aliases ──────────────────────────────────────────
STEM_NAME_ALIASES: dict[str, str] = {
    # vocals
    "vocal": "vocals", "vox": "vocals", "lead_vocals": "vocals",
    "lead_vocal": "vocals", "voice": "vocals", "singer": "vocals",
    # drums
    "drum": "drums", "beat": "drums", "percussion": "drums", "perc": "drums",
    "kick": "drums",
    # bass
    "bass_guitar": "bass", "bass_line": "bass",
    # guitar
    "gtr": "guitar", "guitars": "guitar", "electric_guitar": "guitar",
    "acoustic_guitar": "guitar", "rhythm_guitar": "guitar",
    # piano / keys
    "piano": "piano", "keys": "piano", "keyboard": "piano",
    "keyboards": "piano", "synth": "piano",
    # other / backing
    "accompaniment": "instrumental", "backing": "instrumental",
    "backing_track": "instrumental", "music": "instrumental",
    "inst": "instrumental", "no_vocals": "instrumental",
}

# Stems we expose note detection for (kept in sync with note_extraction.py)
NOTE_ELIGIBLE_STEMS = {"vocals", "bass", "guitar", "piano", "other"}


def _normalise_stem_name(raw: str) -> str:
    """
    Given a bare filename stem (no extension), return the canonical stem name.
    e.g. "Lead_Vocals" -> "vocals", "Gtr" -> "guitar", "my_weird_part" -> "my_weird_part"
    """
    key = raw.lower().strip().replace(" ", "_").replace("-", "_")
    return STEM_NAME_ALIASES.get(key, key)


def _normalise_zip_path(raw_name: str) -> str:
    """
    Normalise a ZIP entry name to forward-slash separators.
    Windows ZIPs often use backslashes; zipfile doesn't normalise for us.
    Uses str.replace with an explicit single-backslash character to avoid
    any escape-sequence ambiguity.
    """
    backslash = chr(92)   # the \ character, unambiguously
    return raw_name.replace(backslash, "/").strip("/")


def _is_safe_path(name: str) -> bool:
    """Return True only if a normalised path has no traversal components."""
    parts = PurePosixPath(name).parts
    return bool(parts) and all(p not in ("", ".", "..") for p in parts)


def ingest_zip(zip_path, data_dir) -> dict:
    """
    Extract a song ZIP into data_dir/<song_id>/ and return the manifest dict.

    Accepts both Colab-pipeline ZIPs (have manifest.json) and raw-stem ZIPs
    (loose WAVs — manifest is auto-generated).
    """
    zip_file = Path(zip_path)
    if not zip_file.is_file():
        raise ValueError(f"ZIP file does not exist: {zip_path}")

    data_root = Path(data_dir)
    data_root.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_file, "r") as archive:
            names = [
                _normalise_zip_path(n)
                for n in archive.namelist()
                if _normalise_zip_path(n)
            ]

            if not names:
                raise ValueError("ZIP archive is empty")

            # Safety check — reject any path-traversal attempts
            for n in names:
                if not _is_safe_path(n):
                    raise ValueError(f"ZIP contains an unsafe path: {n!r}")

            # ── Determine ZIP shape ───────────────────────────────────────
            top_levels = {PurePosixPath(n).parts[0] for n in names if PurePosixPath(n).parts}
            has_manifest = any(
                n == "manifest.json" or n.endswith("/manifest.json")
                for n in names
            )

            if has_manifest and len(top_levels) == 1:
                return _ingest_colab_zip(archive, names, top_levels, data_root)
            else:
                song_id = zip_file.stem.replace(" ", "_")
                return _ingest_raw_zip(archive, names, song_id, data_root)

    except zipfile.BadZipFile as exc:
        raise ValueError(f"Not a valid ZIP file: {zip_path}") from exc


def _ingest_colab_zip(archive, names, top_levels, data_root: Path) -> dict:
    """Extract a Colab-pipeline ZIP that already has a manifest.json."""
    if len(top_levels) != 1:
        raise ValueError("Colab ZIP must contain exactly one top-level directory")

    song_id = next(iter(top_levels))
    song_dir = data_root / song_id

    manifest_path = song_dir / "manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    for info in archive.infolist():
        member = _normalise_zip_path(info.filename)
        if not member or not _is_safe_path(member):
            continue
        parts = PurePosixPath(member).parts
        target = data_root.joinpath(*parts)
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)

    if not manifest_path.exists():
        raise ValueError(f"ZIP does not contain manifest.json inside '{song_id}/'")

    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest.json in '{song_id}' is not valid JSON") from exc


def _ingest_raw_zip(archive, names: list, song_id: str, data_root: Path) -> dict:
    """
    Extract a raw-stems ZIP (no manifest), normalise stem filenames,
    and auto-generate a manifest.json.
    """
    song_dir = data_root / song_id
    manifest_path = song_dir / "manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    song_dir.mkdir(parents=True, exist_ok=True)

    wav_names = [n for n in names if n.lower().endswith(".wav")]
    if not wav_names:
        raise ValueError("Raw-stems ZIP contains no WAV files")

    # Strip the common top-level folder if all WAVs share one
    top_levels = {PurePosixPath(n).parts[0] for n in wav_names}
    strip_prefix = None
    if len(top_levels) == 1:
        prefix = next(iter(top_levels))
        if not prefix.lower().endswith(".wav"):
            strip_prefix = prefix

    stem_files: dict = {}

    for info in archive.infolist():
        member = _normalise_zip_path(info.filename)
        if not member.lower().endswith(".wav"):
            continue
        if not _is_safe_path(member):
            continue

        parts = PurePosixPath(member).parts
        if strip_prefix and parts[0] == strip_prefix:
            parts = parts[1:]
        if not parts:
            continue

        raw_stem = Path(parts[-1]).stem
        canonical = _normalise_stem_name(raw_stem)
        dest_path = song_dir / f"{canonical}.wav"

        with archive.open(info) as src, dest_path.open("wb") as dst:
            shutil.copyfileobj(src, dst)

        stem_files[canonical] = f"{canonical}.wav"

    if not stem_files:
        shutil.rmtree(song_dir, ignore_errors=True)
        raise ValueError("No WAV files could be extracted from the ZIP")

    manifest = {
        "song_id": song_id,
        "title": song_id.replace("_", " "),
        "stems": sorted(stem_files.keys()),
        "notes_available": [],
        "separation_model": "external",
        "separation_engine": "external",
        "demucs_model": "external",
        "stem_presence": {},
        "has_lyrics": False,
        "has_beats": False,
        "has_key": False,
    }

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest
