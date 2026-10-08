## PLAN 03 — Agent Prompt Suite
### Production Source Separation PipelineSix prompts for Plan 03. Run after all Plan 01 and 02 prompts are complete.

---

### [P03-A] Create `backend/separation/engine.py` — Protocol, Config, and Result Models

**Target Files:** `backend/separation/engine.py`, `backend/separation/__init__.py`, `backend/separation/engines/__init__.py`

**Context:** MWTN's existing separation lives in `backend/separation.py` as a single flat file with hard-coded Demucs assumptions. The expanded pipeline wraps that in a formal protocol so any separation engine can be substituted without changing the downstream pipeline. The original `separation.py` is left untouched until the new adapter is verified.

**Objective:**
Define the `SeparationEngine` protocol, `SeparationConfig`, `StemResult`, and `SeparationResult` data models.

**Technical Specifications:**

`SeparationConfig(BaseModel)` — Pydantic v2:
- `profile: Literal["fast", "standard", "vocal_focus", "max_quality", "cpu_only"] = "standard"`
- `requested_stems: list[str] = []` — empty = all stems the engine supports; validated: each must be in `STEM_ROLES`
- `output_sample_rate: int = 44100` — WAV output SR (preserve original quality)
- `device: str = "cpu"` — `"cpu"` or `"cuda"`
- `two_stems: str | None = None` — optional two-stem mode (e.g. `"vocals"` → vocals vs everything else)

`SEPARATION_PROFILE_MATRIX: dict` — module-level constant:
```python
SEPARATION_PROFILE_MATRIX = {
    "fast":        {"engine": "demucs", "model": "htdemucs",    "stems": ["vocals","bass","drums","other"],                         "data_cost_mb": 80},
    "standard":    {"engine": "demucs", "model": "htdemucs_6s", "stems": ["vocals","bass","drums","guitar","piano","other"],        "data_cost_mb": 80},
    "vocal_focus": {"engine": "demucs", "model": "mdx_extra",   "stems": ["vocals","bass","drums","other"],                        "data_cost_mb": 83},
    "max_quality": {"engine": "demucs", "model": "htdemucs_6s", "stems": ["vocals","bass","drums","guitar","piano","other"],        "data_cost_mb": 400, "ensemble": True, "warn": "~400 MB download. Use on unmetered connection."},
    "cpu_only":    {"engine": "spleeter","model": "spleeter:4stems","stems": ["vocals","bass","drums","other"],                     "data_cost_mb": 150},
}
```

`StemResult(BaseModel)`:
- `stem_name: str`
- `file_path: str` — relative path inside song directory
- `status: Literal["ok", "failed", "missing"] = "ok"`
- `error: str | None = None`
- `duration_s: float | None = None`
- `sample_rate: int | None = None`
- `channels: int | None = None`

`SeparationResult(BaseModel)`:
- `engine: str`
- `model: str`
- `profile: str`
- `source_hash: str`
- `stems: dict[str, StemResult]` — keyed by stem name
- `completed_at: str | None = None`
- `warnings: list[str] = []`

`STEM_FALLBACK_MAP: dict[str, str]` — when a requested stem is not produced by the engine:
```python
STEM_FALLBACK_MAP = {
    "guitar": "other",
    "piano":  "other",
}
```

`SeparationEngine` Protocol:
```python
@runtime_checkable
class SeparationEngine(Protocol):
    def supports_stems(self) -> list[str]: ...
    def separate(self, audio_path: str | Path, output_dir: Path, config: SeparationConfig) -> SeparationResult: ...
    def health_check(self) -> bool: ...
    def model_info(self) -> dict: ...
```

**Execution Constraints:**
- Pydantic v2 only
- Import `STEM_ROLES` from `backend.schema.units`
- `SEPARATION_PROFILE_MATRIX` is a module-level constant — not built at call time
- `SeparationEngine` uses `@runtime_checkable` so `isinstance()` checks work in tests
- Both `__init__.py` files are empty
- Do not import any engine adapter here

