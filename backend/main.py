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
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Query, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

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
from backend.audio.beat_tracker import load_or_analyze_beats, write_beats_json
from backend.audio.harmonic_context import KeyMap, KeyMapEntry, load_or_build_key_map, note_name_to_pitch_class
from backend.audio.chord_detection import load_or_detect_chords
from backend.audio.meter import TimeSig, SUPPORTED_TIME_SIGNATURES
from backend.audio.quantizer import quantize_events, QuantizationConfig
from backend.schema.manifest import SongManifest
from backend.jobs.notebook_generator import NotebookSettings, _render_params_cell, generate_notebook
from backend.schema.events import NoteEvent
from backend.schema.validation import validate_song_id, validate_manifest, load_json_safe
from backend.schema.units import SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS
from backend.solfa import resolve_solfa
from backend.transcription.config import TranscriptionConfig, ENGINE_REGISTRY, is_engine_available
from backend.transcription.dispatcher import transcribe_stem, get_job_status

DATA_DIR    = BASE_DIR / "data"
CACHE_DIR   = BASE_DIR / "_cache"
IMPORT_TMP  = BASE_DIR / "_import_tmp"
CONFIG_FILE = BASE_DIR / "mwtn_config.json"
_TRANSCRIPTION_CONFIG_PATH = BASE_DIR / "transcription_config.yaml"
_TRANSCRIPTION_CFG: dict = {}
if _TRANSCRIPTION_CONFIG_PATH.exists():
    with open(_TRANSCRIPTION_CONFIG_PATH, encoding="utf-8") as f:
        _TRANSCRIPTION_CFG = yaml.safe_load(f) or {}
# The frontend is framework-free and served directly; no build step is needed.
# Keep the served frontend aligned with run.ps1 and the packaged layout.
FRONTEND = BASE_DIR.parent / "frontend" / "static"

for d in (DATA_DIR, CACHE_DIR, IMPORT_TMP):
    d.mkdir(exist_ok=True)

import_jobs: dict[str, dict] = {}
notebook_jobs: dict[str, dict] = {}

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


class NotebookRequest(BaseModel):
    song_title: str
    source_url: str = ""
    settings: dict = Field(default_factory=dict)


def _notebook_settings(body: NotebookRequest, job_id: str) -> NotebookSettings:
    values = dict(body.settings)
    values.update(
        job_id=job_id,
        song_title=body.song_title,
        source_url=body.source_url,
        backend_url="",
    )
    return NotebookSettings(**values)


def _song_title_slug(title: str) -> str:
    slug = re.sub(r"\s+", "-", title.strip().lower())
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    return (slug or "untitled")[:40].strip("-") or "untitled"


def _notebook_error(job_id: str, exc: Exception) -> HTTPException:
    notebook_jobs[job_id]["state"] = "error"
    notebook_jobs[job_id]["error"] = str(exc)
    return HTTPException(500, detail={"error": "notebook_generation_failed", "message": str(exc), "job_id": job_id})


@app.post("/api/jobs/generate-notebook")
async def generate_notebook_download(body: NotebookRequest):
    job_id = str(uuid.uuid4())
    notebook_jobs[job_id] = {"state": "queued", "song_title": body.song_title}
    try:
        notebook = await asyncio.to_thread(generate_notebook, _notebook_settings(body, job_id))
    except Exception as exc:
        raise _notebook_error(job_id, exc) from exc
    filename = f"mwtn_{_song_title_slug(body.song_title)}_{job_id[:8]}.ipynb"
    return Response(
        content=notebook,
        media_type="application/x-ipynb+json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-MWTN-Job-ID": job_id},
    )


@app.post("/api/jobs/generate-params-text")
async def generate_params_text(body: NotebookRequest):
    job_id = str(uuid.uuid4())
    notebook_jobs[job_id] = {"state": "queued", "song_title": body.song_title}
    try:
        settings = _notebook_settings(body, job_id)
        params_text = "".join(await asyncio.to_thread(_render_params_cell, settings))
    except Exception as exc:
        raise _notebook_error(job_id, exc) from exc
    return {
        "job_id": job_id,
        "params_text": params_text,
        "instructions": {
            "colab": [
                "Open colab/mwtn_notebook.ipynb in Google Colab.",
                "Find the cell tagged 'parameters' (it has a yellow border in Colab).",
                "Select all text in that cell and paste the copied parameters.",
                "Fill in your BACKEND_URL (ngrok URL) in that cell.",
                "Run all cells from top to bottom (Runtime → Run all).",
            ],
            "local": [
                "Papermill will run the notebook automatically.",
                f"Trigger via: POST /api/jobs/{job_id}/run-local",
                "Or use the 'Run Locally' button in the app.",
            ],
        },
    }


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


