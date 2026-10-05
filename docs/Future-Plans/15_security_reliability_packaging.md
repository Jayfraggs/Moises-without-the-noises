# Plan 15 — Reliability, Security and Distribution

## Motive

The expanded MWTN system will execute external model code, process arbitrary user-uploaded audio, create files in structured directories, and optionally launch MuseScore as an external process. These operations require controlled boundaries. This plan hardens the system before any public release or open-source publication.

---

## Input Validation

### File upload validation (`POST /api/import`)

```python
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aiff", ".opus"}
ALLOWED_MIME_TYPES = {
    "audio/mpeg", "audio/wav", "audio/x-wav", "audio/flac",
    "audio/mp4", "audio/ogg", "audio/aiff", "audio/opus"
}
MAX_UPLOAD_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB

def validate_upload(file: UploadFile) -> None:
    # 1. Check extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(400, f"File type not supported: {ext}")

    # 2. Check MIME type from magic bytes (not from Content-Type header — user-controlled)
    header_bytes = await file.read(16)
    await file.seek(0)
    detected_mime = magic.from_buffer(header_bytes, mime=True)
    if detected_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(400, f"Detected file type not supported: {detected_mime}")

    # 3. Check size
    if file.size and file.size > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(413, "File too large")
```

### Zip import validation (`POST /api/import` with zip)

```python
def validate_import_zip(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            # Path traversal protection
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"Dangerous path in zip: {member.filename}")
            # Zip bomb protection: uncompressed size limit
            if member.file_size > 2 * 1024 * 1024 * 1024:  # 2 GB per file
                raise ValueError(f"File too large in zip: {member.filename}")
```

---

## Path Sanitization

All song IDs used in filesystem paths must be sanitized:

```python
import re

SAFE_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_\-]{1,64}$')

def sanitize_song_id(song_id: str) -> str:
    if not SAFE_ID_PATTERN.match(song_id):
        raise ValueError(f"Invalid song_id: {song_id!r}")
    return song_id

def safe_song_path(base_dir: Path, song_id: str) -> Path:
    song_id = sanitize_song_id(song_id)
    path = (base_dir / song_id).resolve()
    # Ensure the resolved path is still inside base_dir
    if not path.is_relative_to(base_dir.resolve()):
        raise ValueError("Path traversal detected")
    return path
```

Apply `safe_song_path()` to every file operation in `main.py`.

---

## External Process Safety

MuseScore and any future external tools must be launched safely:

```python
import subprocess

def open_in_musescore(musescore_path: str, xml_path: str) -> None:
    # Never use shell=True — prevents shell injection
    # Always use a list, never string interpolation
    proc = subprocess.Popen(
        [musescore_path, xml_path],
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30
    )
```

For background model processes (if added in the future):
```python
# Always set resource limits on child processes
import resource
def set_limits():
    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))  # 4 GB RAM
```

---

## Temporary File Cleanup

All temporary files created during failed jobs must be cleaned up:

```python
from contextlib import contextmanager
import tempfile

@contextmanager
def managed_temp_dir():
    tmpdir = tempfile.mkdtemp(prefix="mwtn_")
    try:
        yield Path(tmpdir)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
```

Apply to: zip extraction, stem preprocessing copies, any intermediate files.

---

## Timeout Configuration

| Operation | Default timeout | Config key |
|---|---|---|
| Audio file validation | 10s | `validation_timeout_s` |
| Local separation job | 3600s (1h) | `separation_timeout_s` |
| Transcription per stem | 600s (10min) | `transcription_timeout_s` |
| MuseScore process | 30s | `musescore_timeout_s` |
| API request (non-job) | 30s | `api_timeout_s` |

---

## MusicXML Validation Before Export

Never expose a MusicXML file to the user or to MuseScore without validation:

```python
def validate_musicxml(xml_path: Path) -> tuple[bool, list[str]]:
    try:
        score = m21.converter.parse(str(xml_path))
        is_valid = score.isWellFormedNotation()
        errors = []
        # Additional checks
        for part in score.parts:
            for measure in part.getElementsByClass('Measure'):
                total = sum(n.duration.quarterLength for n in measure.notesAndRests)
                expected = measure.timeSignature.barDuration.quarterLength if measure.timeSignature else 4.0
                if abs(total - expected) > 0.01:
                    errors.append(f"Measure {measure.number}: rhythmic total {total} ≠ {expected}")
        return is_valid and len(errors) == 0, errors
    except Exception as e:
        return False, [str(e)]
```