**Output Request:**
Return `backend/separation/engine.py`, `backend/separation/__init__.py`, `backend/separation/engines/__init__.py`.

---

### [P03-B] Create `backend/separation/validation.py` — Stem Validation

**Target File:** `backend/separation/validation.py`

**Context:** After any separation run (Colab or local), MWTN validates every output stem before marking the job complete. Validation must catch: missing files, corrupt audio, duration mismatches, and wrong sample rates — all of which would cause silent failures downstream in transcription.

**Objective:**
Create a stem validation module used by every separation engine adapter after it produces output.

**Technical Specifications:**

```python
DURATION_TOLERANCE_S = 0.5      # stems must be within 500ms of source duration
MIN_STEM_DURATION_S = 0.1       # shorter than this is considered a failed stem
```

`StemValidationError` — simple exception class, subclass of `ValueError`.

`validate_stem(stem_path: Path, source_duration_s: float, stem_name: str) -> StemResult`:
- If `stem_path` does not exist → return `StemResult(stem_name=stem_name, file_path=str(stem_path), status="missing", error="File not found")`
- Try `soundfile.info(stem_path)`:
  - On `soundfile.SoundFileError` → return `StemResult(..., status="failed", error=f"Cannot decode audio: {e}")`
- Extract: `duration_s = info.frames / info.samplerate`, `sample_rate = info.samplerate`, `channels = info.channels`
- If `duration_s < MIN_STEM_DURATION_S` → `status="failed"`, error `"Stem duration too short"`
- If `abs(duration_s - source_duration_s) > DURATION_TOLERANCE_S` → `status="failed"`, error `f"Duration mismatch: stem={duration_s:.2f}s, source={source_duration_s:.2f}s"`
- On all checks pass → return `StemResult(stem_name=stem_name, file_path=str(stem_path), status="ok", duration_s=duration_s, sample_rate=sample_rate, channels=channels)`

`validate_all_stems(stems_dir: Path, expected_stems: list[str], source_duration_s: float) -> dict[str, StemResult]`:
- For each stem name in `expected_stems`:
  - Call `validate_stem(stems_dir / f"{stem}.wav", source_duration_s, stem)`
- Return dict keyed by stem name
- Never raise — always return a result dict even if every stem failed

`compute_source_hash(audio_path: Path, chunk_size: int = 65536) -> str`:
- SHA256 of the file contents, read in `chunk_size` byte chunks
- Return the hex digest (full 64-char string)

`get_source_duration(audio_path: Path) -> float`:
- Use `soundfile.info(audio_path)` to get duration without loading audio into memory
- Return `info.frames / info.samplerate`
- On error: raise `ValueError(f"Cannot read source audio: {audio_path}")`

**Execution Constraints:**
- Use `soundfile.info()` — never `soundfile.read()` for validation (avoids loading large files into RAM)
- Every function returns a result or raises explicitly — no silent failures
- The `compute_source_hash` function reads the file in chunks to handle large audio without memory pressure
- Do not import any separation engine

**Output Request:**
Return ONLY `backend/separation/validation.py`.

---

### [P03-C] Create `backend/separation/engines/demucs.py` — Demucs Engine Adapter

**Target File:** `backend/separation/engines/demucs.py`

**Context:** MWTN already uses Demucs (`htdemucs_6s`) for separation. The existing logic lives in `backend/separation.py`. This adapter wraps the same underlying `demucs` library calls but conforms to the new `SeparationEngine` protocol, supports multiple profiles/models, records metadata to the manifest, and validates output. The original `separation.py` remains untouched.

**Objective:**
Implement the Demucs engine adapter supporting all Demucs-based profiles: `fast`, `standard`, `vocal_focus`, and `max_quality`.

**Technical Specifications:**

`DEMUCS_MODEL_MAP: dict[str, str]` — maps profile to Demucs model name:
```python
DEMUCS_MODEL_MAP = {
    "fast":        "htdemucs",
    "standard":    "htdemucs_6s",
    "vocal_focus": "mdx_extra",
    "max_quality": "htdemucs_6s",  # + ensemble flag
}
```