@app.get("/api/health")
async def health_check():
    checks = {}
    checks["data_dir"] = {"status": "ok", "path": str(DATA_DIR)} if DATA_DIR.exists() else {"status": "error", "detail": "DATA_DIR missing"}
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        checks["ffmpeg"] = {"status": "ok", "version": result.stdout.split("\n")[0]}
    except Exception as e:
        checks["ffmpeg"] = {"status": "error", "detail": str(e)}
    checks["schema"] = {"status": "ok", "current_version": SCHEMA_VERSION, "supported_versions": list(SUPPORTED_SCHEMA_VERSIONS)}
    overall = "ok" if all(c.get("status") == "ok" for c in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}


@app.get("/api/transcription/engines")
async def list_engines():
    """Return all known engines with availability status."""
    result = {}
    for name, info in ENGINE_REGISTRY.items():
        result[name] = {
            **info,
            "available": is_engine_available(name),
            "enabled": _TRANSCRIPTION_CFG.get("engines", {}).get(name, {}).get("enabled", True),
        }
    return result


@app.post("/api/songs/{song_id}/transcription")
async def start_transcription(song_id: str, body: dict):
    """
    Start a transcription job for one stem of a song.
    Body: { "stem": str, "quality_profile": "fast"|"standard"|"high_quality" }
    Returns: { "run_id": str, "status": "queued" }
    """
    song_id = validate_song_id(song_id)
    stem = body.get("stem")
    quality_profile = body.get("quality_profile", "standard")

    if stem not in ("vocals", "bass", "drums", "guitar", "piano", "other"):
        raise HTTPException(400, detail=f"Unknown stem: {stem!r}")

    stem_audio_path = DATA_DIR / song_id / "stems" / f"{stem}.wav"
    if not stem_audio_path.exists():
        raise HTTPException(404, detail=f"Stem audio not found: {stem_audio_path}")

    cache_dir = DATA_DIR / song_id / "transcription_cache"
    run_id = uuid.uuid4().hex

    cfg = _TRANSCRIPTION_CFG
    config = TranscriptionConfig(
        stem_type=stem,
        quality_profile=quality_profile,
        onset_threshold=cfg.get("basic_pitch", {}).get("onset_threshold", 0.5),
        frame_threshold=cfg.get("basic_pitch", {}).get("frame_threshold", 0.3),
        minimum_note_length_ms=cfg.get("postprocessing", {}).get("minimum_note_length_ms", 50.0),
        minimum_confidence=cfg.get("postprocessing", {}).get("minimum_confidence", 0.3),
        chunk_duration_s=cfg.get("chunking", {}).get("chunk_duration_s", 60.0),
        chunk_overlap_s=cfg.get("chunking", {}).get("chunk_overlap_s", 2.0),
        device=cfg.get("device", "cpu"),
    )

    def _run():
        try:
            events, _ = transcribe_stem(
                audio_path=stem_audio_path,
                song_id=song_id,
                stem_type=stem,
                config=config,
                cache_dir=cache_dir,
                run_id=run_id,
            )
            events_path = DATA_DIR / song_id / "transcription_cache" / f"{stem}_events.json"
            events_path.parent.mkdir(parents=True, exist_ok=True)
            events_path.write_text(
                json.dumps([e.model_dump(mode="json") for e in events], indent=2),
                encoding="utf-8",
            )
        except Exception:
            # Job state is already updated inside dispatcher on failure.
            pass

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {"run_id": run_id, "status": "queued", "stem": stem, "song_id": song_id}


@app.get("/api/songs/{song_id}/transcription/{run_id}/status")
async def transcription_status(song_id: str, run_id: str):
    song_id = validate_song_id(song_id)
    state = get_job_status(run_id)
    if state.get("status") == "not_found":
        raise HTTPException(404, detail=f"No job found with run_id: {run_id}")
    return state


# ── Song library ──────────────────────────────────────────────────────────────

