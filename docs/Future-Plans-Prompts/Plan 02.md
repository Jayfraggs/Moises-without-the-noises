
---

## PLAN 02 — Agent Prompt Suite
### Unified Automatic Music Transcription (AMT) Engine

Eight prompts. Run in the order listed — each builds on files created by the previous one.

**Prerequisite:** Plan 01 must be complete. All prompts in this suite import from `backend.schema.*`.

---

### [P02-A] Create `backend/transcription/config.py` — TranscriptionConfig and Engine Registry

**Target File:** `backend/transcription/config.py` + `backend/transcription/__init__.py` + `backend/transcription/engines/__init__.py`

**Context:** MWTN is adding a multi-engine AMT layer on top of its existing Python/FastAPI backend. Before any engine is implemented, the shared configuration contract must exist — every engine receives a `TranscriptionConfig` and every dispatcher decision is based on it. The engine registry maps human-readable names to availability flags so the system degrades gracefully when optional models are not installed.

**Objective:**
Create the configuration Pydantic model, the engine registry, and both `__init__.py` files.

**Technical Specifications:**

`TranscriptionConfig(BaseModel)` in `config.py`:
- `stem_type: str` — one of `STEM_ROLES` from `backend.schema.units`
- `quality_profile: Literal["fast", "standard", "high_quality"] = "standard"`
- `onset_threshold: float = 0.5` — [0.0, 1.0]; for Basic Pitch
- `frame_threshold: float = 0.3` — [0.0, 1.0]; for Basic Pitch
- `minimum_note_length_ms: float = 50.0` — post-processing filter
- `minimum_frequency_hz: float = 32.7` — C1; lower bound for pitch detection
- `maximum_frequency_hz: float = 2093.0` — C7; upper bound
- `minimum_confidence: float = 0.3` — post-processing filter
- `chunk_duration_s: float = 60.0` — audio chunking window
- `chunk_overlap_s: float = 2.0` — overlap between chunks
- `sample_rate: int = 22050` — target SR for preprocessing
- `device: str = "cpu"` — `"cpu"` or `"cuda"`; populated by dispatcher
- `source_model: str = ""` — filled in by the engine before transcription

Add a `config_hash` property:
```python
@property
def config_hash(self) -> str:
    import hashlib, json
    data = self.model_dump(exclude={"device", "source_model"})
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
```

`EngineRegistry` — a plain dict constant, not a class:
```python
ENGINE_REGISTRY: dict[str, dict] = {
    "pyin": {
        "display_name": "pYIN (librosa)",
        "license": "ISC",
        "polyphonic": False,
        "requires_gpu": False,
        "install_check": "librosa",          # module name to try-import for availability check
        "stems": ["vocals", "bass"],
        "profiles": ["fast"],
        "data_cost_mb": 0,
    },
    "basic_pitch": {
        "display_name": "Basic Pitch (Spotify)",
        "license": "MIT",
        "polyphonic": True,
        "requires_gpu": False,
        "install_check": "basic_pitch",
        "stems": ["vocals", "bass", "guitar", "piano", "other"],
        "profiles": ["standard", "high_quality"],
        "data_cost_mb": 67,                  # 50 deps + 17 weights
    },
    "piano_kong": {
        "display_name": "Piano Transcription (Kong et al.)",
        "license": "MIT",
        "polyphonic": True,
        "requires_gpu": False,
        "install_check": "piano_transcription_inference",
        "stems": ["piano"],
        "profiles": ["high_quality"],
        "data_cost_mb": 350,                 # 200 deps + 150 weights
        "caveat": "Piano stems only.",
    },
    "adtlib": {
        "display_name": "ADTLib (drum transcription)",
        "license": "MIT",
        "polyphonic": False,
        "requires_gpu": False,
        "install_check": "adtlib",
        "stems": ["drums"],
        "profiles": ["standard", "high_quality"],
        "data_cost_mb": 30,
        "caveat": "Drum stems only.",
    },
    "mt3": {
        "display_name": "MT3 (Google Magenta) — NOT IMPLEMENTED IN V1",
        "license": "Apache-2.0",
        "polyphonic": True,
        "requires_gpu": True,
        "install_check": None,
        "stems": [],
        "profiles": [],
        "data_cost_mb": 2000,
        "caveat": "Deferred to v2. 2 GB checkpoint; JAX dependency.",
        "enabled": False,
    },
}
```