`DemucsEngine` class:

`supports_stems(config: SeparationConfig) -> list[str]`:
```python
profile_stems = SEPARATION_PROFILE_MATRIX.get(config.profile, {}).get("stems", [])
return profile_stems
```

`health_check() -> bool`:
```python
try:
    import demucs
    return True
except ImportError:
    return False
```

`model_info() -> dict`:
```python
import demucs
return {
    "engine": "demucs",
    "version": demucs.__version__,
    "license": "MIT",
    "developer": "Meta AI Research",
    "models_available": list(DEMUCS_MODEL_MAP.values()),
}
```

`separate(audio_path, output_dir, config) -> SeparationResult`:

1. Guard: `if not self.health_check()`: raise `ImportError("demucs not installed")`
2. Get model name from `DEMUCS_MODEL_MAP[config.profile]`; default to `"htdemucs_6s"` if profile not in map
3. `is_ensemble = SEPARATION_PROFILE_MATRIX.get(config.profile, {}).get("ensemble", False)`
4. Compute `source_hash = compute_source_hash(audio_path)` and `source_duration_s = get_source_duration(audio_path)`
5. Build the `demucs` CLI command (Demucs is best invoked via subprocess for isolation):
   ```python
   import subprocess
   cmd = [
       "python", "-m", "demucs",
       "--name", model_name,
       "--out", str(output_dir / "demucs_raw"),
       "--mp3" if str(audio_path).endswith(".mp3") else "--wav",
   ]
   if config.device == "cuda":
       cmd += ["--device", "cuda"]
   if is_ensemble:
       cmd += ["--two-stems"]  # not correct for ensemble; see note below
   cmd.append(str(audio_path))
   ```
   > **Note to agent:** Demucs ensemble mode uses `--model` with multiple model names separated by commas in some versions, or the `BagOfModels` Python API. Use `subprocess` with `["python", "-m", "demucs", "--name", model_name, ...]`. For `max_quality`, add a comment: `# TODO: implement BagOfModels ensemble in v2` and fall through to single-model run.
6. Run: `result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)`
7. If `result.returncode != 0`: raise `RuntimeError(f"Demucs failed:\n{result.stderr}")`
8. Demucs outputs to `output_dir/demucs_raw/<model_name>/<audio_filename_stem>/`. Find the output directory:
   ```python
   audio_stem = Path(audio_path).stem
   demucs_out = output_dir / "demucs_raw" / model_name / audio_stem
   ```
9. Copy and rename stems to the canonical layout (`output_dir / f"{stem}.wav"`):
   - Demucs outputs `vocals.wav`, `bass.wav`, `drums.wav`, `other.wav` (and `guitar.wav`, `piano.wav` for 6s)
   - Copy each to `output_dir / "<stem>.wav"` using `shutil.copy2`
   - If a stem file doesn't exist in Demucs output (e.g. `guitar.wav` when using `htdemucs` 4-stem): note it as missing — do not crash
10. Validate stems: `stem_results = validate_all_stems(output_dir, expected_stems, source_duration_s)`
11. Build and return `SeparationResult`:
    ```python
    SeparationResult(
        engine="demucs",
        model=model_name,
        profile=config.profile,
        source_hash=source_hash,
        stems=stem_results,
        completed_at=datetime.utcnow().isoformat() + "Z",
        warnings=[] if not is_ensemble else ["max_quality ensemble not yet implemented; used single model"],
    )
    ```

**Execution Constraints:**
- Use `subprocess` with `shell=False` and a list — never `shell=True`
- `import demucs` and all demucs imports must be inside `health_check()` and `separate()` — not at module top level
- `shutil`, `subprocess`, `datetime`, `Path` can be at module top level
- Import `SeparationEngine`, `SeparationConfig`, `SeparationResult` from `backend.separation.engine`
- Import `validate_all_stems`, `compute_source_hash`, `get_source_duration` from `backend.separation.validation`
- Import `SEPARATION_PROFILE_MATRIX` from `backend.separation.engine`
- Do not modify `backend/separation.py`