@app.get("/api/songs")
def list_songs():
    songs = []
    for d in sorted(DATA_DIR.iterdir()):
        mf = d / "manifest.json"
        if mf.exists():
            songs.append(SongManifest.from_file(mf).model_dump(mode="json"))
    return songs


@app.get("/api/songs/{song_id}/manifest")
def get_manifest(song_id: str):
    song_id = validate_song_id(song_id)
    p = DATA_DIR / song_id / "manifest.json"
    if not p.exists():
        raise HTTPException(404, f"No manifest for '{song_id}'")
    manifest = SongManifest.from_file(p)
    return manifest.model_dump(mode="json")


@app.get("/api/songs/{song_id}/schema")
async def get_song_schema(song_id: str):
    song_id = validate_song_id(song_id)
    manifest_path = DATA_DIR / song_id / "manifest.json"
    manifest = SongManifest.from_file(manifest_path)
    return {
        "song_id": song_id,
        "schema_version": manifest.schema_version,
        "has_transcription_runs": len(manifest.transcription_runs) > 0,
        "artifact_count": len(manifest.artifacts),
        "stems": manifest.stems,
    }


@app.delete("/api/songs/{song_id}")
def delete_song(song_id: str):
    song_id = validate_song_id(song_id)
    d = DATA_DIR / song_id
    if not d.exists():
        raise HTTPException(404, f"No song '{song_id}'")
    shutil.rmtree(d)
    return {"deleted": song_id}


# ── Peaks (waveform display) ──────────────────────────────────────────────────

