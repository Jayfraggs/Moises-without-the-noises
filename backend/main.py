"""
main.py — FastAPI backend for Moises without the Noises.

Two ways songs get into backend/data/<song_id>/:

  1. Colab pipeline (recommended, fast): run colab/mwtn_notebook.ipynb,
     download the output zip, extract it into backend/data/. No local
     compute needed. The notebook uses GPU and handles Demucs (6 stems),
     Whisper transcription, BPM, and key detection in one pass.

  2. Local import (POST /api/import): runs Demucs on this machine via
     separation.py. Works fully offline once the model is downloaded, but
     on a CPU-only laptop expect 3-10x realtime -- a 4-minute song can take
     15-40 minutes. This is a background job you poll for status.

Either way, once a song directory has a manifest.json, GET /api/songs picks
it up automatically -- no separate registration step.
"""

import json
import shutil
import uuid
import threading
from pathlib import Path
from contextlib import asynccontextmanager
from pydantic import BaseModel

from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from ingest import ingest_zip
from separation import run_separation
from audio.bpm import detect_beats
from audio.key_detection import detect_key
from audio.pitch import pitch_shift_wav, time_stretch_wav

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"
IMPORT_TMP_DIR = BASE_DIR / "_import_tmp"

DATA_DIR.mkdir(exist_ok=True)
IMPORT_TMP_DIR.mkdir(exist_ok=True)

import_jobs: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    for song_dir in DATA_DIR.iterdir():
        if song_dir.is_dir() and not (song_dir / "manifest.json").exists():
            shutil.rmtree(song_dir, ignore_errors=True)
    yield