**Output Request:**
Return ONLY `backend/separation/engines/demucs.py`.

---

### [P03-D] Create `backend/separation/engines/spleeter.py` and `backend/separation/engines/openunmix.py` — Optional Fallback Engines

**Target Files:** `backend/separation/engines/spleeter.py`, `backend/separation/engines/openunmix.py`

**Context:** Two optional fallback engines for environments where Demucs is unavailable or too slow. Spleeter (Deezer, MIT) is the CPU-optimized fallback. Open-Unmix (Inria, MIT) is the alternative fallback with better quality than Spleeter. Both are optional — the dispatcher checks availability before calling them. Neither is activated by default.

**Objective:**
Implement both optional fallback engine adapters with the same `SeparationEngine` interface as the Demucs adapter.

**Technical Specifications:**

**`SpleeterEngine` in `spleeter.py`:**

Spleeter stem names for 4stems: `vocals`, `bass`, `drums`, `other` (it uses `accompaniment` for 2stems — map `accompaniment` → `other`)

`supports_stems()` → `["vocals", "bass", "drums", "other"]`

`health_check()`:
```python
try:
    import spleeter
    return True
except ImportError:
    return False
```

`model_info()`:
```python
return {
    "engine": "spleeter",
    "license": "MIT",
    "developer": "Deezer Research",
    "quality_note": "Lower quality than Demucs. Use for CPU-only environments.",
    "data_cost_mb": 150,
}
```

`separate(audio_path, output_dir, config)`:
1. Guard on `health_check()`
2. Lazy imports: `from spleeter.separator import Separator`
3. Determine config: `"spleeter:4stems"` for profile `cpu_only`; map any other profile to `"spleeter:4stems"` with a warning
4. Invoke via CLI (more reliable than Python API for Spleeter):
   ```python
   cmd = [
       "spleeter", "separate",
       "-p", "spleeter:4stems",
       "-o", str(output_dir / "spleeter_raw"),
       str(audio_path),
   ]
   result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
   ```
5. Spleeter outputs to `output_dir/spleeter_raw/<audio_stem>/`. Find and copy to canonical layout
6. Map Spleeter stem names to canonical names: `vocals→vocals`, `bass→bass`, `drums→drums`, `other→other`
7. Validate and return `SeparationResult`

**`OpenUnmixEngine` in `openunmix.py`:**

`supports_stems()` → `["vocals", "bass", "drums", "other"]`

`health_check()`:
```python
try:
    import openunmix
    return True
except ImportError:
    return False
```

`model_info()`:
```python
return {
    "engine": "openunmix",
    "license": "MIT",
    "developer": "Fabian-Robert Stöter / Inria",
    "quality_note": "Good quality. Slightly below Demucs.",
    "data_cost_mb": 70,
}
```

`separate(audio_path, output_dir, config)`:
1. Guard on `health_check()`
2. Open-Unmix is invoked as a Python API:
   ```python
   import openunmix
   import torch
   import soundfile as sf
   import numpy as np

   audio, rate = sf.read(str(audio_path), always_2d=True)
   audio_tensor = torch.tensor(audio.T, dtype=torch.float32).unsqueeze(0)  # (1, channels, samples)

   separator = openunmix.umx(targets=["vocals", "bass", "drums", "other"], device=config.device)
   estimates = separator(audio_tensor)
   # estimates: dict of target → (1, channels, samples) tensor
   ```
3. Write each separated tensor to `output_dir / f"{stem}.wav"`:
   ```python
   for stem_name, tensor in estimates.items():
       audio_np = tensor.squeeze(0).numpy().T  # (samples, channels)
       sf.write(str(output_dir / f"{stem_name}.wav"), audio_np, rate)
   ```
4. Validate and return `SeparationResult`

