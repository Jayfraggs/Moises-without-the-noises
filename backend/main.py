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

from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

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


# --- Export / pitch-shift ----------------------------------------------------

@app.get("/api/songs/{song_id}/stems/{stem_name}/export")
def export_stem(
    song_id: str,
    stem_name: str,
    semitones: float = Query(default=0.0, ge=-12.0, le=12.0),
    speed: float = Query(default=1.0, ge=0.5, le=2.0),
):
    """
    Downloads a stem WAV with optional pitch shift and/or time stretch.
    Server-side via librosa phase vocoder. For playback-time changes,
    see AudioEngine.js.

    DATA WARNING: stems are 30-100MB. Don't hit this on mobile data.
    """
    stem_path = DATA_DIR / song_id / f"{stem_name}.wav"
    if not stem_path.exists():
        raise HTTPException(404, f"No stem '{stem_name}' for song '{song_id}'")

    audio_path = str(stem_path)

    if semitones != 0.0 and speed != 1.0:
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(pitch_shift_wav(audio_path, semitones))
            tmp_path = tmp.name
        try:
            wav_bytes = time_stretch_wav(tmp_path, speed)
        finally:
            os.unlink(tmp_path)
    elif semitones != 0.0:
        wav_bytes = pitch_shift_wav(audio_path, semitones)
    elif speed != 1.0:
        wav_bytes = time_stretch_wav(audio_path, speed)
    else:
        wav_bytes = stem_path.read_bytes()

    tag = f"_{'+' if semitones > 0 else ''}{semitones}st" if semitones != 0.0 else ""
    tag += f"_{speed}x" if speed != 1.0 else ""
    filename = f"{song_id}_{stem_name}{tag}.wav"

    return Response(
        content=wav_bytes,
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


# --- Frontend static mount — MUST be last ------------------------------------

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
else:
    @app.get("/")
    def frontend_not_built():
        return {"error": "frontend/dist not found. Run: cd frontend && npm install && npm run build"}