Add a helper:
```python
def is_engine_available(engine_name: str) -> bool:
    """Try-import the engine's install_check module. Returns False if not installed."""
    entry = ENGINE_REGISTRY.get(engine_name, {})
    check = entry.get("install_check")
    if check is None:
        return False
    try:
        importlib.import_module(check)
        return True
    except ImportError:
        return False
```

`backend/transcription/__init__.py` — empty file.
`backend/transcription/engines/__init__.py` — empty file.

**Execution Constraints:**
- Pydantic v2 only
- `ENGINE_REGISTRY` is a module-level constant — not built at call time
- `is_engine_available` must never raise — always return bool
- Do not import any engine implementations here (that would cause ImportError when an engine is absent)
- Do not alter any existing backend files

**Output Request:**
Return `backend/transcription/config.py`, `backend/transcription/__init__.py`, and `backend/transcription/engines/__init__.py`.

---

### [P02-B] Create `backend/transcription/engines/pyin.py` — Refactored pYIN Engine

**Target File:** `backend/transcription/engines/pyin.py`

**Context:** MWTN currently performs note extraction in `backend/note_extraction.py` using pYIN via librosa. This logic must be moved into the new engine interface without changing its behavior. The output must now be a `list[NoteEvent]` using the Plan 01 schema instead of raw dicts. The original `note_extraction.py` remains on disk and is left unmodified — the dispatcher will call the new engine; the old file stays for backward compatibility until it is explicitly deprecated.

**Objective:**
Implement the pYIN engine adapter that conforms to the `AMTEngine` protocol and wraps the existing librosa pYIN logic.

**Technical Specifications:**

`AMTEngine` Protocol (define inline in this file — do not create a separate protocol file yet):
```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class AMTEngine(Protocol):
    def supports(self, stem_type: str, quality_profile: str) -> bool: ...
    def transcribe(self, audio_path: str, config: "TranscriptionConfig") -> list: ...
    def health_check(self) -> bool: ...
    def model_info(self) -> dict: ...
```

`PYINEngine` class:
- `supports(stem_type, quality_profile)` → `True` only when `stem_type in ("vocals", "bass")` and `quality_profile == "fast"`
- `health_check()` → try `import librosa`; return `True` on success, `False` on `ImportError`
- `model_info()` → return `{"engine": "pyin", "library": "librosa", "version": librosa.__version__, "polyphonic": False}`

`transcribe(audio_path, config)` implementation:
1. Load audio with `librosa.load(audio_path, sr=config.sample_rate, mono=True)`
2. Run pYIN:
   ```python
   f0, voiced_flag, voiced_prob = librosa.pyin(
       y,
       fmin=config.minimum_frequency_hz,
       fmax=config.maximum_frequency_hz,
       sr=sr,
       frame_length=2048,
       hop_length=512,
   )
   ```
3. Convert voiced frames to note events:
   - Scan voiced runs (consecutive `voiced_flag == True` frames)
   - Each run → one `NoteEvent`
   - `start_time` = first frame index × hop_length / sr
   - `end_time` = (last frame index + 1) × hop_length / sr
   - `frequency_hz` = median of `f0` values in that run (ignoring NaN)
   - `midi_pitch` = `int(round(librosa.hz_to_midi(frequency_hz)))`; clamp to [0, 127]
   - `confidence` = mean of `voiced_prob` in that run; clamp to [0.0, 1.0]
   - `velocity` = None (pYIN provides no amplitude information)
   - `source_model` = `f"pyin_librosa_{librosa.__version__}"`
   - `track_id` = `config.stem_type`

4. Post-process:
   - Filter out notes shorter than `config.minimum_note_length_ms / 1000.0` seconds
   - Filter out notes with `confidence < config.minimum_confidence`
   - Sort by `start_time`

5. Return `list[NoteEvent]`

Import `NoteEvent` from `backend.schema.events` and `TranscriptionConfig` from `backend.transcription.config`.

**Execution Constraints:**
- Do not import `basic_pitch`, `piano_transcription_inference`, or any optional engine
- All NoteEvent construction must go through the Pydantic model constructor, not raw dict
- `librosa.pyin` returns NaN for unvoiced frames — handle NaN gracefully (skip those frames, do not crash)
- If `audio_path` does not exist, raise `FileNotFoundError` immediately — do not create a partial result
- The `AMTEngine` Protocol is defined here and will be re-exported by later engine files that import it