**Shared execution constraints for both engines:**
- All library imports are lazy (inside `health_check` and `separate`)
- `subprocess`, `shutil`, `Path`, `datetime` can be at module top level
- Use `shell=False` and list args for all subprocess calls
- Import protocol/models from `backend.separation.engine` and `backend.separation.validation`
- On any inference failure: raise `RuntimeError` with a clear message including the engine name

**Output Request:**
Return BOTH files: `backend/separation/engines/spleeter.py` and `backend/separation/engines/openunmix.py`.

---

### [P03-E] Create `backend/separation/dispatcher.py` — Separation Job Orchestration

**Target File:** `backend/separation/dispatcher.py`

**Context:** The separation dispatcher selects the correct engine for a given profile, manages job state, handles caching via source hash, runs validation, writes separation metadata to the song manifest, and optionally triggers AMT preprocessing copies. It is the only entry point for all separation work in the backend.

**Objective:**
Create the separation dispatcher with engine selection, source-hash caching, job state tracking, manifest update, and optional AMT preprocessing.

**Technical Specifications:**

**Engine selection:**
```python
def _select_engine(profile: str) -> SeparationEngine | None:
    """Select and instantiate the engine for a profile. Returns None if unavailable."""
    engine_name = SEPARATION_PROFILE_MATRIX.get(profile, {}).get("engine", "demucs")
    if engine_name == "demucs":
        from backend.separation.engines.demucs import DemucsEngine
        e = DemucsEngine()
    elif engine_name == "spleeter":
        from backend.separation.engines.spleeter import SpleeterEngine
        e = SpleeterEngine()
    elif engine_name == "openunmix":
        from backend.separation.engines.openunmix import OpenUnmixEngine
        e = OpenUnmixEngine()
    else:
        return None
    return e if e.health_check() else None
```

**Fallback chain:**
```python
PROFILE_FALLBACK: dict[str, str] = {
    "fast":        "standard",
    "max_quality": "standard",
    "vocal_focus": "standard",
    "cpu_only":    "fast",
}
```
If `_select_engine(profile)` returns `None`, try the fallback profile. If that also fails, try `"standard"` (Demucs). If all fail, raise `RuntimeError("No separation engine available")`.

**In-memory job state:**
```python
_SEP_JOB_STATE: dict[str, dict] = {}
```

**Main function:**
```python
def separate_audio(
    audio_path: Path,
    song_dir: Path,
    song_id: str,
    config: SeparationConfig,
    job_id: str | None = None,
) -> SeparationResult:
```

Steps inside `separate_audio`:
1. `job_id = job_id or uuid.uuid4().hex`
2. Set state: `status="queued"`
3. Compute `source_hash = compute_source_hash(audio_path)` and `source_duration_s`
4. **Cache check:** Look in `song_dir / "stems"` — if stems exist AND `manifest.json` records matching `source_hash` → validate existing stems; if valid, return early with `cached=True` in result warnings
5. Set state: `status="separating"`
6. Ensure `stems_dir = song_dir / "stems"` and `source_dir = song_dir / "source"` exist
7. Copy source audio to `source_dir / f"original{Path(audio_path).suffix}"`
8. Select engine with fallback
9. Warn if `config.profile == "max_quality"`: append `SEPARATION_PROFILE_MATRIX["max_quality"]["warn"]` to a warnings list
10. Run: `result = engine.separate(audio_path, stems_dir, config)`
11. Set state: `status="validating"`
12. Validate result: any stem with `status != "ok"` → append to warnings
13. Set state: `status="complete"` or `"failed"` (if ALL stems failed)
14. Update `manifest.json` via `SongManifest`:
    ```python
    manifest_path = song_dir / "manifest.json"
    if manifest_path.exists():
        manifest = SongManifest.from_file(manifest_path)
    else:
        manifest = SongManifest(song_id=song_id, title=song_id, stems=[])
    manifest.separation_engine = SeparationEngineInfo(
        name=result.engine,
        model=result.model,
        profile=result.profile,
    )
    manifest.stems = [s for s, r in result.stems.items() if r.status == "ok"]
    manifest.updated_at = datetime.utcnow().isoformat() + "Z"
    manifest.to_file(manifest_path)
    ```
