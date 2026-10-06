# PLAN 01 — Agent Prompt Suite
Musical Intelligence Architecture and Data Contracts

Six prompts. Each is a complete, self-contained task for a coding agent. Run them in the order listed — later ones import from earlier ones.

## [P01-A] Create backend/schema/units.py — Canonical Unit Constants

### Target File: backend/schema/units.py

Context: MWTN is adding a canonical musical data layer on top of its existing FastAPI/librosa backend. All modules that produce or consume musical data must share a single authoritative unit reference to prevent ambiguity (e.g. is this time value in milliseconds or seconds? is this pitch a MIDI integer or a frequency?).

Objective:
Create backend/schema/units.py as a constants-only module. No classes, no functions — just named constants that every other backend module will import.

### Technical Specifications:

AUDIO_TIME_UNIT = "seconds" — all time values are floats in seconds from audio start
MIDI_PITCH_MIN = 0, MIDI_PITCH_MAX = 127 — MIDI pitch is always an int in this range
FREQUENCY_UNIT = "hz" — raw frequency is always a float in Hz
TEMPO_UNIT = "bpm" — tempo is always a float in beats-per-minute
CONFIDENCE_MIN = 0.0, CONFIDENCE_MAX = 1.0 — confidence is always a float in [0.0, 1.0]
MIDI_PPQ = 480 — ticks per quarter note for all MIDI export operations
SCHEMA_VERSION = "1.0" — current schema version string, used as default in all Pydantic models
SUPPORTED_SCHEMA_VERSIONS: tuple[str, ...] = ("1.0",) — versions the backend can read
STEM_ROLES: tuple[str, ...] = ("vocals", "bass", "drums", "guitar", "piano", "other") — canonical stem names
EVENT_TYPES: tuple[str, ...] = ("note", "rest", "chord", "drum_hit", "lyric", "beat", "downbeat", "section") — valid event type strings
Also create backend/schema/__init__.py as an empty file

### Execution Constraints:

Pure constants only. No imports beyond stdlib typing if needed.
No functions, no classes.
Every constant must have an inline comment explaining what it governs.
Do not create any other files in this task.

### Output Request:
Return ONLY the two files: backend/schema/__init__.py and backend/schema/units.py.

# [P01-B] Create backend/schema/events.py — MusicalEvent Pydantic Models

## Target File: backend/schema/events.py

Context: MWTN's backend is Python + FastAPI with Pydantic v2. The project is adding a canonical MusicalEvent representation that all analysis pipelines (transcription, beat tracking, chord detection, solfa) will produce and consume. This file defines every event type as a Pydantic v2 model. It replaces the ad-hoc dicts currently written by note_extraction.py, bpm.py, and key_detection.py.

### Objective:
Create backend/schema/events.py containing Pydantic v2 models for all musical event subtypes. All models inherit from a shared MusicalEventBase.

### Technical Specifications:

``` python
Base class MusicalEventBase(BaseModel):

event_id: str — default factory: lambda: str(uuid.uuid4())
track_id: str — stem name this event belongs to (e.g. "vocals", "piano")
event_type: str — must be one of EVENT_TYPES from units.py; validated with @field_validator
start_time: float — seconds; must be >= 0.0
end_time: float | None = None — seconds; if present, must be > start_time
confidence: float — clamped to [0.0, 1.0] by validator
source_model: str — e.g. "pyin_librosa_0.10.1"; required, no default
schema_version: str — default from units.SCHEMA_VERSION
model_config = ConfigDict(extra="allow") — allow extra fields for forward compatibility

Subclasses (each sets its event_type as a Literal):

NoteEvent(MusicalEventBase):

event_type: Literal["note"] = "note"
midi_pitch: int — validated: must be in [MIDI_PITCH_MIN, MIDI_PITCH_MAX]
frequency_hz: float | None = None
velocity: int | None = None — if present, validated: [0, 127]
duration_s: float | None = None — computed as end_time - start_time if both present; stored explicitly for convenience
is_rest: bool = False
quantized_position: dict | None = None — populated later by Plan 04 quantizer; leave as open dict for now
pitch_confidence: float | None = None — separate from overall confidence where model supports it

RestEvent(MusicalEventBase):

event_type: Literal["rest"] = "rest"
duration_s: float — required; > 0
quantized_position: dict | None = None

ChordEvent(MusicalEventBase):

event_type: Literal["chord"] = "chord"
root: str — e.g. "G", "Bb"
quality: str — e.g. "major", "minor", "dominant7"
extensions: list[str] = []
inversion: int = 0 — 0 = root position
bass_note: str | None = None
beat_aligned_start: dict | None = None

DrumHitEvent(MusicalEventBase):

event_type: Literal["drum_hit"] = "drum_hit"
drum_type: str — e.g. "kick", "snare", "hihat_closed", "hihat_open", "crash", "ride", "tom_high", "tom_mid", "tom_low"
velocity: int | None = None

LyricEvent(MusicalEventBase):

event_type: Literal["lyric"] = "lyric"
word: str
syllable: str | None = None
word_index: int
syllable_index: int = 0
alignment_confidence: float | None = None
source_note_id: str | None = None — links to a NoteEvent.event_id

BeatEvent(MusicalEventBase):

event_type: Literal["beat"] = "beat"
beat_number: int — 1-based within measure
is_downbeat: bool = False
tempo_bpm: float | None = None — tempo at this beat

KeyEvent(MusicalEventBase):

event_type: Literal["key"] = "key"
tonic: str — e.g. "C", "F#", "Bb"
mode: str — "major" or "minor" for v1; extensible
analysis_end_time: float | None = None — None means "until end of audio"
manually_overridden: bool = False

TempoEvent(MusicalEventBase):

event_type: Literal["tempo"] = "tempo"
tempo_bpm: float — must be > 0
analysis_end_time: float | None = None

SectionEvent(MusicalEventBase):

event_type: Literal["section"] = "section"
label: str — e.g. "intro", "verse", "chorus", "bridge", "outro", "unknown"

```
Add a discriminated union type alias at the bottom:

``` python
AnyMusicalEvent = Annotated[
    NoteEvent | RestEvent | ChordEvent | DrumHitEvent |
    LyricEvent | BeatEvent | KeyEvent | TempoEvent | SectionEvent,
    Field(discriminator="event_type")
] 

```


### Execution Constraints:

Pydantic v2 only (from pydantic import BaseModel, Field, field_validator, ConfigDict, model_validator)
Import constants from backend.schema.units — do not hardcode any magic numbers
All validators use @field_validator (Pydantic v2 style, not v1 @validator)
model_config = ConfigDict(extra="allow") on the base class only
Do not alter any existing backend files

### Output Request:
Return ONLY backend/schema/events.py.


# [P01-C] Create backend/schema/manifest.py — Extended Manifest Pydantic Model

## Target File: backend/schema/manifest.py

#### Context: MWTN's backend discovers songs by reading manifest.json from backend/data/<song_id>/. The current manifest is a plain dict loaded with json.load(). This task replaces that with a typed Pydantic v2 model that is backward-compatible with all existing manifest fields while adding the new fields required by the song-to-score expansion.

Current manifest fields (must all be preserved):

```json
{
  "song_id": "...",
  "title": "...",
  "stems": ["vocals", "bass", "drums", "guitar", "piano", "other"],
  "notes_available": true,
  "has_lyrics": false,
  "has_beats": true,
  "has_key": true,
  "bpm": 120.0,
  "key": "C major"
}
```
### Objective:
Create backend/schema/manifest.py with a SongManifest Pydantic v2 model that:

Loads all existing fields without breaking
Adds new song-to-score fields as optional with safe defaults
Can be serialized back to JSON to overwrite manifest.json when updated

### Technical Specifications:

``` python
SeparationEngineInfo(BaseModel):

name: str — e.g. "demucs"
model: str — e.g. "htdemucs_6s"
version: str | None = None
profile: str = "standard"

TranscriptionRun(BaseModel):

run_id: str — UUID
stem: str
engine: str
engine_version: str | None = None
config_hash: str | None = None
completed_at: str | None = None — ISO8601 string
status: str = "complete" — "complete" | "failed" | "partial"
error: str | None = None

ArtifactEntry(BaseModel) (the artifact registry entry, inline in the manifest):

artifact_id: str
artifact_type: str — e.g. "musicxml", "midi", "events_json", "solfa", "beats", "key"
file_path: str — relative to the song directory
source_run_id: str | None = None
schema_version: str
model: str | None = None
config_hash: str | None = None
created_at: str | None = None
is_stale: bool = False

SongManifest(BaseModel):

Existing fields (all required, same types as before):

song_id: str
title: str
stems: list[str] = []
notes_available: bool = False
has_lyrics: bool = False
has_beats: bool = False
has_key: bool = False
bpm: float | None = None
key: str | None = None — legacy string e.g. "C major"; kept for UI backward compat

New fields (all optional, safe defaults):

schema_version: str = Field(default_factory=lambda: SCHEMA_VERSION)
source_hash: str | None = None — sha256 of original audio
separation_engine: SeparationEngineInfo | None = None
transcription_runs: list[TranscriptionRun] = []
analysis_settings: dict = {}
artifacts: dict[str, ArtifactEntry] = {} — keyed by artifact_id
quality_summary: dict = {}
created_at: str | None = None
updated_at: str | None = None
model_config = ConfigDict(extra="allow") — absorb any fields added by future versions
``` 
Add two class methods:

``` python
@classmethod
def from_file(cls, path: Path) -> "SongManifest": ...
    # json.loads the file, validates through Pydantic

def to_file(self, path: Path) -> None: ...
    # writes model_dump(mode="json") back to path atomically
    # atomic write: write to .tmp then os.replace()
```
### Execution Constraints:

Pydantic v2 only
model_config = ConfigDict(extra="allow") on SongManifest — do not reject unknown fields from old manifests
Atomic write in to_file(): write to path.with_suffix(".tmp") then os.replace(tmp, path)
Import constants from backend.schema.units
Do not alter any existing backend files

### Output Request:
Return ONLY backend/schema/manifest.py.


# [P01-D] Create backend/schema/migrations.py — Schema Migration Utilities

Target File: ```backend/schema/migrations.py```

Context: MWTN currently stores analysis results as plain dicts in notes_<stem>.json, beats.json, key.json, and lyrics.json. These predate the canonical MusicalEvent schema. When the backend first accesses one of these legacy files, it needs to convert them into the new event format without modifying the original file. This migration module handles that conversion and provides a schema version registry for future upgrades.

### Objective:
Create ```backend/schema/migrations.py``` with:

A migration registry mapping old schema versions to upgrade functions
Legacy converter functions for each existing file type
A migrate_events() dispatcher that handles version detection and upgrade

Technical Specifications:

```python
Import from backend.schema.events: NoteEvent, BeatEvent, KeyEvent, LyricEvent, AnyMusicalEvent
Import from backend.schema.units: SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS

MigrationError(Exception) — raised when a schema version is unknown and no migration path exists.

MIGRATION_REGISTRY: dict[str, Callable] — maps "from_version" strings to upgrade functions. For v1 this only needs:

"legacy_notes" → migrate_legacy_notes()
"legacy_beats" → migrate_legacy_beats()
"legacy_key" → migrate_legacy_key()
"legacy_lyrics" → migrate_legacy_lyrics()
```
Legacy format reference (what these files currently look like in MWTN):

notes_<stem>.json — a list of dicts:

```json
[{"time": 1.24, "duration": 0.5, "frequency": 329.6, "confidence": 0.87, "midi_note": 64}]

beats.json:

```json
{"bpm": 120.0, "beats": [0.5, 1.0, 1.5, 2.0], "beat_times": [0.5, 1.0, 1.5]}

key.json:

```json
{"key": "C major", "confidence": 0.83}

lyrics.json — Whisper word-level output:

```json
{"segments": [{"words": [{"word": "hello", "start": 0.5, "end": 0.9, "probability": 0.97}]}]}
```
### Functions to implement:

```python
def migrate_legacy_notes(raw: list[dict], stem: str, source_model: str = "pyin_librosa") -> list[NoteEvent]:
    # Maps: time→start_time, duration→(end_time=time+duration), frequency→frequency_hz,
    #       confidence→confidence, midi_note→midi_pitch, track_id=stem
    # Generates event_id for each note (uuid4)

def migrate_legacy_beats(raw: dict, source_model: str = "librosa_beat_track") -> list[BeatEvent]:
    # raw["beats"] or raw["beat_times"] is the list of beat timestamps
    # Each timestamp → BeatEvent(start_time=t, beat_number=i+1, track_id="mix")
    # raw["bpm"] → TempoEvent(start_time=0.0, tempo_bpm=bpm, track_id="mix")
    # Returns list of BeatEvent + one TempoEvent