**Output Request:**
Return ONLY `backend/transcription/engines/pyin.py`.

---

### [P02-C] Create `backend/transcription/preprocessing.py` — Audio Preprocessing Pipeline

**Target File:** `backend/transcription/preprocessing.py`

**Context:** Every AMT engine requires audio in a specific format. Rather than implementing preprocessing inside each engine, MWTN centralizes it here. This module is called by the dispatcher before handing audio to any engine. It also handles chunking of long audio files to prevent memory issues during inference.

**Objective:**
Create a preprocessing module that normalizes audio for any engine and produces chunks for long files.

**Technical Specifications:**

`preprocess_for_transcription(audio_path: str | Path, config: TranscriptionConfig) -> Path`:
- Loads the source audio with `soundfile.read()` or `librosa.load()` (prefer soundfile for speed)
- Resamples to `config.sample_rate` if different from source SR
- Converts to mono (average channels if stereo)
- Peak-normalizes to -1 dBFS: `audio = audio / (np.abs(audio).max() + 1e-8)`
- Writes the processed audio to a temp file in the system temp dir (use `tempfile.mkstemp(suffix=".wav")`)
- Returns the `Path` to the temp file
- The caller is responsible for deleting the temp file

`chunk_audio(audio_path: str | Path, chunk_s: float, overlap_s: float, sr: int) -> list[tuple[Path, float]]`:
- Loads the preprocessed audio
- If duration ≤ `chunk_s + overlap_s`: returns `[(audio_path, 0.0)]` — no chunking needed
- Splits into chunks with `overlap_s` on each side
- Each chunk is written to a temp WAV file
- Returns list of `(chunk_path, chunk_start_offset_s)` tuples
- `chunk_start_offset_s` is the time in the original audio where this chunk begins (needed for event time remapping)

`merge_chunked_events(chunk_results: list[tuple[list, float]], onset_tolerance_s: float = 0.02) -> list`:
- Input: list of `(events_for_chunk, chunk_start_offset_s)` tuples
- For each chunk: remap all event times by adding `chunk_start_offset_s` to `start_time` and `end_time`
- Merge all remapped events into a single list
- Deduplicate: two events are duplicates if their `start_time` values differ by less than `onset_tolerance_s` AND their `midi_pitch` values are equal — keep the one with higher `confidence`
- Sort result by `start_time`
- Return merged, deduplicated list

`cleanup_temp_files(paths: list[Path]) -> None`:
- Silently deletes each path; does not raise if a file is already missing

**Execution Constraints:**
- Use `numpy` and `soundfile` for audio I/O; `librosa.resample` only for resampling (not for full load)
- All temp files must be named with a `mwtn_preproc_` prefix for debuggability
- `merge_chunked_events` must handle the case where one of the input event lists is empty
- Never read or write to `backend/data/` — all files in this module are strictly temp
- Do not import any AMT engine here

**Output Request:**
Return ONLY `backend/transcription/preprocessing.py`.

---

### [P02-D] Create `backend/transcription/engines/basic_pitch.py` — Basic Pitch Engine Adapter

**Target File:** `backend/transcription/engines/basic_pitch.py`

**Context:** Basic Pitch (Spotify Research, MIT license) is the default polyphonic AMT engine for MWTN. It handles vocals, bass, guitar, piano, and "other" stems. It must be importable without crashing when `basic_pitch` is not installed — the dispatcher checks `is_engine_available("basic_pitch")` before calling it.

**Objective:**
Implement the Basic Pitch engine adapter conforming to the `AMTEngine` protocol.

**Technical Specifications:**

`BasicPitchEngine` class:

`supports(stem_type, quality_profile)` → `True` when:
- `stem_type in ("vocals", "bass", "guitar", "piano", "other")` AND
- `quality_profile in ("standard", "high_quality")`

`health_check()`:
```python
try:
    from basic_pitch.inference import predict
    from basic_pitch import ICASSP_2022_MODEL_PATH
    return True
except ImportError:
    return False
```