15. Return `result`

**AMT preprocessing (optional):**
```python
def prepare_for_transcription(
    stems_dir: Path,
    song_dir: Path,
    stem_names: list[str],
    target_sr: int = 22050,
) -> dict[str, Path]:
    """
    Create mono 22050Hz copies of stems for AMT engines.
    Writes to song_dir/stems_for_transcription/<stem>_preproc.wav.
    Returns dict of stem_name → preproc_path.
    """
```
Use `librosa.resample` if SR differs. Convert to mono by averaging channels. Write with `soundfile.write`.

**Status query:**
```python
def get_separation_status(job_id: str) -> dict:
    return _SEP_JOB_STATE.get(job_id, {"status": "not_found"})
```

**Execution Constraints:**
- All engine imports are lazy (inside `_select_engine`)
- Manifest update uses `SongManifest.from_file` + `to_file` (atomic write from Plan 01)
- Cache check uses `source_hash` comparison against manifest — not file timestamps
- `prepare_for_transcription` never modifies files in `stems_dir` — writes only to `stems_for_transcription/`
- `stems_dir` is passed directly to the engine as `output_dir` — engines write stems there directly

**Output Request:**
Return ONLY `backend/separation/dispatcher.py`.

---

### [P03-F] Wire Separation into `backend/main.py` and Update Tests

**Target Files:** `backend/main.py` (additive), `tests/unit/test_separation_validation.py`

**Context:** Plan 03's last step is two additive changes: new endpoints in `main.py` for triggering and monitoring separation jobs, and unit tests for the validation module which has no external dependencies and runs cleanly in CI.

**Objective:**
Add separation endpoints to `main.py` (additive only) and create unit tests for `backend/separation/validation.py`.

**Technical Specifications:**

**New endpoint 1 — `POST /api/songs/{song_id}/separate`:**
```python
@app.post("/api/songs/{song_id}/separate")
async def start_separation(song_id: str, body: dict):
    """
    Trigger separation for an already-imported song (re-separate with a new profile).
    Body: { "profile": "fast" | "standard" | "vocal_focus" | "max_quality" | "cpu_only" }
    Returns: { "job_id": str, "status": "queued", "data_cost_warning": str | null }
    """
    song_id = validate_song_id(song_id)
    profile = body.get("profile", "standard")

    if profile not in SEPARATION_PROFILE_MATRIX:
        raise HTTPException(400, detail=f"Unknown separation profile: {profile!r}. Valid: {list(SEPARATION_PROFILE_MATRIX)}")

    source_dir = DATA_DIR / song_id / "source"
    source_files = list(source_dir.glob("original.*")) if source_dir.exists() else []
    if not source_files:
        raise HTTPException(404, detail=f"No source audio found for song {song_id!r}. Import the song first.")

    audio_path = source_files[0]
    job_id = uuid.uuid4().hex
    warning = SEPARATION_PROFILE_MATRIX.get(profile, {}).get("warn")

    config = SeparationConfig(profile=profile)

    def _run():
        try:
            separate_audio(audio_path, DATA_DIR / song_id, song_id, config, job_id)
        except Exception as e:
            _SEP_JOB_STATE[job_id] = {"status": "failed", "error": str(e)}

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id, "status": "queued", "profile": profile, "data_cost_warning": warning}
```

**New endpoint 2 — `GET /api/songs/{song_id}/separation/status`:**
```python
@app.get("/api/songs/{song_id}/separation/status")
async def separation_status(song_id: str):
    song_id = validate_song_id(song_id)
    # Return most recent job for this song from _SEP_JOB_STATE
    # (v1: return all jobs for song_id, client picks latest)
    jobs = {jid: state for jid, state in _SEP_JOB_STATE.items() if state.get("song_id") == song_id}
    if not jobs:
        raise HTTPException(404, detail=f"No separation jobs found for song {song_id!r}")
    return jobs
```