def migrate_legacy_key(raw: dict, source_model: str = "krumhansl_schmuckler") -> list[KeyEvent]:
    # raw["key"] is "C major" or "F# minor" — parse tonic and mode
    # raw["confidence"] → confidence
    # Returns [KeyEvent(start_time=0.0, tonic=..., mode=..., track_id="mix")]

def migrate_legacy_lyrics(raw: dict, source_model: str = "whisper") -> list[LyricEvent]:
    # Flattens raw["segments"][*]["words"] into LyricEvent list
    # word_index is global across all segments
    # probability → confidence

def check_schema_version(data: dict) -> str:
    # Returns the schema_version string if present
    # Returns "legacy_notes" / "legacy_beats" / "legacy_key" / "legacy_lyrics"
    # based on the shape of the data if no schema_version field
    # Raises MigrationError if shape is completely unrecognized

def migrate_events(data: dict | list, file_type: str, stem: str = "unknown") -> list[AnyMusicalEvent]:
    # Dispatcher: detects version/type, calls the right migrator, returns canonical events
    # file_type: "notes" | "beats" | "key" | "lyrics"
    # If data already has schema_version == SCHEMA_VERSION, deserialize directly via AnyMusicalEvent
    # If schema_version is in SUPPORTED_SCHEMA_VERSIONS, deserialize directly
    # If schema_version is unknown, raise MigrationError
```

### Execution Constraints:

Original files must never be read or written by this module — it operates on already-loaded dicts/lists
All output events must pass Pydantic validation (construct via model constructors, not raw dicts)
The check_schema_version function must not crash on empty dicts or empty lists — return "legacy_unknown" and let the caller decide
Do not alter any existing backend files

### Output Request:
Return ONLY backend/schema/migrations.py.

# [P01-E] Create backend/schema/validation.py — API Boundary Validators

### Target File: ```backend/schema/validation.py```

Context: MWTN's FastAPI backend currently does minimal input validation on POST /api/import and song data endpoints. The schema layer needs boundary validators that run at every API entry point where musical data enters or exits the system. These validators wrap the Pydantic models and produce FastAPI-compatible HTTPException responses.

### Objective:
Create backend/schema/validation.py with validation functions that the main.py route handlers will call. Each function raises HTTPException with a clear message on failure; on success it returns the validated model.

## Technical Specifications:

```python
from fastapi import HTTPException
from pathlib import Path
from backend.schema.events import AnyMusicalEvent, NoteEvent
from backend.schema.manifest import SongManifest
from backend.schema.units import SUPPORTED_SCHEMA_VERSIONS, MIDI_PITCH_MIN, MIDI_PITCH_MAX

def validate_manifest(raw: dict) -> SongManifest:
    # Attempt SongManifest(**raw)
    # On ValidationError: raise HTTPException(422, detail=formatted_errors)
    # On success: return the SongManifest instance

def validate_event_list(raw: list[dict]) -> list[AnyMusicalEvent]:
    # Validate each item as an AnyMusicalEvent (discriminated union)
    # Collect ALL errors before raising (don't stop at first)
    # On any errors: raise HTTPException(422, detail={"errors": [...], "valid_count": n, "error_count": m})
    # On success: return list of validated events

def validate_schema_version(data: dict | list) -> str:
    # Extract schema_version from data
    # If missing: return "legacy" (not an error — triggers migration path)
    # If present but not in SUPPORTED_SCHEMA_VERSIONS:
    #   raise HTTPException(422, detail=f"Unsupported schema version: {v!r}. Supported: {SUPPORTED_SCHEMA_VERSIONS}")
    # If present and supported: return the version string

def validate_song_id(song_id: str) -> str:
    # song_id must match r'^[a-zA-Z0-9_\-]{1,64}$'
    # On failure: raise HTTPException(400, detail=f"Invalid song_id: {song_id!r}")
    # On success: return the song_id unchanged