@app.get("/api/songs/{song_id}/peaks")
def get_peaks(song_id: str):
    song_id = validate_song_id(song_id)
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

    manifest = SongManifest.from_file(manifest_path)
    stems = manifest.stems
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
    song_id = validate_song_id(song_id)
    song_dir = DATA_DIR / song_id
    wav_path = song_dir / f"{stem_name}.wav"
    if not wav_path.exists():
        raise HTTPException(404, f"No stem '{stem_name}' for '{song_id}'")
    cache_key = CACHE_DIR / f"{song_id}_{stem_name}_{buckets}_waveform.json"
    cached_payload = None
    if cache_key.exists():
        try:
            cached_payload = json.loads(cache_key.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached_payload = None

    if isinstance(cached_payload, dict) and "peaks" in cached_payload and "rms" in cached_payload:
        return cached_payload

    try:
        peaks, rms = scan_stem(str(wav_path), buckets)
        payload = {"peaks": peaks, "rms": rms}
        cache_key.write_text(json.dumps(payload), encoding="utf-8")
        return payload
    except Exception as e:
        raise HTTPException(500, f"Waveform scan failed: {e}")


# ── Stems ─────────────────────────────────────────────────────────────────────

@app.get("/api/songs/{song_id}/stems/{stem_name}")
def get_stem(song_id: str, stem_name: str):
    song_id = validate_song_id(song_id)
    p = DATA_DIR / song_id / f"{stem_name}.wav"
    if not p.exists():
        raise HTTPException(404, f"No stem '{stem_name}' for '{song_id}'")
    return FileResponse(str(p), media_type="audio/wav")


@app.get("/api/songs/{song_id}/stems/{stem_name}.mp3")
def get_stem_mp3(song_id: str, stem_name: str):
    song_id = validate_song_id(song_id)
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
    song_id = validate_song_id(song_id)
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
    song_id = validate_song_id(song_id)
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


@app.post("/api/songs/{song_id}/analyze/beats")
async def analyze_beats(song_id: str, body: dict = {}):
    """
    Trigger full beat/meter analysis for a song.
    Body (optional): { "force_reanalyze": bool, "device": "cpu"|"cuda" }
    Returns: BeatGrid summary.
    """
    song_id = validate_song_id(song_id)
    force = body.get("force_reanalyze", False)
    device = body.get("device", "cpu")

    # Find source audio: prefer stems_dir/mix, fall back to source/original.*
    source_dir = DATA_DIR / song_id / "source"
    source_files = list(source_dir.glob("original.*")) if source_dir.exists() else []
    if not source_files:
        raise HTTPException(404, detail=f"No source audio found for song {song_id!r}")

    audio_path = source_files[0]
    cache_path = DATA_DIR / song_id / "beats.json"

    grid = load_or_analyze_beats(audio_path, cache_path, force_reanalyze=force, device=device)

    return {
        "song_id": song_id,
        "time_signature": {"numerator": grid.time_sig.numerator, "denominator": grid.time_sig.denominator},
        "assumed_time_sig": grid.assumed_time_sig,
        "beat_count": len(grid.entries),
        "measure_count": max((e.measure_number for e in grid.entries), default=0),
        "tempo_map": grid.tempo_map,
        "source": grid.source,
        "cached": not force,
    }


@app.patch("/api/songs/{song_id}/meter")
async def override_meter(song_id: str, body: dict):
    """
    Override the detected time signature.
    Body: { "numerator": int, "denominator": int }
    Rebuilds the beat grid using the existing beat times but with the new time signature.
    """
    song_id = validate_song_id(song_id)
    numerator = body.get("numerator")
    denominator = body.get("denominator")

    if numerator not in (2, 3, 4, 6) or denominator not in (4, 8):
        raise HTTPException(400, detail=f"Unsupported time signature: {numerator}/{denominator}. Supported: 2/4, 3/4, 4/4, 6/8")

    cache_path = DATA_DIR / song_id / "beats.json"
    if not cache_path.exists():
        raise HTTPException(404, detail=f"No beat analysis found for song {song_id!r}. Run /analyze/beats first.")

    # Load existing beats.json, extract beat times, rebuild grid with new time sig
    import json as _json
    beats_data = _json.loads(cache_path.read_text())
    beat_times = beats_data.get("beats", [])
    if not beat_times:
        raise HTTPException(422, detail="Existing beat data has no beat timestamps to rebuild from.")

    from backend.audio.meter import build_beat_grid, detect_time_signature
    new_time_sig = TimeSig(numerator=numerator, denominator=denominator)
    # Recompute downbeats from beat times using new time sig
    downbeat_times = beat_times[::numerator]
    grid = build_beat_grid(beat_times, downbeat_times, new_time_sig)
    grid.assumed_time_sig = False  # user explicitly set it
    grid.source = beats_data.get("source", "librosa") + "+user_override"

    write_beats_json(grid, cache_path)

    return {
        "song_id": song_id,
        "time_signature": {"numerator": numerator, "denominator": denominator},
        "beat_count": len(grid.entries),
        "measure_count": max((e.measure_number for e in grid.entries), default=0),
        "overridden": True,
    }


@app.get("/api/songs/{song_id}/beats")
def get_beats(song_id: str):
    song_id = validate_song_id(song_id)
    song_dir = DATA_DIR / song_id
    beats_path = song_dir / "beats.json"
    if beats_path.exists():
        return json.loads(beats_path.read_text())
    manifest_path = song_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(404, f"No song '{song_id}'")
    manifest = SongManifest.from_file(manifest_path)
    stems = manifest.stems
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
    song_id = validate_song_id(song_id)
    song_dir = DATA_DIR / song_id
    beats_path = song_dir / "beats.json"
    if not beats_path.exists():
        raise HTTPException(404, f"No beats for '{song_id}'")
    data = json.loads(beats_path.read_text())
    data["beats"] = body.beats
    data["edited"] = True
    if body.bars:
        data["bars"] = body.bars
    beats_path.write_text(json.dumps(data), encoding="utf-8")
    return data


@app.delete("/api/songs/{song_id}/beats")
def reset_beats(song_id: str):
    song_id = validate_song_id(song_id)
    song_dir = DATA_DIR / song_id
    beats_path = song_dir / "beats.json"
    if beats_path.exists():
        beats_path.unlink(missing_ok=True)
    return {"reset": True, "edited": False}


# ── Analysis: key ─────────────────────────────────────────────────────────────

def _find_source_audio(song_dir: Path) -> Path:
    """Find original audio, falling back to a usable mix stem for legacy songs."""
    source_dir = song_dir / "source"
    if source_dir.exists():
        source_files = sorted(source_dir.glob("original.*"))
        if source_files:
            return source_files[0]

    for stem_name in ("other", "vocals", "bass", "drums", "guitar", "piano"):
        stem_path = song_dir / f"{stem_name}.wav"
        if stem_path.exists():
            return stem_path
    raise HTTPException(404, detail=f"No source audio found in {song_dir.name!r}. Import the song first.")

@app.get("/api/songs/{song_id}/key")
def get_key(song_id: str):
    song_id = validate_song_id(song_id)
    song_dir = DATA_DIR / song_id
    key_path = song_dir / "key.json"
    if key_path.exists():
        return json.loads(key_path.read_text())
    manifest_path = song_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(404, f"No song '{song_id}'")
    manifest = SongManifest.from_file(manifest_path)
    stems = manifest.stems
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


@app.get("/api/songs/{song_id}/keymap")
async def get_key_map(song_id: str):
    """Return the full time-varying key analysis for a song."""
    song_id = validate_song_id(song_id)
    song_dir = DATA_DIR / song_id
    key_map = load_or_build_key_map(_find_source_audio(song_dir), song_dir / "key.json")
    return key_map.to_dict()


@app.patch("/api/songs/{song_id}/key")
async def override_key(song_id: str, body: dict):
    """Persist a user-provided global or time-ranged key override."""
    song_id = validate_song_id(song_id)
    tonic = body.get("tonic")
    mode = str(body.get("mode", "major")).lower()
    if not isinstance(tonic, str) or not tonic.strip():
        raise HTTPException(400, detail="'tonic' is required")
    if mode not in {"major", "minor", "dorian", "mixolydian", "phrygian"}:
        raise HTTPException(400, detail=f"Unsupported mode: {mode!r}")
    try:
        note_name_to_pitch_class(tonic)
        start_s = float(body.get("start_s", 0.0))
        end_value = body.get("end_s")
        end_s = None if end_value is None else float(end_value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, detail=f"Invalid key override: {exc}") from exc
    if start_s < 0 or (end_s is not None and end_s <= start_s):
        raise HTTPException(422, detail="end_s must be greater than non-negative start_s")

    song_dir = DATA_DIR / song_id
    cache_path = song_dir / "key.json"
    key_map = load_or_build_key_map(_find_source_audio(song_dir), cache_path)
    key_map.entries = [entry for entry in key_map.entries if entry.start_s != start_s]
    key_map.entries.append(KeyMapEntry(
        tonic=tonic, mode=mode, confidence=1.0, start_s=start_s, end_s=end_s,
        source="user_override", manually_overridden=True,
    ))
    key_map.entries.sort(key=lambda entry: entry.start_s)

    data = key_map.to_dict()
    data.update({"schema_version": "2.0", "key": f"{tonic} {mode}", "confidence": 1.0})
    tmp = cache_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, cache_path)
    return {"song_id": song_id, "key_map": key_map.to_dict(), "overridden": True}