`model_info()`:
```python
try:
    import basic_pitch
    return {
        "engine": "basic_pitch",
        "version": basic_pitch.__version__,
        "license": "MIT",
        "polyphonic": True,
        "model": "ICASSP_2022",
        "data_cost_mb": 67,
    }
except ImportError:
    return {"engine": "basic_pitch", "available": False}
```

`transcribe(audio_path, config)`:
1. Guard: if `not self.health_check()`: raise `ImportError("basic-pitch is not installed. Run: pip install basic-pitch")`
2. Import lazily inside the method:
   ```python
   from basic_pitch.inference import predict
   from basic_pitch import ICASSP_2022_MODEL_PATH
   ```
3. Run inference:
   ```python
   model_output, midi_data, note_events = predict(
       audio_path,
       ICASSP_2022_MODEL_PATH,
       onset_threshold=config.onset_threshold,
       frame_threshold=config.frame_threshold,
       minimum_note_length=config.minimum_note_length_ms,
       minimum_frequency=config.minimum_frequency_hz,
       maximum_frequency=config.maximum_frequency_hz,
       melodia_trick=True,
   )
   ```
4. Convert `note_events` (Basic Pitch returns a list of tuples: `(start_s, end_s, pitch_midi, confidence, pitch_bend)`) to `NoteEvent` objects:
   ```python
   NoteEvent(
       start_time=float(start_s),
       end_time=float(end_s),
       midi_pitch=int(pitch_midi),
       frequency_hz=float(librosa.midi_to_hz(pitch_midi)),
       confidence=float(confidence),
       velocity=None,
       source_model=f"basic_pitch_{basic_pitch.__version__}",
       track_id=config.stem_type,
   )
   ```
5. Post-process:
   - Filter `confidence < config.minimum_confidence`
   - Filter duration `< config.minimum_note_length_ms / 1000.0`
   - Sort by `start_time`
6. Return `list[NoteEvent]`

Add a class-level docstring noting the guitar quality caveat:
```
NOTE: Guitar AMT quality via Basic Pitch is lower than piano or vocal transcription.
Guitar stem outputs will typically require human review (Plan 10). This is a known
limitation of all current open-source guitar AMT models, not a Basic Pitch-specific bug.
```