app = FastAPI(title="Moises without the Noises API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Song library ------------------------------------------------------------

@app.get("/api/songs")
def list_songs():
    songs = []
    for song_dir in sorted(DATA_DIR.iterdir()):
        manifest_path = song_dir / "manifest.json"
        if manifest_path.exists():
            songs.append(json.loads(manifest_path.read_text()))
    return songs


@app.get("/api/songs/{song_id}/manifest")
def get_manifest(song_id: str):
    manifest_path = DATA_DIR / song_id / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(404, f"No manifest for song '{song_id}'")
    return json.loads(manifest_path.read_text())


@app.delete("/api/songs/{song_id}")
def delete_song(song_id: str):
    song_dir = DATA_DIR / song_id
    if not song_dir.exists():
        raise HTTPException(404, f"No song '{song_id}'")
    shutil.rmtree(song_dir)
    return {"deleted": song_id}


# --- Stems -------------------------------------------------------------------

@app.get("/api/songs/{song_id}/stems/{stem_name}")
def get_stem(song_id: str, stem_name: str):
    stem_path = DATA_DIR / song_id / f"{stem_name}.wav"
    if not stem_path.exists():
        raise HTTPException(404, f"No stem '{stem_name}' for song '{song_id}'")
    return FileResponse(stem_path, media_type="audio/wav")


# --- Notes -------------------------------------------------------------------

@app.get("/api/songs/{song_id}/notes/{stem_name}")
def get_notes(song_id: str, stem_name: str):
    notes_path = DATA_DIR / song_id / f"notes_{stem_name}.json"
    if not notes_path.exists():
        return []
    return json.loads(notes_path.read_text())


# --- Lyrics (Whisper) --------------------------------------------------------

@app.get("/api/songs/{song_id}/lyrics")
def get_lyrics(song_id: str):
    """
    Word-level timestamped lyrics from Whisper. Only available for songs
    processed via the Colab notebook — Whisper on CPU is too slow for v1
    local import.
    """
    lyrics_path = DATA_DIR / song_id / "lyrics.json"
    if not lyrics_path.exists():
        return {"available": False, "segments": []}
    return {"available": True, **json.loads(lyrics_path.read_text())}


# Pydantic models for lyrics patching
class LyricWord(BaseModel):
    word: str
    start: float
    end: float


class LyricsPatchBody(BaseModel):
    words: list[LyricWord]


@app.patch("/api/songs/{song_id}/lyrics")
def patch_lyrics(song_id: str, body: LyricsPatchBody):
    """
    Atomically overwrite backend/data/{song_id}/lyrics.json with validated words.
    """
    song_dir = DATA_DIR / song_id
    if not song_dir.exists():
        raise HTTPException(404, f"No song '{song_id}'")

    # Validate each word: start >= 0, end > start
    for i, w in enumerate(body.words):
        if w.start < 0:
            raise HTTPException(status_code=422, detail=f"word[{i}].start must be >= 0")
        if w.end <= w.start:
            raise HTTPException(status_code=422, detail=f"word[{i}].end must be > start")

    lyrics_path = song_dir / "lyrics.json"
    tmp_path = song_dir / "lyrics.json.tmp"

    # Prepare payload
    payload = {"words": [x.dict() for x in body.words]}

    # Atomic write: write temp then replace
    import os

    tmp_path.write_text(json.dumps(payload))
    os.replace(str(tmp_path), str(lyrics_path))

    # Invalidate any manifest/cache if present (best-effort)
    try:
        if 'manifest_cache' in globals():
            del globals()['manifest_cache']
    except Exception:
        pass

    return payload


# --- BPM & beats -------------------------------------------------------------

@app.get("/api/songs/{song_id}/beats")
def get_beats(song_id: str):
    """
    Returns BPM + beat/downbeat timestamps. Computed on-demand if not cached.
    Cached as beats.json after first computation.
    """
    beats_path = DATA_DIR / song_id / "beats.json"
    if beats_path.exists():
        return json.loads(beats_path.read_text())

    song_dir = DATA_DIR / song_id
    manifest_path = song_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(404, f"No song '{song_id}'")

    manifest = json.loads(manifest_path.read_text())
    stem_priority = ["drums", "other", "bass", "vocals", "guitar", "piano"]
    stem_name = next((s for s in stem_priority if s in manifest["stems"]), manifest["stems"][0])

    result = detect_beats(str(song_dir / f"{stem_name}.wav"))
    beats_path.write_text(json.dumps(result))
    return result


# --- Key detection -----------------------------------------------------------

@app.get("/api/songs/{song_id}/key")
def get_key(song_id: str):
    """
    Returns detected musical key. Computed on-demand if not cached.
    """
    key_path = DATA_DIR / song_id / "key.json"
    if key_path.exists():
        return json.loads(key_path.read_text())

    song_dir = DATA_DIR / song_id
    manifest_path = song_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(404, f"No song '{song_id}'")

    manifest = json.loads(manifest_path.read_text())
    stem_priority = ["other", "vocals", "guitar", "piano", "bass", "drums"]
    stem_name = next((s for s in stem_priority if s in manifest["stems"]), manifest["stems"][0])

    result = detect_key(str(song_dir / f"{stem_name}.wav"))
    key_path.write_text(json.dumps(result))
    return result


@app.get("/api/songs/{song_id}/chords")
def get_chords(song_id: str) -> list[dict]:
    """
    Returns precomputed chord segments from `chords.json` produced by the Colab
    notebook. Returns 404 if chords are not available for this song.
    """
    chords_path = DATA_DIR / song_id / "chords.json"
    if not chords_path.exists():
        raise HTTPException(status_code=404, detail="Chords not available for this song")
    return json.loads(chords_path.read_text())


# --- Export / pitch-shift ----------------------------------------------------

@app.get("/api/songs/{song_id}/stems/{stem_name}/export")
def export_stem(
    song_id: str,
    stem_name: str,
    semitones: float = Query(default=0.0, ge=-12.0, le=12.0),
):
    """
    Downloads a stem WAV with optional pitch shift applied server-side.

    This endpoint returns a one-shot export (no caching) as a streaming
    WAV. If `semitones == 0.0` the original file bytes are returned.

    DATA WARNING: stems are 30-100MB. Don't hit this on mobile data.
    """
    stem_path = DATA_DIR / song_id / f"{stem_name}.wav"
    if not stem_path.exists():
        raise HTTPException(404, f"No stem '{stem_name}' for song '{song_id}'")

    # Local import to avoid top-level import cycles and keep this change
    # limited to the export route. Returns raw WAV bytes.
    from audio.pitch_shift import shift_pitch
    from fastapi.responses import StreamingResponse
    import io

    if semitones != 0.0:
        wav_bytes = shift_pitch(stem_path, semitones)
    else:
        wav_bytes = stem_path.read_bytes()

    tag = f"_{'+' if semitones > 0 else ''}{semitones}st" if semitones != 0.0 else ""
    filename = f"{song_id}_{stem_name}{tag}.wav"

    return StreamingResponse(
        io.BytesIO(wav_bytes),
        media_type="audio/wav",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Export mix of stems with optional click overlay
class ExportMixBody(BaseModel):
    stem_gains: dict[str, float] = {}
    include_click: bool = False


@app.post("/api/songs/{song_id}/export")
def export_mix(song_id: str, body: ExportMixBody):
    """Return a mixed stereo WAV per-stem gains and optional click overlay.

    Request JSON: { "stem_gains": {"vocals":1.0}, "include_click": false }
    """
    song_dir = DATA_DIR / song_id
    if not song_dir.exists():
        raise HTTPException(404, f"No song '{song_id}'")

    beats = []
    bpm = 120.0
    if body.include_click:
        beats_path = song_dir / "beats.json"
        if not beats_path.exists():
            raise HTTPException(status_code=422, detail="beats not available for this song")
        beats_payload = json.loads(beats_path.read_text())
        beats = beats_payload.get("beats", [])
        bpm = beats_payload.get("bpm", bpm)

    # Perform the mix
    from audio.mixer import mix_stems
    mix = mix_stems(song_dir, body.stem_gains or {}, body.include_click, beats, bpm)

    # Determine sample rate from first existing stem (fallback to 44100)
    import soundfile as _sf
    sr = None
    manifest_path = song_dir / "manifest.json"
    stems = []
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            stems = manifest.get("stems", [])
        except Exception:
            stems = []
    if not stems:
        stems = [p.stem for p in sorted(song_dir.glob("*.wav"))]
    for s in stems:
        p = song_dir / f"{s}.wav"
        if p.exists():
            try:
                sr = _sf.info(str(p)).samplerate
                break
            except Exception:
                continue
    if sr is None:
        sr = 44100

    # Encode to WAV in-memory
    import io
    buf = io.BytesIO()
    with _sf.SoundFile(buf, mode="w", samplerate=sr, channels=2, format="WAV", subtype="PCM_16") as f:
        if mix.size:
            f.write(mix)

    buf.seek(0)
    filename = f"{song_id}_mix.wav"

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        buf,
        media_type="audio/wav",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- Local import (slow path) ------------------------------------------------

def _run_import_job(job_id: str, input_path: Path, song_id: str):
    def progress(msg: str):
        import_jobs[job_id]["log"].append(msg)
        import_jobs[job_id]["status_message"] = msg

    try:
        import_jobs[job_id]["state"] = "running"
        run_separation(input_path, song_id, progress_callback=progress)

        song_dir = DATA_DIR / song_id
        manifest = json.loads((song_dir / "manifest.json").read_text())

        progress("Detecting BPM and key...")
        beat_stem = next((s for s in ["drums", "other", "bass", "vocals"] if s in manifest["stems"]), manifest["stems"][0])
        key_stem = next((s for s in ["other", "vocals", "bass"] if s in manifest["stems"]), manifest["stems"][0])

        try:
            beats = detect_beats(str(song_dir / f"{beat_stem}.wav"))
            (song_dir / "beats.json").write_text(json.dumps(beats))
            progress(f"BPM: {beats['bpm']}")
        except Exception as e:
            progress(f"BPM detection failed (non-fatal): {e}")

        try:
            key = detect_key(str(song_dir / f"{key_stem}.wav"))
            (song_dir / "key.json").write_text(json.dumps(key))
            progress(f"Key: {key['key']}")
        except Exception as e:
            progress(f"Key detection failed (non-fatal): {e}")

        import_jobs[job_id]["state"] = "done"
    except Exception as e:
        import_jobs[job_id]["state"] = "error"
        import_jobs[job_id]["error"] = str(e)
    finally:
        input_path.unlink(missing_ok=True)


@app.post("/api/import")
async def import_song(file: UploadFile = File(...)):
    """
    Kicks off local Demucs (htdemucs, 4 stems) as a background thread.
    For 6 stems + lyrics, use the Colab notebook.
    """
    job_id = str(uuid.uuid4())
    song_id = Path(file.filename).stem.replace(" ", "_")

    if (DATA_DIR / song_id).exists():
        raise HTTPException(409, f"Song '{song_id}' already exists")

    dest = IMPORT_TMP_DIR / f"{job_id}_{file.filename}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    import_jobs[job_id] = {"state": "queued", "song_id": song_id, "log": [], "status_message": "Queued"}

    threading.Thread(target=_run_import_job, args=(job_id, dest, song_id), daemon=True).start()

    return {"job_id": job_id, "song_id": song_id}


@app.get("/api/import/{job_id}/status")
def import_status(job_id: str):
    if job_id not in import_jobs:
        raise HTTPException(404, f"No import job '{job_id}'")
    return import_jobs[job_id]


class IngestBody(BaseModel):
    zip_path: str


@app.post("/api/ingest")
def ingest_song(body: IngestBody):
    """Ingest a fully processed ZIP whose structure matches the Colab output."""
    zip_path = Path(body.zip_path)
    if not zip_path.is_file():
        raise HTTPException(status_code=400, detail=f"ZIP path does not exist: {body.zip_path}")

    try:
        manifest = ingest_zip(str(zip_path), str(DATA_DIR))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    song_id = manifest.get("song_id") or zip_path.stem
    return {"song_id": song_id, "manifest": manifest}


# --- Frontend static mount — MUST be last ------------------------------------

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
else:
    @app.get("/")
    def frontend_not_built():
        return {"error": "frontend/dist not found. Run: cd frontend && npm install && npm run build"}