# ── Analysis: lyrics ──────────────────────────────────────────────────────────

class LyricsPatch(BaseModel):
    words: list


@app.get("/api/songs/{song_id}/lyrics")
def get_lyrics(song_id: str):
    song_id = validate_song_id(song_id)
    p = DATA_DIR / song_id / "lyrics.json"
    if not p.exists():
        raise HTTPException(404, f"No lyrics for '{song_id}'")
    return json.loads(p.read_text())


@app.patch("/api/songs/{song_id}/lyrics")
def patch_lyrics(song_id: str, body: LyricsPatch):
    song_id = validate_song_id(song_id)
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
    song_id = validate_song_id(song_id)
    p = DATA_DIR / song_id / "chords.json"
    if not p.exists():
        raise HTTPException(404, f"No chords for '{song_id}'")
    return json.loads(p.read_text())


@app.get("/api/songs/{song_id}/chords/detect")
async def detect_song_chords(song_id: str, force: bool = False):
    """Detect and cache beat-aligned chords without changing the legacy GET route."""
    song_id = validate_song_id(song_id)
    song_dir = DATA_DIR / song_id
    beats_path = song_dir / "beats.json"
    audio_path = _find_source_audio(song_dir)
    # Chord detection can be requested directly from the UI. Build the beat
    # grid on demand instead of forcing callers to know the analysis order.
    grid = load_or_analyze_beats(audio_path, beats_path)
    key_map = load_or_build_key_map(audio_path, song_dir / "key.json")
    chords = load_or_detect_chords(audio_path, song_dir / "chords.json", grid, key_map, force=force)
    return {
        "song_id": song_id,
        "chord_count": len(chords),
        "chords": [chord.model_dump(mode="json") for chord in chords],
    }