---

## Structured Error Logging

Replace `print()` statements throughout the backend with structured logging:

```python
import logging
import json

logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "module": "%(name)s", "msg": %(message)s}'
)
logger = logging.getLogger("mwtn")

# Usage:
logger.error(json.dumps({
    "event": "transcription_failed",
    "song_id": song_id,
    "stem": stem_name,
    "engine": engine_name,
    "error": str(e)
}))
```

---

## Health Check Endpoint

```
GET /api/health
returns:
{
  "status": "ok | degraded | down",
  "checks": {
    "backend":          { "status": "ok" },
    "ffmpeg":           { "status": "ok", "version": "6.1" },
    "data_dir":         { "status": "ok", "writable": true },
    "separation":       { "status": "ok", "engine": "demucs", "model": "htdemucs_6s" },
    "transcription":    { "status": "ok", "engines": ["pyin", "basic_pitch"] },
    "musescore":        { "status": "not_installed" }
  }
}
```

All optional components (transcription models, MuseScore) report `not_installed` rather than `down` when absent — they are optional features, not failures.

---

## Dependency Documentation

### Required (core mwtn — existing)
- Python 3.11+
- FastAPI, uvicorn
- librosa, soundfile, numpy
- ffmpeg (system binary)

### Required for song-to-score expansion
- music21 (MusicXML + MIDI export)
- mido (MIDI utilities)
- pyphen (lyric syllabification)

### Optional — enable features
- basic-pitch (polyphonic transcription; recommended)
- piano-transcription-inference (high-quality piano; optional)
- madmom (beat tracking with downbeat; recommended)
- autochord (neural chord detection; recommended)
- whisperx (enhanced lyric alignment; optional)
- adtlib (drum transcription; optional)

### Runtime (user-installed)
- MuseScore 3 or 4 (notation editor; MWTN detects but does not bundle)

---

## Open-Source License Compliance

All models and libraries used must have licenses compatible with MWTN's open-source distribution. Audit:

| Dependency | License | Distribution OK? |
|---|---|---|
| Demucs | MIT | ✅ |
| Basic Pitch | MIT | ✅ |
| Piano Transcription | MIT | ✅ |
| madmom | BSD | ✅ |
| autochord | MIT | ✅ |
| music21 | BSD | ✅ |
| mido | MIT | ✅ |
| pyphen | LGPL | ✅ (dynamic link) |
| whisperx | MIT | ✅ |
| ADTLib | MIT | ✅ |
| Open-Unmix | MIT | ✅ |
| Spleeter | MIT | ✅ |
| mir_eval (test only) | MIT | ✅ |
| MuseScore | GPL | ✅ (separate process; not bundled) |
| Omnizart | Custom (research) | ⚠️ Review before including |

---

## Files to Create / Modify

```
backend/
  security/
    __init__.py
    upload_validation.py    # file type + path + size validation
    path_sanitizer.py       # song_id + path traversal guards
    process_safety.py       # safe subprocess wrapper
    temp_cleanup.py         # managed_temp_dir context manager
  health.py                 # health check endpoint

LICENSES/
  THIRD_PARTY.md            # all model + library licenses documented
```

Modify:
- `backend/main.py` — apply path sanitization everywhere; add health endpoint
- `backend/export/musicxml_exporter.py` — add validation before expose
- `electron/main.js` — safe subprocess for MuseScore launch

---

## Colab / Mobile Data Implications

No additional data costs. This plan is hardening, not feature addition.

---

## Expected Results

- Arbitrary or malicious audio filenames cannot escape the data directory
- Zip imports cannot execute path traversal attacks
- External processes (MuseScore) cannot be hijacked via crafted filenames
- Broken MusicXML is never sent to MuseScore or the user without a clear error
- Health checks make missing optional dependencies visible and non-fatal
- All bundled licenses are documented for open-source compliance

---

## Acceptance Criteria

- [ ] Path traversal filenames (`../../../etc/passwd`) are rejected at upload and zip import
- [ ] Zip bomb detection triggers before extraction
- [ ] MuseScore subprocess uses list argument form (not `shell=True`)
- [ ] Temp files from failed jobs are cleaned up automatically
- [ ] Health check correctly reports `not_installed` for MuseScore when absent
- [ ] All transcription features work when optional models are absent (graceful degradation)
- [ ] `LICENSES/THIRD_PARTY.md` lists all models and libraries with their license types
- [ ] No `shell=True` remains in any subprocess call in the backend