**Execution Constraints:**
- All `basic_pitch` imports must be inside `transcribe()` and `health_check()` — never at module top level
- Import `librosa` at module top level (it's always available in MWTN)
- Import `NoteEvent` from `backend.schema.events` and `TranscriptionConfig` from `backend.transcription.config`
- `note_events` from Basic Pitch may be an empty list — handle gracefully (return `[]`, do not crash)
- Do not call `preprocess_for_transcription` inside this engine — preprocessing is the dispatcher's responsibility

**Output Request:**
Return ONLY `backend/transcription/engines/basic_pitch.py`.

---

### [P02-E] Create `backend/transcription/engines/piano_kong.py` and `backend/transcription/engines/drums.py` — Optional High-Quality Engines

**Target Files:** `backend/transcription/engines/piano_kong.py`, `backend/transcription/engines/drums.py`

**Context:** Two optional, flag-gated engines. `piano_kong.py` wraps Piano Transcription by Qiuqiang Kong (MIT, piano-only, ~150 MB weights). `drums.py` wraps ADTLib (MIT, drums-only, ~30 MB). Both are never imported at the top level of the dispatcher — only if `is_engine_available()` returns `True` and the user's profile selects them. The interface is identical to `BasicPitchEngine`.

**Objective:**
Implement both optional engine adapters.

**Technical Specifications:**

**`PianoKongEngine` in `piano_kong.py`:**

`supports(stem_type, quality_profile)` → `True` only when `stem_type == "piano"` and `quality_profile == "high_quality"`

`health_check()`:
```python
try:
    import piano_transcription_inference
    return True
except ImportError:
    return False
```

`model_info()`:
```python
return {
    "engine": "piano_kong",
    "license": "MIT",
    "polyphonic": True,
    "stems": ["piano"],
    "profiles": ["high_quality"],
    "data_cost_mb": 350,
    "caveat": "Piano stems only. ~350 MB first-run download on Colab.",
}
```

`transcribe(audio_path, config)`:
1. Guard on `health_check()`
2. Lazy import:
   ```python
   from piano_transcription_inference import PianoTranscription, sample_rate as pt_sr, load_audio
   ```
3. Load audio using the library's own `load_audio` (it expects its own specific SR):
   ```python
   audio, _ = load_audio(str(audio_path), sr=pt_sr, mono=True)
   ```
4. Run transcription to a temp MIDI file:
   ```python
   import tempfile, os
   with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as tmp:
       tmp_midi_path = tmp.name
   transcriptor = PianoTranscription(device=config.device, checkpoint_path=None)
   result = transcriptor.transcribe(audio, tmp_midi_path)
   os.unlink(tmp_midi_path)
   ```
5. Convert `result["est_note_events"]` (list of dicts with keys `onset_time`, `offset_time`, `midi_note`, `velocity`) to `NoteEvent` objects:
   ```python
   NoteEvent(
       start_time=float(e["onset_time"]),
       end_time=float(e["offset_time"]),
       midi_pitch=int(e["midi_note"]),
       frequency_hz=float(librosa.midi_to_hz(e["midi_note"])),
       velocity=int(e["velocity"]),
       confidence=1.0,        # Kong model doesn't expose per-note confidence
       source_model="piano_kong_1.0",
       track_id=config.stem_type,
   )
   ```
6. Post-process: filter by minimum duration; sort by `start_time`
7. Return `list[NoteEvent]`

---

**`ADTLibEngine` in `drums.py`:**

`supports(stem_type, quality_profile)` → `True` only when `stem_type == "drums"`

`health_check()`:
```python
try:
    import adtlib
    return True
except ImportError:
    return False
```

`model_info()`:
```python
return {
    "engine": "adtlib",
    "license": "MIT",
    "polyphonic": False,
    "stems": ["drums"],
    "data_cost_mb": 30,
}
```

`transcribe(audio_path, config)` — produce `DrumHitEvent` objects:
1. Guard on `health_check()`
2. Lazy import: `import adtlib`
3. ADTLib's API varies by version. Use the following pattern and handle `AttributeError` if the API differs:
   ```python
   # Attempt standard ADTLib inference
   try:
       result = adtlib.transcribe(str(audio_path))
       # result expected to be a list of (time_s, drum_label, velocity) tuples
   except Exception as e:
       raise RuntimeError(f"ADTLib inference failed: {e}") from e
   ```
4. Map ADTLib drum labels to MWTN canonical `drum_type` strings:
   ```python
   DRUM_LABEL_MAP = {
       "KD": "kick", "BD": "kick",
       "SD": "snare", "SN": "snare",
       "HH": "hihat_closed", "HHC": "hihat_closed",
       "HHO": "hihat_open",
       "TT": "tom_mid", "LT": "tom_low", "HT": "tom_high",
       "CY": "crash", "CR": "crash",
       "RD": "ride",
   }
   ```
5. Convert to `DrumHitEvent`:
   ```python
   DrumHitEvent(
       start_time=float(time_s),
       end_time=None,          # drum hits are instantaneous
       drum_type=DRUM_LABEL_MAP.get(label, "unknown"),
       velocity=int(vel) if vel is not None else None,
       confidence=1.0,
       source_model="adtlib",
       track_id="drums",
   )
   ```
6. Return `list[DrumHitEvent]`

**Important:** Both engines must handle the case where the library is installed but inference fails (corrupted audio, incompatible sample rate, etc.) by raising a `RuntimeError` with a clear message. The dispatcher catches this and marks the stem transcription as `"failed"`.

**Execution Constraints:**
- All engine-specific imports must be lazy (inside the methods that use them)
- `librosa` can be imported at module top level
- Import `NoteEvent`, `DrumHitEvent` from `backend.schema.events`
- Import `TranscriptionConfig` from `backend.transcription.config`
- Piano Kong: delete the temp MIDI file even if transcription fails (use try/finally)
- Do not call preprocessing from inside these engines

**Output Request:**
Return BOTH files: `backend/transcription/engines/piano_kong.py` and `backend/transcription/engines/drums.py`.

---

### [P02-F] Create `backend/transcription/dispatcher.py` — Engine Selection and Job Orchestration

**Target File:** `backend/transcription/dispatcher.py`

**Context:** The dispatcher is the single entry point for all transcription work in MWTN. It selects the correct engine for a given stem and quality profile, runs preprocessing and chunking, orchestrates inference, merges chunk results, caches outputs, and returns canonical `MusicalEvent` lists. It also manages job status in memory for the duration of a process run.

**Objective:**
Create the transcription dispatcher with engine selection, caching, chunked inference, and in-memory job state tracking.

**Technical Specifications:**

**Transcription profile matrix** (matches Plan 02 document exactly):
```python
PROFILE_MATRIX: dict[str, dict[str, str]] = {
    "vocals": {"fast": "pyin",        "standard": "basic_pitch", "high_quality": "basic_pitch"},
    "bass":   {"fast": "pyin",        "standard": "basic_pitch", "high_quality": "basic_pitch"},
    "piano":  {"fast": "basic_pitch", "standard": "basic_pitch", "high_quality": "piano_kong"},
    "guitar": {"fast": "basic_pitch", "standard": "basic_pitch", "high_quality": "basic_pitch"},
    "drums":  {"fast": "adtlib",      "standard": "adtlib",      "high_quality": "adtlib"},
    "other":  {"fast": "basic_pitch", "standard": "basic_pitch", "high_quality": "basic_pitch"},
}

GUITAR_QUALITY_CAVEAT = (
    "Guitar transcription quality is lower than vocals or piano with all current open-source models. "
    "Expect errors requiring human review in the Score workspace."
)
```

**Engine loading** (lazy, with fallback):
```python
def _load_engine(engine_name: str):
    """Load an engine by name. Returns None if unavailable."""
    from backend.transcription.config import is_engine_available
    if not is_engine_available(engine_name):
        return None
    if engine_name == "pyin":
        from backend.transcription.engines.pyin import PYINEngine
        return PYINEngine()
    if engine_name == "basic_pitch":
        from backend.transcription.engines.basic_pitch import BasicPitchEngine
        return BasicPitchEngine()
    if engine_name == "piano_kong":
        from backend.transcription.engines.piano_kong import PianoKongEngine
        return PianoKongEngine()
    if engine_name == "adtlib":
        from backend.transcription.engines.drums import ADTLibEngine
        return ADTLibEngine()
    return None
```

**Fallback chain** — if the preferred engine is unavailable, fall back:
```python
FALLBACK_CHAIN: dict[str, list[str]] = {
    "piano_kong": ["basic_pitch"],
    "adtlib":     ["basic_pitch"],   # imperfect but better than nothing
    "basic_pitch": ["pyin"],         # monophonic only but available
    "pyin":        [],               # no fallback
}
```

**In-memory job state** (simple dict, sufficient for v1):
```python
_JOB_STATE: dict[str, dict] = {}
# key: run_id
# value: { "status": str, "stage": str, "stem": str, "song_id": str, "warnings": list[str], "error": str | None }
```

**Main function:**
```python
def transcribe_stem(
    audio_path: str | Path,
    song_id: str,
    stem_type: str,
    config: TranscriptionConfig,
    cache_dir: Path,
    run_id: str | None = None,
) -> tuple[list, dict]:
    """
    Transcribe one stem. Returns (events, job_info).
    job_info: { "run_id", "engine_used", "cached", "warnings", "status" }
    """
```

Implementation steps inside `transcribe_stem`:
1. Generate `run_id = uuid.uuid4().hex` if not provided
2. Set job state: `status="preprocessing", stage="preprocessing"`
3. Compute cache key: `sha256(audio_path bytes read) + engine_name + config.config_hash` → 16 hex chars
4. Check cache: look for `cache_dir / f"{stem_type}_{cache_key}.json"`; if it exists, load and deserialize back to events, set `status="complete"`, return with `cached=True`
5. Select engine via `PROFILE_MATRIX[stem_type][config.quality_profile]`; if not in matrix, use `"basic_pitch"`
6. Load engine via `_load_engine`; if `None`, try fallback chain; if all fail, set `status="failed"`, raise `RuntimeError(f"No transcription engine available for stem={stem_type}")`
7. Warn if guitar: append `GUITAR_QUALITY_CAVEAT` to warnings
8. Warn if engine was a fallback: append `f"Preferred engine unavailable; used {engine_name} instead"` to warnings
9. Update `config.source_model` with engine's `model_info()["engine"]` + version
10. Set job state: `status="preprocessing", stage="preprocessing"`
11. Preprocess: call `preprocess_for_transcription(audio_path, config)` → `preproc_path`
12. Chunk: call `chunk_audio(preproc_path, config.chunk_duration_s, config.chunk_overlap_s, config.sample_rate)` → `chunks`
13. Set job state: `status="transcribing", stage="transcribing"`
14. Transcribe each chunk: call `engine.transcribe(chunk_path, config)` → chunk events; collect `(events, offset)` pairs
15. Set job state: `status="merging", stage="merging"`
16. Merge: call `merge_chunked_events(chunk_results)`
17. Set job state: `status="validating", stage="validating"`
18. Validate: each event must pass Pydantic validation (they already should; this is a safety check)
19. Write cache: serialize events to `cache_dir / f"{stem_type}_{cache_key}.json"`
20. Cleanup temp files
21. Set job state: `status="complete"`
22. Return `(events, job_info)`

Wrap step 14 in a per-chunk `try/except`; on failure for a chunk, log the error and append a warning rather than failing the entire stem.

**Status query function:**
```python
def get_job_status(run_id: str) -> dict:
    return _JOB_STATE.get(run_id, {"status": "not_found"})
```

**Execution Constraints:**
- All engine imports are lazy (inside `_load_engine`)
- Cache directory is created by the dispatcher if it doesn't exist: `cache_dir.mkdir(parents=True, exist_ok=True)`
- Cache serialization: `json.dumps([e.model_dump(mode="json") for e in events])`
- Cache deserialization: use `AnyMusicalEvent` discriminated union adapter from `backend.schema.events`
- The `_JOB_STATE` dict is module-level — acceptable for v1 single-process deployment
- Do not import from `backend.main`

**Output Request:**
Return ONLY `backend/transcription/dispatcher.py`.

---

### [P02-G] Create `backend/transcription_config.yaml` — User-Facing Engine Configuration

**Target File:** `backend/transcription_config.yaml`

**Context:** MWTN is an open-source project. Developers and advanced users need a single plain-text file to control which engines are active and what thresholds apply, without touching Python code. The dispatcher reads this file on startup. The file documents all options inline with comments.

**Objective:**
Create a self-documenting YAML configuration file for the transcription system.

**Technical Specifications:**

The file must contain these sections with inline comments explaining each option:

```yaml
# MWTN Transcription Engine Configuration
# ----------------------------------------
# Controls which AMT engines are active and their thresholds.
# All heavy ML runs on Google Colab — see colab/mwtn_notebook.ipynb.
# Restart the backend after changing this file.

# --- Enabled engines ---
# Basic Pitch and pYIN are always available (no extra install needed for pYIN).
# Set to false to disable an engine (e.g. if you hit Colab memory limits).
engines:
  pyin:        { enabled: true }
  basic_pitch: { enabled: true }
  piano_kong:  { enabled: false }   # High quality piano. ~350 MB first-run. Set true to activate.
  adtlib:      { enabled: false }   # Drum transcription. ~30 MB. Set true to activate.
  mt3:         { enabled: false }   # NOT IMPLEMENTED. Deferred to v2.

# --- Quality profiles per stem ---
# "fast"         → fastest available engine (pYIN for vocals/bass; Basic Pitch elsewhere)
# "standard"     → recommended default (Basic Pitch for all polyphonic stems)
# "high_quality" → best available engine per stem (Piano Kong for piano if enabled)
default_profiles:
  vocals:  fast        # pYIN is sufficient and fast for monophonic vocal melodies
  bass:    fast        # pYIN is sufficient for bass lines
  piano:   standard    # Change to high_quality to use Piano Kong (requires piano_kong: enabled: true)
  guitar:  standard    # NOTE: guitar AMT quality is low for ALL open-source models. Expect manual review.
  drums:   standard    # Requires adtlib: enabled: true for drum-specific transcription
  other:   standard

# --- Post-processing thresholds ---
postprocessing:
  minimum_confidence: 0.30       # Drop notes below this confidence [0.0–1.0]
  minimum_note_length_ms: 50.0   # Drop notes shorter than this (milliseconds)

# --- Basic Pitch thresholds ---
# Lower onset_threshold → more notes detected (more false positives)
# Higher onset_threshold → fewer notes (more misses)
basic_pitch:
  onset_threshold: 0.50
  frame_threshold: 0.30
  minimum_frequency_hz: 32.7    # C1 — lowest note to detect
  maximum_frequency_hz: 2093.0  # C7 — highest note to detect

# --- Chunking ---
# Long audio is split into overlapping chunks to prevent memory issues.
chunking:
  chunk_duration_s: 60.0    # Each chunk is this many seconds
  chunk_overlap_s: 2.0      # Overlap between adjacent chunks (for clean merging)

# --- Hardware ---
device: cpu     # "cpu" or "cuda". Use "cuda" only if running locally with a GPU.
                # Colab handles GPU automatically; leave this as "cpu" for Colab use.
```

**Execution Constraints:**
- Every key must have an inline comment
- Do not include any Python-specific syntax — pure YAML only
- The `mt3` section must clearly state it is not implemented in v1

**Output Request:**
Return ONLY `backend/transcription_config.yaml`.

---

### [P02-H] Wire Transcription into `backend/main.py` — New Endpoints Only

**Target File:** `backend/main.py` (modify existing)

**Context:** Plan 01 already hardened `main.py` with schema validation and the health check endpoint. Plan 02 now adds three new transcription endpoints. These are additive only — no existing route is modified.

**Objective:**
Add three new endpoints to `backend/main.py` for transcription job management. Do not touch any existing route.

**Technical Specifications:**

**Imports to add:**
```python
import yaml
from backend.transcription.dispatcher import transcribe_stem, get_job_status
from backend.transcription.config import TranscriptionConfig, ENGINE_REGISTRY, is_engine_available
from pathlib import Path
import threading
import uuid
```

**Load transcription config at startup** (add near the top of `main.py`, after existing config loading):
```python
_TRANSCRIPTION_CONFIG_PATH = Path(__file__).parent / "transcription_config.yaml"
_TRANSCRIPTION_CFG: dict = {}
if _TRANSCRIPTION_CONFIG_PATH.exists():
    with open(_TRANSCRIPTION_CONFIG_PATH) as f:
        _TRANSCRIPTION_CFG = yaml.safe_load(f) or {}
```

**New endpoint 1 — `GET /api/transcription/engines`:**
```python
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
```

**New endpoint 2 — `POST /api/songs/{song_id}/transcription`:**
```python
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
            events, info = transcribe_stem(
                audio_path=stem_audio_path,
                song_id=song_id,
                stem_type=stem,
                config=config,
                cache_dir=cache_dir,
                run_id=run_id,
            )
            # Write events to disk
            events_path = DATA_DIR / song_id / "transcription_cache" / f"{stem}_events.json"
            events_path.parent.mkdir(parents=True, exist_ok=True)
            events_path.write_text(
                json.dumps([e.model_dump(mode="json") for e in events], indent=2)
            )
        except Exception as e:
            # Job state is already updated inside dispatcher on failure
            pass  # errors are stored in _JOB_STATE via dispatcher

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {"run_id": run_id, "status": "queued", "stem": stem, "song_id": song_id}
```

**New endpoint 3 — `GET /api/songs/{song_id}/transcription/{run_id}/status`:**
```python
@app.get("/api/songs/{song_id}/transcription/{run_id}/status")
async def transcription_status(song_id: str, run_id: str):
    song_id = validate_song_id(song_id)
    state = get_job_status(run_id)
    if state.get("status") == "not_found":
        raise HTTPException(404, detail=f"No job found with run_id: {run_id}")
    return state
```

**Also add `pyyaml` to `backend/requirements.txt`** (add the line `pyyaml>=6.0` if not already present).

**Execution Constraints:**
- Do not modify any existing route
- The background thread is daemon=True so it doesn't block server shutdown
- `json` is already imported in `main.py` — do not re-import
- `DATA_DIR` is already defined in `main.py` — use it
- If `pyyaml` is not in `requirements.txt`, add it

**Output Request:**
Return the three new endpoint functions as a clearly labeled code block (not the entire `main.py` — these are additive only), plus the `pyyaml` requirements line. Label each block clearly so the developer knows exactly where to insert each one.

---

**Implementation order:** P02-A → P02-B → P02-C → P02-D → P02-E → P02-F → P02-G → P02-H

**Mobile data note:** Plan 02 itself is zero local data cost — all Python files. The first time the Colab notebook runs `pip install basic-pitch`, that's ~50 MB on Colab's connection, not yours. `piano_kong` (~350 MB) and `adtlib` (~30 MB) only download if you set `enabled: true` in `transcription_config.yaml` — which you control before running the notebook.