@app.patch("/api/songs/{song_id}/chords/{chord_id}")
async def override_chord(song_id: str, chord_id: str, body: dict):
    """Record a non-destructive chord correction for Plan 10's overlay workflow."""
    song_id = validate_song_id(song_id)
    root, quality = body.get("root"), body.get("quality")
    if not root and not quality:
        raise HTTPException(400, detail="Provide at least 'root' or 'quality' to override.")
    if root:
        try:
            note_name_to_pitch_class(str(root))
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc

    corrections_path = DATA_DIR / song_id / "corrections.json"
    try:
        corrections = json.loads(corrections_path.read_text(encoding="utf-8")) if corrections_path.exists() else {"corrections": []}
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(422, detail=f"Invalid corrections cache: {exc}") from exc
    corrections.setdefault("corrections", []).append({
        "correction_id": uuid.uuid4().hex,
        "target_event_id": chord_id,
        "correction_type": "chord",
        "corrected_value": {"root": root, "quality": quality},
        "corrected_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "correction_source": "user",
    })
    tmp = corrections_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(corrections, indent=2), encoding="utf-8")
    os.replace(tmp, corrections_path)
    return {"song_id": song_id, "chord_id": chord_id, "overridden": True}


# ── Analysis: sections ────────────────────────────────────────────────────────

class SectionsPatch(BaseModel):
    sections: list


@app.get("/api/songs/{song_id}/sections")
def get_sections(song_id: str):
    song_id = validate_song_id(song_id)
    p = DATA_DIR / song_id / "sections.json"
    if not p.exists():
        raise HTTPException(404, f"No sections for '{song_id}'")
    return json.loads(p.read_text())


@app.patch("/api/songs/{song_id}/sections")
def patch_sections(song_id: str, body: SectionsPatch):
    song_id = validate_song_id(song_id)
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
    song_id = validate_song_id(song_id)
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
    song_id = validate_song_id(song_id)
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
    song_id = validate_song_id(song_id)
    p = DATA_DIR / song_id / f"notes_{stem_name}.json"
    if not p.exists():
        raise HTTPException(404, f"No notes for stem '{stem_name}' in '{song_id}'")
    return json.loads(p.read_text())


# ── Solfa ─────────────────────────────────────────────────────────────────────

def _parse_key_root_and_scale(raw_key: object, fallback_scale: str | None = None) -> tuple[str, str]:
    if not isinstance(raw_key, str) or not raw_key.strip():
        return "C", fallback_scale or "Major"
    label = raw_key.strip()
    match = re.match(r"^([A-G](?:#|b)?)(?:\s+(?:maj|min|major|minor))?", label, flags=re.IGNORECASE)
    if match:
        root = match.group(1)
        scale = fallback_scale or "Major"
        lowered = label.lower()
        if "minor" in lowered or "min" in lowered:
            scale = "Natural Minor"
        elif "major" in lowered or "maj" in lowered:
            scale = "Major"
        return root, scale
    return "C", fallback_scale or "Major"


def _solfa_label_for_pitch_class(pitch_class: int, tonic_pc: int, scale: str) -> str:
    if scale.lower() in {"major", "maj"}:
        scale_steps = [0, 2, 4, 5, 7, 9, 11]
        labels = ["Do", "Re", "Mi", "Fa", "Sol", "La", "Ti"]
    else:
        scale_steps = [0, 2, 3, 5, 7, 8, 10]
        labels = ["La", "Ti", "Do", "Re", "Mi", "Fa", "Sol"]

    delta = (pitch_class - tonic_pc) % 12
    if delta in scale_steps:
        index = scale_steps.index(delta)
        return labels[index]

    nearest_step = min(scale_steps, key=lambda step: min((step - delta) % 12, (delta - step) % 12))
    nearest_index = scale_steps.index(nearest_step)
    base = labels[nearest_index]
    diff = (delta - nearest_step) % 12
    if diff <= 6:
        return f"{base}#"
    return f"{base}b"