**New endpoint 3 — `GET /api/separation/profiles`:**
```python
@app.get("/api/separation/profiles")
async def list_separation_profiles():
    """Return all available separation profiles with metadata."""
    return SEPARATION_PROFILE_MATRIX
```

**Required new imports for `main.py`:**
```python
from backend.separation.engine import SeparationConfig, SEPARATION_PROFILE_MATRIX
from backend.separation.dispatcher import separate_audio, get_separation_status, _SEP_JOB_STATE
```

---

**`tests/unit/test_separation_validation.py`:**

```python
pytestmark = pytest.mark.unit
```

Tests:

**`TestComputeSourceHash`**:
- `test_hash_is_deterministic(tmp_path)` — write the same bytes twice to two files → same hash
- `test_hash_differs_for_different_content(tmp_path)` — different file content → different hash
- `test_hash_is_64_hex_chars(tmp_path)` — output is a 64-char hex string

**`TestGetSourceDuration`**:
- `test_duration_from_real_wav(c_major_scale_path)` — duration ≈ 4.0s (8 notes × 0.5s); assert `3.8 < duration < 4.2`
- `test_duration_from_silence(silence_path)` — ≈ 5.0s
- `test_missing_file_raises(tmp_path)` — non-existent path → `ValueError`

**`TestValidateStem`**:
- `test_valid_stem_returns_ok(c_major_scale_path, tmp_path)`:
  - Copy `c_major_scale.wav` to `tmp_path / "vocals.wav"`
  - `result = validate_stem(tmp_path / "vocals.wav", source_duration_s=4.0, stem_name="vocals")`
  - `assert result.status == "ok"`
  - `assert result.duration_s is not None`
  - `assert result.sample_rate == 22050`

- `test_missing_file_returns_missing(tmp_path)`:
  - `result = validate_stem(tmp_path / "does_not_exist.wav", 4.0, "vocals")`
  - `assert result.status == "missing"`

- `test_duration_mismatch_returns_failed(c_major_scale_path, tmp_path)`:
  - Copy to `tmp_path / "vocals.wav"`
  - Call with `source_duration_s=60.0` (way off from 4.0s actual)
  - `assert result.status == "failed"`
  - `assert "Duration mismatch" in result.error`

- `test_corrupt_file_returns_failed(tmp_path)`:
  - Write `b"not audio data"` to `tmp_path / "corrupt.wav"`
  - `result = validate_stem(tmp_path / "corrupt.wav", 4.0, "corrupt")`
  - `assert result.status == "failed"`

**`TestValidateAllStems`**:
- `test_all_valid(c_major_scale_path, tmp_path)`:
  - Copy `c_major_scale.wav` to `tmp_path / "vocals.wav"` and `tmp_path / "bass.wav"`
  - `results = validate_all_stems(tmp_path, ["vocals", "bass"], 4.0)`
  - `assert all(r.status == "ok" for r in results.values())`

- `test_partial_failure_does_not_raise(tmp_path)`:
  - Only `vocals.wav` exists; `bass.wav` does not
  - `results = validate_all_stems(tmp_path, ["vocals", "bass"], 4.0)`
  - `assert results["bass"].status == "missing"`
  - `assert results["vocals"].status in ("ok", "failed")` — depends on whether file is present

- `test_returns_dict_even_when_all_fail(tmp_path)`:
  - No files at all
  - `results = validate_all_stems(tmp_path, ["vocals", "bass", "drums"], 4.0)`
  - `assert len(results) == 3`
  - `assert all(r.status == "missing" for r in results.values())`

**Execution Constraints for all `main.py` changes:**
- Additive only — do not modify existing routes
- `_SEP_JOB_STATE` is imported from `dispatcher.py`; use it directly for status lookups
- `threading` and `uuid` are already imported after Plan 02-H

**Output Request:**
Return the three new endpoint functions as labeled code blocks (not the full `main.py`), the required imports, and the complete `tests/unit/test_separation_validation.py` file.
