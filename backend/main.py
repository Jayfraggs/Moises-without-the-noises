"""
main.py — FastAPI backend for Moises without the Noises (mwtn).

API surface is now at parity with StemDeck's app/api layer:

  Songs / library
    GET  /api/songs                         list all manifests
    GET  /api/songs/{id}/manifest           read manifest
    DELETE /api/songs/{id}                  delete song + stems

  Stems
    GET  /api/songs/{id}/stems/{name}       download WAV
    GET  /api/songs/{id}/stems/{name}.mp3   cached MP3 transcode
    GET  /api/songs/{id}/stems/{name}/waveform  pre-computed peaks
    GET  /api/songs/{id}/peaks              peaks.json (all stems)

  Analysis
    GET  /api/songs/{id}/beats              beat grid (with user edits)
    PATCH /api/songs/{id}/beats             persist edited grid
    DELETE /api/songs/{id}/beats            reset to detected grid
    GET  /api/songs/{id}/key                key + LUFS + dynamic range
    GET  /api/songs/{id}/lyrics             Whisper word-level lyrics
    PATCH /api/songs/{id}/lyrics            save lyric edits
    GET  /api/songs/{id}/chords             chord data
    GET  /api/songs/{id}/sections           section data
    PATCH /api/songs/{id}/sections          save/validate sections
    GET  /api/songs/{id}/notes/{stem}       note extraction data

  Export
    GET  /api/songs/{id}/mixdown.{ext}      ffmpeg mixdown (wav/mp3/flac/ogg)
    GET  /api/songs/{id}/stems/all.zip      bundle stems as zip
    POST /api/songs/{id}/stems/{name}/export  pitch-shift/time-stretch single stem

  Events (SSE)
    GET  /api/songs/{id}/events             job progress stream

  Import
    POST /api/import                        local separation import (background job)
    GET  /api/import/{job_id}/status        poll import job
    POST /api/ingest                        ingest pre-processed zip
    POST /api/ingest/upload                 upload + ingest zip

  Config
    GET  /api/config                        model list, defaults

  Setup
    GET  /api/setup/check                   system capability probe
    POST /api/setup/save                    persist wizard settings
    POST /api/setup/install                 pip-install an engine on demand
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ingest import ingest_zip
from separation import run_separation, SUPPORTED_MODELS, DEFAULT_MODEL
from audio.bpm import detect_beats
from audio.key_detection import detect_key
from audio.pitch import pitch_shift_wav, time_stretch_wav
from audio.waveform_scan import scan_stem
from audio.sections import normalize_sections, validate_sections
from audio.vocal_split import run_vocal_split
from audio.section_detection import detect_sections
from audio.collect import (
    compute_stem_peaks,
    compute_stem_presence,
    compute_stem_presence_from_wavs,
    merge_stem_peaks,
)
from audio.errors import classify_failure

BASE_DIR    = Path(__file__).parent
DATA_DIR    = BASE_DIR / "data"
CACHE_DIR   = BASE_DIR / "_cache"
IMPORT_TMP  = BASE_DIR / "_import_tmp"
CONFIG_FILE = BASE_DIR / "mwtn_config.json"
# Prefer the new vanilla JS static/ dir; fall back to legacy Vite dist/.
_STATIC_DIR = BASE_DIR.parent / "frontend" / "static"
_DIST_DIR   = BASE_DIR.parent / "frontend" / "dist"
FRONTEND    = _STATIC_DIR if _STATIC_DIR.is_dir() else _DIST_DIR

for d in (DATA_DIR, CACHE_DIR, IMPORT_TMP):
    d.mkdir(exist_ok=True)

import_jobs: dict[str, dict] = {}

# ── Manifest helpers ──────────────────────────────────────────────────────────

def _patch_manifest(song_dir: Path, updates: dict) -> None:
    """
    Atomically update manifest.json with *only the keys in `updates` that are
    currently absent or None*. Existing fields are never overwritten so that
    manually curated metadata is preserved.
    """
    manifest_path = song_dir / "manifest.json"
    if not manifest_path.exists():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    changed = False
    for k, v in updates.items():
        if manifest.get(k) is None and v is not None:
            manifest[k] = v
            changed = True
    if not changed:
        return
    tmp = manifest_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    tmp.replace(manifest_path)


# ── SSE helpers ──────────────────────────────────────────────────────────────
_MAX_SSE_SECONDS = 4 * 3600
_MAX_SSE = 200
_sse_active = 0


def _claim_sse() -> None:
    global _sse_active
    if _sse_active >= _MAX_SSE:
        raise HTTPException(503, "too many concurrent streams")
    _sse_active += 1


def _release_sse() -> None:
    global _sse_active
    _sse_active -= 1


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="mwtn API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Config ────────────────────────────────────────────────────────────────────

@app.get("/api/config")
def get_config():
    return {
        "stem_names": list(("vocals", "drums", "bass", "guitar", "piano", "other")),
        "extra_stem_names": ["lead_vocals", "backing_vocals"],
        "separation_models": {
            name: {
                "stems": info["stems"],
                "description": info["description"],
                "engine": info["engine"],
                "pip_hint": info["pip_hint"],
                "data_cost_mb": info["data_cost_mb"],
            }
            for name, info in SUPPORTED_MODELS.items()
        },
        "default_model": DEFAULT_MODEL,
    }


# ── Song library ──────────────────────────────────────────────────────────────

@app.get("/api/songs")
def list_songs():
    songs = []
    for d in sorted(DATA_DIR.iterdir()):
        mf = d / "manifest.json"
        if mf.exists():
            songs.append(json.loads(mf.read_text()))
    return songs


@app.get("/api/songs/{song_id}/manifest")
def get_manifest(song_id: str):
    p = DATA_DIR / song_id / "manifest.json"
    if not p.exists():
        raise HTTPException(404, f"No manifest for '{song_id}'")
    return json.loads(p.read_text())


@app.delete("/api/songs/{song_id}")
def delete_song(song_id: str):
    d = DATA_DIR / song_id
    if not d.exists():
        raise HTTPException(404, f"No song '{song_id}'")
    shutil.rmtree(d)
    return {"deleted": song_id}


# ── Peaks (waveform display) ──────────────────────────────────────────────────

@app.get("/api/songs/{song_id}/peaks")
def get_peaks(song_id: str):
    song_dir = DATA_DIR / song_id
    if not song_dir.exists():
        raise HTTPException(404, f"No song '{song_id}'")

    peaks_path = song_dir / "peaks.json"
    if peaks_path.exists():
        try:
            data = json.loads(peaks_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict) and data and any(
            isinstance(value, list) and value and isinstance(value[0], (list, tuple))
            for value in data.values()
        ):
            return data

    manifest_path = song_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(404, f"No manifest for '{song_id}'")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stems = manifest.get("stems", [])
    if not stems:
        raise HTTPException(404, "No stems in manifest")

    try:
        peaks: dict[str, list[list[float]]] = {}
        for name in stems:
            wav_path = song_dir / f"{name}.wav"
            if not wav_path.exists():
                continue
            try:
                result, _ = scan_stem(str(wav_path), 3000)
            except Exception:
                continue
            if result:
                peaks[name] = result
        if not peaks:
            raise HTTPException(404, f"No waveform peaks for '{song_id}'")
        peaks_path.write_text(json.dumps(peaks), encoding="utf-8")
        return peaks
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Peak computation failed: {e}")


@app.get("/api/songs/{song_id}/stems/{stem_name}/waveform")
def get_stem_waveform(song_id: str, stem_name: str, buckets: int = Query(default=1500, ge=100, le=10000)):
    song_dir = DATA_DIR / song_id
    wav_path = song_dir / f"{stem_name}.wav"
    if not wav_path.exists():
        raise HTTPException(404, f"No stem '{stem_name}' for '{song_id}'")
    cache_key = CACHE_DIR / f"{song_id}_{stem_name}_{buckets}_waveform.json"
    if cache_key.exists():
        return json.loads(cache_key.read_text())
    try:
        data = scan_stem(str(wav_path), buckets)
        cache_key.write_text(json.dumps(data))
        return data
    except Exception as e:
        raise HTTPException(500, f"Waveform scan failed: {e}")


# ── Stems ─────────────────────────────────────────────────────────────────────

@app.get("/api/songs/{song_id}/stems/{stem_name}")
def get_stem(song_id: str, stem_name: str):
    p = DATA_DIR / song_id / f"{stem_name}.wav"
    if not p.exists():
        raise HTTPException(404, f"No stem '{stem_name}' for '{song_id}'")
    return FileResponse(str(p), media_type="audio/wav")


@app.get("/api/songs/{song_id}/stems/{stem_name}.mp3")
def get_stem_mp3(song_id: str, stem_name: str):
    wav = DATA_DIR / song_id / f"{stem_name}.wav"
    if not wav.exists():
        raise HTTPException(404, f"No stem '{stem_name}' for '{song_id}'")
    cache_mp3 = CACHE_DIR / f"{song_id}_{stem_name}.mp3"
    if not cache_mp3.exists():
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav), "-codec:a", "libmp3lame", "-qscale:a", "2", str(cache_mp3)],
            capture_output=True,
        )
        if result.returncode != 0:
            raise HTTPException(500, "ffmpeg MP3 transcode failed")
    return FileResponse(str(cache_mp3), media_type="audio/mpeg")


@app.get("/api/songs/{song_id}/stems/all.zip")
def get_stems_zip(song_id: str, format: str = Query(default="wav")):
    song_dir = DATA_DIR / song_id
    if not song_dir.exists():
        raise HTTPException(404, f"No song '{song_id}'")
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for wav in song_dir.glob("*.wav"):
            zf.write(wav, wav.name)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{song_id}_stems.zip"'})


@app.post("/api/songs/{song_id}/stems/{stem_name}/export")
async def export_stem(song_id: str, stem_name: str,
                      pitch_semitones: float = Query(default=0.0),
                      speed: float = Query(default=1.0)):
    wav = DATA_DIR / song_id / f"{stem_name}.wav"
    if not wav.exists():
        raise HTTPException(404, f"No stem '{stem_name}' for '{song_id}'")
    tmp_path = CACHE_DIR / f"{song_id}_{stem_name}_export_{uuid.uuid4().hex[:8]}.wav"
    try:
        if pitch_semitones != 0.0 and speed != 1.0:
            inter = tmp_path.with_suffix(".inter.wav")
            pitch_shift_wav(str(wav), str(inter), pitch_semitones)
            time_stretch_wav(str(inter), str(tmp_path), speed)
            inter.unlink(missing_ok=True)
        elif pitch_semitones != 0.0:
            pitch_shift_wav(str(wav), str(tmp_path), pitch_semitones)
        elif speed != 1.0:
            time_stretch_wav(str(wav), str(tmp_path), speed)
        else:
            shutil.copy(wav, tmp_path)
        from starlette.background import BackgroundTask
        return FileResponse(
            str(tmp_path),
            media_type="audio/wav",
            background=BackgroundTask(lambda: tmp_path.unlink(missing_ok=True)),
        )
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(500, f"Export failed: {e}")


# ── Analysis: beats ───────────────────────────────────────────────────────────

class BeatsPatch(BaseModel):
    beats: list
    bars: list = []


@app.get("/api/songs/{song_id}/beats")
def get_beats(song_id: str):
    song_dir = DATA_DIR / song_id
    beats_path = song_dir / "beats.json"
    if beats_path.exists():
        return json.loads(beats_path.read_text())
    manifest_path = song_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(404, f"No song '{song_id}'")
    manifest = json.loads(manifest_path.read_text())
    stems = manifest.get("stems", [])
    beat_stem = next((s for s in ["drums", "other", "bass", "vocals"] if s in stems),
                     stems[0] if stems else None)
    if not beat_stem:
        raise HTTPException(404, "No stems available for beat detection")
    wav = song_dir / f"{beat_stem}.wav"
    if not wav.exists():
        raise HTTPException(404, f"Stem WAV not found: {beat_stem}")
    try:
        beats = detect_beats(str(wav))
        beats_path.write_text(json.dumps(beats))
        _patch_manifest(song_dir, {"has_beats": True, "bpm": beats.get("bpm")})
        return beats
    except Exception as e:
        raise HTTPException(500, f"Beat detection failed: {e}")


@app.patch("/api/songs/{song_id}/beats")
def patch_beats(song_id: str, body: BeatsPatch):
    song_dir = DATA_DIR / song_id
    beats_path = song_dir / "beats.json"
    if not beats_path.exists():
        raise HTTPException(404, f"No beats for '{song_id}'")
    data = json.loads(beats_path.read_text())
    data["beats"] = body.beats
    if body.bars:
        data["bars"] = body.bars
    beats_path.write_text(json.dumps(data))
    return data


@app.delete("/api/songs/{song_id}/beats")
def reset_beats(song_id: str):
    song_dir = DATA_DIR / song_id
    beats_path = song_dir / "beats.json"
    beats_path.unlink(missing_ok=True)
    return {"reset": True}


# ── Analysis: key ─────────────────────────────────────────────────────────────

@app.get("/api/songs/{song_id}/key")
def get_key(song_id: str):
    song_dir = DATA_DIR / song_id
    key_path = song_dir / "key.json"
    if key_path.exists():
        return json.loads(key_path.read_text())
    manifest_path = song_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(404, f"No song '{song_id}'")
    manifest = json.loads(manifest_path.read_text())
    stems = manifest.get("stems", [])
    key_stem = next((s for s in ["other", "vocals", "bass"] if s in stems),
                    stems[0] if stems else None)
    if not key_stem:
        raise HTTPException(404, "No stems for key detection")
    wav = song_dir / f"{key_stem}.wav"
    if not wav.exists():
        raise HTTPException(404, f"Stem WAV not found: {key_stem}")
    try:
        key = detect_key(str(wav))
        key_path.write_text(json.dumps(key))
        _patch_manifest(song_dir, {"has_key": True, "key": key.get("key"), "scale": key.get("scale")})
        return key
    except Exception as e:
        raise HTTPException(500, f"Key detection failed: {e}")


# ── Analysis: lyrics ──────────────────────────────────────────────────────────

class LyricsPatch(BaseModel):
    words: list


@app.get("/api/songs/{song_id}/lyrics")
def get_lyrics(song_id: str):
    p = DATA_DIR / song_id / "lyrics.json"
    if not p.exists():
        raise HTTPException(404, f"No lyrics for '{song_id}'")
    return json.loads(p.read_text())


@app.patch("/api/songs/{song_id}/lyrics")
def patch_lyrics(song_id: str, body: LyricsPatch):
    p = DATA_DIR / song_id / "lyrics.json"
    if not p.exists():
        raise HTTPException(404, f"No lyrics for '{song_id}'")
    data = json.loads(p.read_text())
    data["words"] = body.words
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)
    return data


# ── Analysis: chords ──────────────────────────────────────────────────────────

@app.get("/api/songs/{song_id}/chords")
def get_chords(song_id: str):
    p = DATA_DIR / song_id / "chords.json"
    if not p.exists():
        raise HTTPException(404, f"No chords for '{song_id}'")
    return json.loads(p.read_text())


# ── Analysis: sections ────────────────────────────────────────────────────────

class SectionsPatch(BaseModel):
    sections: list


@app.get("/api/songs/{song_id}/sections")
def get_sections(song_id: str):
    p = DATA_DIR / song_id / "sections.json"
    if not p.exists():
        raise HTTPException(404, f"No sections for '{song_id}'")
    return json.loads(p.read_text())


@app.patch("/api/songs/{song_id}/sections")
def patch_sections(song_id: str, body: SectionsPatch):
    song_dir = DATA_DIR / song_id
    if not song_dir.exists():
        raise HTTPException(404, f"No song '{song_id}'")
    try:
        validated = validate_sections(body.sections)
        # normalize_sections requires duration; derive it from the sections themselves
        duration = max((float(s.get("end", 0)) for s in validated if isinstance(s, dict)), default=0.0)
        normalized = normalize_sections(validated, duration)
    except Exception as e:
        raise HTTPException(422, f"Invalid sections: {e}")
    p = song_dir / "sections.json"
    p.write_text(json.dumps(normalized, ensure_ascii=False), encoding="utf-8")
    return normalized


# ── Sections: auto-detect ─────────────────────────────────────────────────────

@app.post("/api/songs/{song_id}/sections/detect")
def auto_detect_sections(song_id: str):
    """
    Run the allin1 ML model (or librosa heuristic fallback) to automatically
    detect song structure sections and persist them to sections.json.

    allin1 must be installed in the environment for the ML path:
        pip install allin1
    The librosa heuristic fallback works without any extra install.

    Returns the normalised section list on success.
    """
    song_dir = DATA_DIR / song_id
    if not song_dir.exists():
        raise HTTPException(404, f"No song '{song_id}'")

    log: list[str] = []
    try:
        sections = detect_sections(song_dir, report=log.append)
    except Exception as exc:
        raise HTTPException(500, f"Section detection failed: {exc}")

    if not sections:
        raise HTTPException(
            422,
            "Section detection produced no results. "
            "Install allin1 for best results: pip install allin1"
        )

    _patch_manifest(song_dir, {"has_sections": True})
    return {"sections": sections, "log": log}


# ── Vocal split ───────────────────────────────────────────────────────────────

@app.post("/api/songs/{song_id}/vocal-split")
def vocal_split(song_id: str):
    """
    Second-pass vocal separation: splits the existing vocals.wav into
    lead_vocals.wav and backing_vocals.wav using audio-separator's
    UVR-BVE-4B_SN-44100-1 model.

    Requires: pip install 'audio-separator[cpu]'
    (~200 MB model downloaded on first use)

    On success: updates the manifest and returns the new stem list.
    """
    song_dir = DATA_DIR / song_id
    if not song_dir.exists():
        raise HTTPException(404, f"No song '{song_id}'")
    if not (song_dir / "vocals.wav").exists():
        raise HTTPException(404, f"No vocals.wav for '{song_id}' — run separation first")

    log: list[str] = []
    try:
        stem_files = run_vocal_split(song_dir, report=log.append)
    except Exception as exc:
        raise HTTPException(500, f"Vocal split failed: {exc}")

    if not stem_files:
        raise HTTPException(
            422,
            "Vocal split produced no output. "
            "Install audio-separator: pip install 'audio-separator[cpu]'"
        )

    # Update manifest with new stems
    manifest_path = song_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        stems = manifest.get("stems", [])
        for new_stem in stem_files:
            if new_stem not in stems:
                stems.append(new_stem)
        manifest["stems"] = stems
        manifest["has_vocal_split"] = True
        tmp = manifest_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        tmp.replace(manifest_path)

    return {
        "new_stems": list(stem_files.keys()),
        "log": log,
    }


# ── Analysis: notes ───────────────────────────────────────────────────────────

@app.get("/api/songs/{song_id}/notes/{stem_name}")
def get_notes(song_id: str, stem_name: str):
    p = DATA_DIR / song_id / f"notes_{stem_name}.json"
    if not p.exists():
        raise HTTPException(404, f"No notes for stem '{stem_name}' in '{song_id}'")
    return json.loads(p.read_text())


# ── Solfa ─────────────────────────────────────────────────────────────────────

@app.get("/api/songs/{song_id}/solfa")
def get_solfa(song_id: str):
    p = DATA_DIR / song_id / "solfa.json"
    if not p.exists():
        raise HTTPException(404, f"No solfa for '{song_id}'")
    return json.loads(p.read_text())


@app.post("/api/songs/{song_id}/solfa")
def compute_solfa(song_id: str):
    song_dir = DATA_DIR / song_id
    bass_wav = song_dir / "bass.wav"
    if not bass_wav.exists():
        raise HTTPException(404, f"No bass stem for '{song_id}'")
    try:
        from note_extraction import extract_note_timeline
        timeline = extract_note_timeline(str(bass_wav), "bass")
        solfa_path = song_dir / "solfa.json"
        solfa_path.write_text(json.dumps(timeline))
        return timeline
    except Exception as e:
        raise HTTPException(500, f"Solfa extraction failed: {e}")


# ── Stem presence ─────────────────────────────────────────────────────────────

@app.get("/api/songs/{song_id}/stem_presence")
def get_stem_presence(song_id: str):
    song_dir = DATA_DIR / song_id
    manifest_path = song_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(404, f"No song '{song_id}'")
    manifest = json.loads(manifest_path.read_text())
    presence = manifest.get("stem_presence")
    if presence:
        return presence
    stems = manifest.get("stems", [])
    try:
        wavs = {s: song_dir / f"{s}.wav" for s in stems if (song_dir / f"{s}.wav").exists()}
        presence = compute_stem_presence_from_wavs(wavs)
        _patch_manifest(song_dir, {"stem_presence": presence})
        return presence
    except Exception as e:
        raise HTTPException(500, f"Stem presence failed: {e}")


# ── Mixdown export ────────────────────────────────────────────────────────────

@app.get("/api/songs/{song_id}/mixdown.{ext}")
def get_mixdown(song_id: str, ext: str,
                stems: str = Query(...),
                gains: str = Query(...),
                click: str = Query(default="0"),
                click_gain: float = Query(default=0.6)):
    song_dir = DATA_DIR / song_id
    if not song_dir.exists():
        raise HTTPException(404, f"No song '{song_id}'")
    if ext not in ("wav", "mp3", "flac", "ogg"):
        raise HTTPException(400, f"Unsupported format: {ext}")

    stem_names = [s.strip() for s in stems.split(",") if s.strip()]
    gain_vals  = [float(g) for g in gains.split(",")]
    if len(stem_names) != len(gain_vals):
        raise HTTPException(400, "stems and gains length mismatch")

    tmp_path = CACHE_DIR / f"mixdown_{song_id}_{uuid.uuid4().hex[:8]}.{ext}"
    try:
        inputs = []
        filters = []
        for i, (stem, gain) in enumerate(zip(stem_names, gain_vals)):
            wav = song_dir / f"{stem}.wav"
            if not wav.exists():
                continue
            inputs.extend(["-i", str(wav)])
            filters.append(f"[{i}:a]volume={gain:.4f}[a{i}]")

        if not inputs:
            raise HTTPException(404, "No matching stems found")

        n = len(filters)
        mix_inputs = "".join(f"[a{i}]" for i in range(n))

        if click == "1":
            beats_path = song_dir / "beats.json"
            if beats_path.exists():
                from audio.click_render import render_click_wav, ACCENT_AUTO
                beats_data = json.loads(beats_path.read_text())
                click_tmp = tmp_path.with_suffix(".click.wav")
                render_click_wav(beats_data, str(click_tmp), accent=ACCENT_AUTO)
                inputs.extend(["-i", str(click_tmp)])
                filters.append(f"[{n}:a]volume={click_gain:.4f}[a{n}]")
                mix_inputs += f"[a{n}]"
                n += 1

        mix_filter = f"{mix_inputs}amix=inputs={n}:normalize=0[out]"
        filter_complex = ";".join(filters) + (";" if filters else "") + mix_filter

        codec_args = {
            "wav":  ["-codec:a", "pcm_s16le"],
            "mp3":  ["-codec:a", "libmp3lame", "-qscale:a", "2"],
            "flac": ["-codec:a", "flac"],
            "ogg":  ["-codec:a", "libvorbis", "-qscale:a", "5"],
        }[ext]

        cmd = ["ffmpeg", "-y", *inputs,
               "-filter_complex", filter_complex,
               "-map", "[out]",
               *codec_args,
               str(tmp_path)]

        subprocess_result = subprocess.run(
            cmd, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if subprocess_result.returncode != 0:
            raise RuntimeError(subprocess_result.stderr.decode()[-1000:])

    except HTTPException:
        raise
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(500, f"Mixdown failed: {e}")

    media_types = {"wav": "audio/wav", "mp3": "audio/mpeg", "flac": "audio/flac", "ogg": "audio/ogg"}
    from starlette.background import BackgroundTask
    return FileResponse(
        str(tmp_path),
        media_type=media_types[ext],
        background=BackgroundTask(lambda: tmp_path.unlink(missing_ok=True)),
    )


# ── SSE: song job events ──────────────────────────────────────────────────────

@app.get("/api/songs/{song_id}/events")
async def song_events(song_id: str, request: Request):
    """
    Server-Sent Events stream of import job progress.
    Clients subscribe while a local import is running.
    """
    job = next(
        (j for j in import_jobs.values() if j.get("song_id") == song_id),
        None,
    )
    if job is None:
        raise HTTPException(404, f"No active import for '{song_id}'")

    _claim_sse()

    async def event_gen():
        try:
            last_msg = None
            elapsed = 0
            while elapsed < _MAX_SSE_SECONDS:
                if await request.is_disconnected():
                    break
                state = job.get("state", "queued")
                msg = job.get("status_message", "")
                if msg != last_msg:
                    last_msg = msg
                    data = json.dumps({"state": state, "message": msg})
                    yield f"data: {data}\n\n"
                if state in ("done", "error"):
                    data = json.dumps({"state": state, "message": msg,
                                       "error": job.get("error", "")})
                    yield f"data: {data}\n\n"
                    break
                await asyncio.sleep(0.5)
                elapsed += 0.5
        finally:
            _release_sse()

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Local import (background separation job) ──────────────────────────────────

def _run_import(job_id: str, input_path: Path, song_id: str, model_name: str):
    def prog(msg: str):
        import_jobs[job_id]["log"].append(msg)
        import_jobs[job_id]["status_message"] = msg

    try:
        import_jobs[job_id]["state"] = "running"
        run_separation(input_path, song_id, model_name=model_name, progress_callback=prog)

        song_dir = DATA_DIR / song_id
        manifest = json.loads((song_dir / "manifest.json").read_text())
        stems = manifest.get("stems", [])

        # Compute peaks + presence
        prog("Computing waveform peaks…")
        rms = compute_stem_peaks(song_dir, stems)
        presence = compute_stem_presence(rms)
        manifest["stem_presence"] = presence
        (song_dir / "manifest.json").write_text(json.dumps(manifest))

        # BPM
        prog("Detecting BPM…")
        beat_stem = next((s for s in ["drums", "other", "bass", "vocals"] if s in stems), stems[0] if stems else None)
        if beat_stem:
            try:
                beats = detect_beats(str(song_dir / f"{beat_stem}.wav"))
                (song_dir / "beats.json").write_text(json.dumps(beats))
                manifest["has_beats"] = True
                manifest["bpm"] = beats.get("bpm")
                manifest["tempo_stability"] = beats.get("tempo_stability")
                prog(f"BPM: {beats['bpm']}")
            except Exception as e:
                prog(f"BPM detection failed (non-fatal): {e}")

        # Key
        prog("Detecting key…")
        key_stem = next((s for s in ["other", "vocals", "bass"] if s in stems), stems[0] if stems else None)
        if key_stem:
            try:
                key = detect_key(str(song_dir / f"{key_stem}.wav"))
                (song_dir / "key.json").write_text(json.dumps(key))
                manifest["has_key"] = True
                manifest["key"] = key.get("key")
                manifest["scale"] = key.get("scale")
                manifest["lufs"] = key.get("lufs")
                manifest["peak_db"] = key.get("peak_db")
                manifest["dynamic_range"] = key.get("dynamic_range")
                prog(f"Key: {key['key']}")
            except Exception as e:
                prog(f"Key detection failed (non-fatal): {e}")

        # Lyrics via Whisper (optional — gracefully skipped if not installed)
        vocals_wav = song_dir / "vocals.wav"
        if vocals_wav.exists():
            prog("Transcribing lyrics with Whisper (optional — may be slow)…")
            try:
                import whisper as _whisper  # noqa: PLC0415
                # Load config to pick the right model size
                _cfg = {}
                if CONFIG_FILE.exists():
                    try:
                        _cfg = json.loads(CONFIG_FILE.read_text())
                    except Exception:
                        pass
                whisper_model_size = _cfg.get("whisper_model", "base")
                prog(f"Loading Whisper ({whisper_model_size})…")
                wmodel = _whisper.load_model(whisper_model_size)
                result = wmodel.transcribe(
                    str(vocals_wav),
                    word_timestamps=True,
                    verbose=False,
                )
                words = []
                for seg in result.get("segments", []):
                    for w in seg.get("words", []):
                        words.append({
                            "word":  w.get("word", "").strip(),
                            "start": round(w.get("start", 0.0), 3),
                            "end":   round(w.get("end",   0.0), 3),
                        })
                lyrics_payload = {
                    "language": result.get("language", ""),
                    "text":     result.get("text", "").strip(),
                    "words":    words,
                }
                (song_dir / "lyrics.json").write_text(json.dumps(lyrics_payload, ensure_ascii=False))
                manifest["has_lyrics"] = True
                prog(f"Lyrics transcribed: {len(words)} words")
                del wmodel  # free VRAM / RAM immediately
            except ImportError:
                prog("Whisper not installed — skipping lyrics (pip install openai-whisper to enable)")
            except Exception as e:
                prog(f"Whisper transcription failed (non-fatal): {e}")

        # Section detection (optional — requires allin1 or degrades to librosa heuristic)
        prog("Detecting song sections…")
        try:
            sections = detect_sections(song_dir, report=prog)
            if sections:
                manifest["has_sections"] = True
                prog(f"Sections: {len(sections)} detected")
        except Exception as e:
            prog(f"Section detection failed (non-fatal): {e}")

        (song_dir / "manifest.json").write_text(json.dumps(manifest))
        import_jobs[job_id]["state"] = "done"
        import_jobs[job_id]["song_id"] = song_id
    except Exception as e:
        import_jobs[job_id]["state"] = "error"
        import_jobs[job_id]["error"] = classify_failure(str(e))
    finally:
        input_path.unlink(missing_ok=True)


class ScanBody(BaseModel):
    path: str
    folder_name: str = "mwtn-outputs"


@app.post("/api/scan")
def scan_drive(body: ScanBody):
    """
    Scan a local Drive folder for Colab output ZIPs and ingest any new ones.
    """
    folder = Path(body.path) / body.folder_name
    if not folder.exists():
        raise HTTPException(404, f"Folder not found: {folder}")

    ingested = []
    skipped  = []
    errors   = []

    for zip_file in sorted(folder.glob("*.zip")):
        song_id = zip_file.stem
        if (DATA_DIR / song_id / "manifest.json").exists():
            skipped.append(song_id)
            continue  # already imported
        try:
            result = ingest_zip(zip_file, DATA_DIR)
            ingested.append(result.get("song_id", song_id))
        except Exception as e:
            errors.append({"file": zip_file.name, "error": str(e)})

    return {"ingested": ingested, "skipped": skipped, "errors": errors}


@app.post("/api/import")
async def import_song(
    file: UploadFile = File(...),
    model: str = Query(default=DEFAULT_MODEL),
):
    if model not in SUPPORTED_MODELS:
        raise HTTPException(400, f"Unknown model '{model}'")
    job_id  = str(uuid.uuid4())
    song_id = Path(file.filename).stem.replace(" ", "_")
    if (DATA_DIR / song_id).exists():
        raise HTTPException(409, f"Song '{song_id}' already exists")
    dest = IMPORT_TMP / f"{job_id}_{file.filename}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    import_jobs[job_id] = {"state": "queued", "song_id": song_id, "model": model, "log": [], "status_message": "Queued"}
    threading.Thread(target=_run_import, args=(job_id, dest, song_id, model), daemon=True).start()
    return {"job_id": job_id, "song_id": song_id}


@app.get("/api/import/{job_id}/status")
def import_status(job_id: str):
    if job_id not in import_jobs:
        raise HTTPException(404, f"No import job '{job_id}'")
    return import_jobs[job_id]


# ── Ingest (pre-processed zip) ────────────────────────────────────────────────

class IngestBody(BaseModel):
    zip_path: str


@app.post("/api/ingest")
def ingest_song(body: IngestBody):
    p = Path(body.zip_path)
    if not p.exists():
        raise HTTPException(404, f"Zip not found: {p}")
    try:
        result = ingest_zip(p, DATA_DIR)
    except Exception as e:
        raise HTTPException(500, f"Ingest failed: {e}")
    return result


@app.post("/api/ingest/upload")
async def ingest_upload(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(400, "Only .zip files accepted")
    tmp = IMPORT_TMP / f"upload_{file.filename}"
    try:
        with tmp.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        result = ingest_zip(tmp, DATA_DIR)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"Ingest failed: {e}")
    finally:
        tmp.unlink(missing_ok=True)
    return result


# ── Setup endpoints ───────────────────────────────────────────────────────────

class SetupSaveBody(BaseModel):
    path: str = "colab"                  # "colab" | "local"
    drive_path: str = ""
    folder_name: str = "mwtn-outputs"
    local_model: str = "htdemucs_6s"
    whisper_model: str = "base"


@app.get("/api/setup/check")
def setup_check():
    """
    Probe which dependencies are available so the setup wizard can show
    accurate tick/cross indicators without guessing.
    """
    result: dict[str, object] = {}

    # ffmpeg
    result["ffmpeg"] = shutil.which("ffmpeg") is not None

    # librosa / soundfile
    try:
        import librosa    # noqa: F401
        import soundfile  # noqa: F401
        result["librosa"] = True
    except ImportError:
        result["librosa"] = False

    # Installed separation engines — check each pip package
    installed_engines: dict[str, bool] = {}
    engine_checks = {
        "demucs":            ("demucs",),
        "spleeter":          ("spleeter",),
        "openunmix":         ("openunmix",),
        "mdxnet":            ("audio_separator",),
        "bs_roformer":       ("bs_roformer",),
        "melband_roformer":  ("mel_band_roformer",),
    }
    for engine, modules in engine_checks.items():
        ok = True
        for mod in modules:
            try:
                __import__(mod)
            except ImportError:
                ok = False
                break
        installed_engines[engine] = ok

    result["engines"] = installed_engines

    # Whisper
    try:
        import whisper  # noqa: F401
        result["whisper"] = True
    except ImportError:
        result["whisper"] = False

    # Drive folder (colab path)
    cfg = {}
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    drive_path = cfg.get("drive_path", "")
    folder_name = cfg.get("folder_name", "mwtn-outputs")
    if drive_path:
        folder = Path(drive_path) / folder_name
        result["drive_folder_exists"] = folder.exists()
    else:
        result["drive_folder_exists"] = False

    result["config"] = cfg
    return result


@app.post("/api/setup/save")
def setup_save(body: SetupSaveBody):
    """Persist wizard settings to mwtn_config.json."""
    cfg = {}
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    cfg.update({
        "path":          body.path,
        "drive_path":    body.drive_path,
        "folder_name":   body.folder_name,
        "local_model":   body.local_model,
        "whisper_model": body.whisper_model,
    })
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"saved": True, "config": cfg}


class InstallBody(BaseModel):
    engine: str   # e.g. "demucs", "spleeter", "whisper"


@app.post("/api/setup/install")
def setup_install(body: InstallBody):
    """
    Pip-install a separation engine or Whisper into the running venv.
    Returns immediately with a job_id; poll /api/setup/install/{job_id}/status.
    """
    # Map engine name → pip package(s)
    ENGINE_PACKAGES: dict[str, list[str]] = {
        "demucs":           ["torch", "demucs"],
        "spleeter":         ["spleeter"],
        "openunmix":        ["openunmix", "torchaudio"],
        "mdxnet":           ["audio-separator[cpu]"],
        "bs_roformer":      ["bs-roformer-infer"],
        "melband_roformer": ["melband-roformer-infer"],
        "whisper":          ["openai-whisper", "ffmpeg-python"],
    }
    if body.engine not in ENGINE_PACKAGES:
        raise HTTPException(400, f"Unknown engine '{body.engine}'. Supported: {list(ENGINE_PACKAGES)}")

    packages = ENGINE_PACKAGES[body.engine]
    job_id   = f"install_{body.engine}_{uuid.uuid4().hex[:8]}"
    install_jobs[job_id] = {"state": "running", "engine": body.engine, "log": [], "status_message": "Starting install…"}

    def _do_install():
        log = install_jobs[job_id]["log"]
        def prog(msg):
            log.append(msg)
            install_jobs[job_id]["status_message"] = msg

        prog(f"pip install {' '.join(packages)}")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", *packages],
                capture_output=True, text=True,
            )
            for line in result.stdout.splitlines():
                log.append(line)
            for line in result.stderr.splitlines():
                log.append(line)
            if result.returncode == 0:
                install_jobs[job_id]["state"] = "done"
                prog(f"✓ {body.engine} installed successfully")
            else:
                install_jobs[job_id]["state"] = "error"
                prog(f"pip failed (exit {result.returncode})")
        except Exception as e:
            install_jobs[job_id]["state"] = "error"
            prog(f"Install error: {e}")

    threading.Thread(target=_do_install, daemon=True).start()
    return {"job_id": job_id}


install_jobs: dict[str, dict] = {}


@app.get("/api/setup/install/{job_id}/status")
def install_status(job_id: str):
    if job_id not in install_jobs:
        raise HTTPException(404, f"No install job '{job_id}'")
    return install_jobs[job_id]


# ── Static frontend ───────────────────────────────────────────────────────────

if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
else:
    @app.get("/")
    def _no_frontend():
        return {"message": "Frontend not found. Expected: frontend/static/index.html"}