def _build_solfa_payload(song_dir: Path, bass_wav: Path) -> dict:
    try:
        import librosa
    except ImportError as exc:
        raise RuntimeError(f"librosa required for solfa generation: {exc}")

    manifest_path = song_dir / "manifest.json"
    key_payload: dict = {}
    if (song_dir / "key.json").exists():
        try:
            key_payload = json.loads((song_dir / "key.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            key_payload = {}
    elif manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
        key_payload = {"key": manifest.get("key"), "scale": manifest.get("scale")}

    key_label = key_payload.get("key") or "C major"
    scale_name = key_payload.get("scale") or "Major"
    root, resolved_scale = _parse_key_root_and_scale(key_label, scale_name)

    try:
        from note_extraction import extract_note_timeline
        timeline = extract_note_timeline(str(bass_wav), "bass")
    except Exception as exc:
        raise RuntimeError(f"Note extraction failed: {exc}")

    tonic_pc = librosa.note_to_midi(root) % 12 if root else 0
    events: list[dict] = []
    for note in timeline:
        start = float(note.get("start", 0.0))
        end = float(note.get("end", start))
        pitch = str(note.get("note") or note.get("pitch") or "C4")
        midi = int(note.get("midi") or round(librosa.note_to_midi(pitch)))
        pitch_class = midi % 12
        solfa = _solfa_label_for_pitch_class(pitch_class, tonic_pc, resolved_scale)
        octave = int((midi // 12) - 1)
        events.append({
            "time": start,
            "duration": max(0.05, end - start),
            "pitch": pitch,
            "midi": midi,
            "solfa": solfa,
            "octave": octave,
        })

    return {
        "key": key_label,
        "scale": resolved_scale,
        "root": root,
        "events": events,
    }


@app.get("/api/songs/{song_id}/solfa")
def get_solfa(song_id: str):
    song_id = validate_song_id(song_id)
    p = DATA_DIR / song_id / "solfa.json"
    if not p.exists():
        raise HTTPException(404, f"No solfa for '{song_id}'")
    payload = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"key": "C major", "scale": "Major", "root": "C", "events": payload}
    if isinstance(payload, dict) and "events" in payload:
        return payload
    raise HTTPException(500, f"Solfa file for '{song_id}' is not valid")


@app.post("/api/songs/{song_id}/solfa")
def compute_solfa(song_id: str):
    song_id = validate_song_id(song_id)
    song_dir = DATA_DIR / song_id
    bass_wav = song_dir / "bass.wav"
    if not bass_wav.exists():
        raise HTTPException(404, f"No bass stem for '{song_id}'")
    try:
        payload = _build_solfa_payload(song_dir, bass_wav)
        solfa_path = song_dir / "solfa.json"
        solfa_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload
    except Exception as e:
        raise HTTPException(500, f"Solfa extraction failed: {e}")


_SOLFA_PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def _solfa_key_context(key_payload: dict) -> tuple[int, str]:
    """Normalize current and future key.json shapes for solfège resolution."""
    raw_tonic = key_payload.get("tonic_midi")
    if isinstance(raw_tonic, int):
        tonic_midi = raw_tonic
    else:
        root, _ = _parse_key_root_and_scale(key_payload.get("key"), key_payload.get("scale"))
        normalized_root = root.upper().replace("DB", "C#").replace("EB", "D#").replace("GB", "F#").replace("AB", "G#").replace("BB", "A#")
        tonic_midi = 60 + (_SOLFA_PITCH_CLASSES.index(normalized_root) if normalized_root in _SOLFA_PITCH_CLASSES else 0)

    raw_mode = str(key_payload.get("mode") or key_payload.get("scale") or key_payload.get("key") or "major").lower()
    mode = "minor" if "min" in raw_mode else "major"
    return tonic_midi, mode


def _note_events_from_solfa_json(raw_notes: object, stem_name: str) -> list[NoteEvent]:
    """Adapt legacy and canonical note JSON entries to the shared event model."""
    if not isinstance(raw_notes, list):
        raise ValueError("notes data must be a JSON array")

    events: list[NoteEvent] = []
    for item in raw_notes:
        if not isinstance(item, dict):
            raise ValueError("each note entry must be a JSON object")
        start_time = float(item.get("start_time", item.get("start", item.get("time", 0.0))))
        end_time = float(item.get("end_time", item.get("end", start_time + item.get("duration", 0.0))))
        events.append(NoteEvent(
            track_id=str(item.get("track_id", stem_name)),
            start_time=start_time,
            end_time=end_time,
            midi_pitch=int(item.get("midi_pitch", item.get("midi", 0))),
            frequency_hz=item.get("frequency_hz", item.get("pitch_hz")),
            confidence=float(item.get("confidence", 1.0)),
            source_model=str(item.get("source_model", "note_extraction")),
        ))
    return events


@app.get("/api/songs/{song_id}/stems/{stem_name}/solfa")
def get_stem_solfa(song_id: str, stem_name: str):
    """Resolve and cache movable-do solfège for a stem's precomputed notes."""
    song_id = validate_song_id(song_id)
    song_dir = DATA_DIR / song_id
    notes_path = song_dir / f"notes_{stem_name}.json"
    key_path = song_dir / "key.json"
    cache_path = song_dir / f"solfa_{stem_name}.json"

    if not notes_path.exists() or not key_path.exists():
        raise HTTPException(404, f"Solfa prerequisites are unavailable for stem '{stem_name}' in '{song_id}'")

    if cache_path.exists() and cache_path.stat().st_mtime >= max(notes_path.stat().st_mtime, key_path.stat().st_mtime):
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    try:
        raw_notes = json.loads(notes_path.read_text(encoding="utf-8"))
        key_payload = json.loads(key_path.read_text(encoding="utf-8"))
        if not isinstance(key_payload, dict):
            raise ValueError("key data must be a JSON object")
        tonic_midi, mode = _solfa_key_context(key_payload)
        solfa_result = resolve_solfa(_note_events_from_solfa_json(raw_notes, stem_name), tonic_midi, mode)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HTTPException(422, f"Could not resolve solfa metadata: {exc}") from exc

    payload = {
        "song_id": song_id,
        "stem": stem_name,
        "tonic": solfa_result.tonic_name,
        "tonic_midi": solfa_result.tonic_midi,
        "mode": solfa_result.mode,
        "events": [
            {
                "onset_s": event.start_time,
                "duration_s": event.duration_s or 0.0,
                "pitch_midi": event.midi_pitch,
                "pitch_hz": event.frequency_hz,
                "solfa": event.solfa,
                "confidence": event.confidence,
            }
            for event in solfa_result.events
        ],
    }
    temporary_path = cache_path.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary_path.replace(cache_path)
    return payload


# ── Stem presence ─────────────────────────────────────────────────────────────

@app.get("/api/songs/{song_id}/stem_presence")
def get_stem_presence(song_id: str):
    song_id = validate_song_id(song_id)
    song_dir = DATA_DIR / song_id
    manifest_path = song_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(404, f"No song '{song_id}'")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(500, f"Manifest is unreadable for '{song_id}'")

    existing = manifest.get("stem_presence")
    if isinstance(existing, dict) and existing:
        return existing

    analysis_settings = manifest.get("analysis_settings")
    if isinstance(analysis_settings, dict):
        existing = analysis_settings.get("stem_presence")
        if isinstance(existing, dict) and existing:
            return existing

    try:
        presence = compute_stem_presence_from_wavs(song_dir)
    except Exception as e:
        raise HTTPException(500, f"Stem presence failed: {e}")

    if presence:
        manifest["stem_presence"] = presence
        tmp = manifest_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        tmp.replace(manifest_path)
    return presence


# ── Mixdown export ────────────────────────────────────────────────────────────

@app.get("/api/songs/{song_id}/mixdown.{ext}")
def get_mixdown(song_id: str, ext: str,
                stems: str = Query(...),
                gains: str = Query(...),
                click: str = Query(default="0"),
                click_gain: float = Query(default=0.6)):
    song_id = validate_song_id(song_id)
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
    song_id = validate_song_id(song_id)
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
    Accepts either the root folder itself or a folder containing a nested
    `folder_name` subdirectory (the default mwtn-outputs layout used by the
    setup wizard).
    """
    root = Path(body.path)
    folder = root if root.exists() and root.is_dir() else root / body.folder_name
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(404, f"Folder not found: {folder}")

    zip_files = sorted(folder.glob("*.zip"))
    scanned = len(zip_files)
    ingested = []
    skipped  = []
    errors   = []

    for zip_file in zip_files:
        song_id = zip_file.stem
        if (DATA_DIR / song_id / "manifest.json").exists():
            skipped.append(song_id)
            continue  # already imported
        try:
            result = ingest_zip(zip_file, DATA_DIR)
            ingested.append(result.get("song_id", song_id))
        except Exception as e:
            errors.append({"file": zip_file.name, "error": str(e)})

    return {
        "scanned": scanned,
        "ingested": ingested,
        "skipped": skipped,
        "errors": errors,
    }


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
        return {"message": "Frontend not found. Expected: frontend/index.html"}