def validate_note_event_patch(patch: dict) -> dict:
    # Validates a partial note update (used by Plan 10 correction endpoints)
    # Allowed keys: "midi_pitch", "start_time", "end_time", "velocity", "confidence"
    # "midi_pitch" if present: must be int in [MIDI_PITCH_MIN, MIDI_PITCH_MAX]
    # "start_time", "end_time" if present: must be float >= 0.0
    # "end_time" if present alongside "start_time": must be > "start_time"
    # Unknown keys: raise HTTPException(400, detail=f"Unknown patch field: {key!r}")
    # Returns the validated patch dict unchanged on success
```
Also add a context manager for safe JSON loading from disk:

```python
def load_json_safe(path: Path) -> dict | list:
    # Reads and json.loads the file
    # On FileNotFoundError: raise HTTPException(404, detail=f"File not found: {path}")
    # On json.JSONDecodeError: raise HTTPException(422, detail=f"Invalid JSON at {path}: {e}")
    # Returns the parsed data
```
### Execution Constraints:

All functions must be pure — no filesystem side effects except load_json_safe
Error messages must name the specific field and value that failed, not just the exception type
Do not import from backend.main — this module has no knowledge of route handlers
Do not alter any existing backend files

### Output Request:
Return ONLY backend/schema/validation.py.


# [P01-F] Wire Schema into backend/main.py — Non-Breaking Integration

Target Files: `backend/main.py` (modify existing)

Context: MWTN's FastAPI backend (backend/main.py) currently loads manifests with raw json.load() and returns them as unvalidated dicts. With the schema layer in place (backend/schema/), the manifest loading must go through SongManifest.from_file(), and song_id parameters on all routes must go through validate_song_id(). No existing route behavior changes — this is purely a hardening pass.

### Objective:
Modify backend/main.py to:

Replace all raw json.load(manifest_path) calls with SongManifest.from_file(manifest_path)
Add validate_song_id() to every route that accepts song_id as a path parameter
Add the new GET /api/health endpoint
Add the new GET /api/songs/{song_id}/schema introspection endpoint

### Technical Specifications:

Imports to add at the top of main.py:

```python
from backend.schema.manifest import SongManifest
from backend.schema.validation import validate_song_id, validate_manifest, load_json_safe
from backend.schema.units import SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS
```

For every existing route that has song_id: str as a path parameter, add this as the first line of the handler body:

```python
song_id = validate_song_id(song_id)
```
Replace every manifest loading pattern that looks like:

```python
manifest_path = DATA_DIR / song_id / "manifest.json"
with open(manifest_path) as f:
    manifest = json.load(f)
```

With:

```python
manifest_path = DATA_DIR / song_id / "manifest.json"
manifest = SongManifest.from_file(manifest_path)
```

Then replace manifest["field"] dict access with manifest.field attribute access throughout the handler.

New endpoint — GET `/api/health`:

```python
@app.get("/api/health")
async def health_check():
    checks = {}
    # 1. data_dir: check DATA_DIR exists and is writable
    checks["data_dir"] = {"status": "ok", "path": str(DATA_DIR)} if DATA_DIR.exists() else {"status": "error", "detail": "DATA_DIR missing"}
    # 2. ffmpeg: try subprocess ["ffmpeg", "-version"], capture first line
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        checks["ffmpeg"] = {"status": "ok", "version": result.stdout.split("\n")[0]}
    except Exception as e:
        checks["ffmpeg"] = {"status": "error", "detail": str(e)}
    # 3. schema: always ok — just report the current version
    checks["schema"] = {"status": "ok", "current_version": SCHEMA_VERSION, "supported_versions": list(SUPPORTED_SCHEMA_VERSIONS)}
    # overall status
    overall = "ok" if all(c.get("status") == "ok" for c in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}
```
New endpoint — GET `/api/songs/{song_id}/schema`:

```python
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
```
Execution Constraints:

Every existing route must continue to return the same JSON shape as before — do not rename, add, or remove fields from existing responses
Where a handler previously returned manifest as a dict (e.g. return manifest), return manifest.model_dump(mode="json") instead to maintain JSON-serializable output
Do not remove the json import — it is still needed for other non-manifest operations
Use subprocess (already likely imported); if not present, add it
Do not change any route path, HTTP method, or query parameter name
The subprocess call for ffmpeg must use shell=False and a list argument

Output Request:
Return ONLY the complete modified backend/main.py. Include the full file — do not return a diff or partial snippet.