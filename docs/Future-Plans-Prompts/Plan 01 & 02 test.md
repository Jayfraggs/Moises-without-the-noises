Good. Generating tests for Plans 01 and 02, then Plan 03 prompts immediately after.

### [T01-A] Create `tests/conftest.py` and `tests/fixtures/generate_fixtures.py` — Shared Infrastructure

**Target Files:** `tests/conftest.py`, `tests/fixtures/generate_fixtures.py`, `tests/fixtures/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`

**Context:** MWTN is adding a test suite for its new schema layer (`backend/schema/`) and AMT transcription engine (`backend/transcription/`). Tests use pytest. All audio fixtures are synthetically generated — no real songs, no licensing issues. Fixtures are written to disk once and reused across the full test suite.

**Objective:**
Create the test infrastructure: shared pytest fixtures in `conftest.py` and a standalone script that generates all synthetic WAV files needed by both unit and integration tests.

**Technical Specifications:**

**`tests/fixtures/generate_fixtures.py`** — runnable standalone (`python tests/fixtures/generate_fixtures.py`):

```python
"""
Run this script once to generate all synthetic test audio fixtures.
Requires: numpy, soundfile
No models or network access needed.
"""
```

Implement these generator functions:

```python
def generate_sine_note(freq_hz: float, duration_s: float, sr: int = 22050) -> np.ndarray:
    """Pure sine wave at freq_hz for duration_s seconds."""
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    return 0.5 * np.sin(2 * np.pi * freq_hz * t)

def generate_silence(duration_s: float, sr: int = 22050) -> np.ndarray:
    return np.zeros(int(sr * duration_s))

def generate_white_noise(duration_s: float, sr: int = 22050, amplitude: float = 0.1) -> np.ndarray:
    return np.random.RandomState(42).randn(int(sr * duration_s)) * amplitude
```

Files to generate and write to `tests/fixtures/audio/`:

| Filename | Content | How to generate |
|---|---|---|
| `c_major_scale.wav` | C4 D4 E4 F4 G4 A4 B4 C5, each 0.5s, 120 BPM | 8 sine notes: 261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88, 523.25 Hz |
| `g_major_scale.wav` | G4 A4 B4 C5 D5 E5 F#5 G5, each 0.5s | 392.00, 440.00, 493.88, 523.25, 587.33, 659.25, 739.99, 783.99 Hz |
| `a_minor_scale.wav` | A4 B4 C5 D5 E5 F5 G5 A5, each 0.5s | 440.00, 493.88, 523.25, 587.33, 659.25, 698.46, 783.99, 880.00 Hz |
| `simple_melody.wav` | C4 E4 G4 E4 C4, each 0.5s | 261.63, 329.63, 392.00, 329.63, 261.63 Hz |
| `silence.wav` | 5s silence | `generate_silence(5.0)` |
| `noise.wav` | 3s white noise | `generate_white_noise(3.0)` |
| `major_triad.wav` | C4+E4+G4 simultaneously for 1s | Sum of three sine waves; normalize to peak -1 dBFS |
| `long_audio.wav` | C major scale repeated for 6 min 5s | Repeat `c_major_scale` audio 45 times + 1 extra scale |
| `single_note_a4.wav` | A4 (440 Hz) for 2s | Single sine note |

Also write ground truth JSON files to `tests/fixtures/ground_truth/`:

`c_major_scale.json`:
```json
{
  "file": "c_major_scale.wav",
  "sample_rate": 22050,
  "duration_s": 4.0,
  "expected_notes": [
    {"midi_pitch": 60, "start_time": 0.0, "end_time": 0.5, "frequency_hz": 261.63},
    {"midi_pitch": 62, "start_time": 0.5, "end_time": 1.0, "frequency_hz": 293.66},
    {"midi_pitch": 64, "start_time": 1.0, "end_time": 1.5, "frequency_hz": 329.63},
    {"midi_pitch": 65, "start_time": 1.5, "end_time": 2.0, "frequency_hz": 349.23},
    {"midi_pitch": 67, "start_time": 2.0, "end_time": 2.5, "frequency_hz": 392.00},
    {"midi_pitch": 69, "start_time": 2.5, "end_time": 3.0, "frequency_hz": 440.00},
    {"midi_pitch": 71, "start_time": 3.0, "end_time": 3.5, "frequency_hz": 493.88},
    {"midi_pitch": 72, "start_time": 3.5, "end_time": 4.0, "frequency_hz": 523.25}
  ],
  "expected_key": {"tonic": "C", "mode": "major"},
  "expected_tempo": 120.0,
  "expected_solfa": ["Do", "Re", "Mi", "Fa", "Sol", "La", "Ti", "Do"]
}
```

`simple_melody.json`:
```json
{
  "file": "simple_melody.wav",
  "expected_notes": [
    {"midi_pitch": 60, "start_time": 0.0, "end_time": 0.5},
    {"midi_pitch": 64, "start_time": 0.5, "end_time": 1.0},
    {"midi_pitch": 67, "start_time": 1.0, "end_time": 1.5},
    {"midi_pitch": 64, "start_time": 1.5, "end_time": 2.0},
    {"midi_pitch": 60, "start_time": 2.0, "end_time": 2.5}
  ],
  "expected_key": {"tonic": "C", "mode": "major"},
  "expected_solfa": ["Do", "Mi", "Sol", "Mi", "Do"]
}
```

`major_triad.json`:
```json
{
  "file": "major_triad.wav",
  "expected_notes": [
    {"midi_pitch": 60},
    {"midi_pitch": 64},
    {"midi_pitch": 67}
  ],
  "note_count": 3,
  "polyphonic": true
}
```

At the bottom of `generate_fixtures.py`, add:
```python
if __name__ == "__main__":
    generate_all()
    print("All fixtures generated successfully.")
    print(f"Audio files: tests/fixtures/audio/")
    print(f"Ground truth: tests/fixtures/ground_truth/")
```

**`tests/conftest.py`** — shared pytest fixtures:

```python
import pytest
from pathlib import Path
import json

FIXTURES_DIR = Path(__file__).parent / "fixtures"
AUDIO_DIR = FIXTURES_DIR / "audio"
GROUND_TRUTH_DIR = FIXTURES_DIR / "ground_truth"

@pytest.fixture(scope="session", autouse=True)
def ensure_fixtures():
    """Generate fixtures if they don't exist yet."""
    if not AUDIO_DIR.exists() or not list(AUDIO_DIR.glob("*.wav")):
        from tests.fixtures.generate_fixtures import generate_all
        generate_all()

@pytest.fixture
def audio_dir():
    return AUDIO_DIR

@pytest.fixture
def c_major_scale_path():
    return AUDIO_DIR / "c_major_scale.wav"

@pytest.fixture
def silence_path():
    return AUDIO_DIR / "silence.wav"

@pytest.fixture
def noise_path():
    return AUDIO_DIR / "noise.wav"

@pytest.fixture
def major_triad_path():
    return AUDIO_DIR / "major_triad.wav"

@pytest.fixture
def long_audio_path():
    return AUDIO_DIR / "long_audio.wav"

@pytest.fixture
def ground_truth(request):
    """Load ground truth JSON by filename stem."""
    name = request.param
    path = GROUND_TRUTH_DIR / f"{name}.json"
    return json.loads(path.read_text())

@pytest.fixture
def tmp_song_dir(tmp_path):
    """Temporary directory mimicking backend/data/<song_id>/."""
    song_dir = tmp_path / "test_song_001"
    (song_dir / "stems").mkdir(parents=True)
    (song_dir / "transcription_cache").mkdir()
    return song_dir
```

**Execution Constraints:**
- `generate_fixtures.py` must run in isolation with only `numpy` and `soundfile` — no backend imports
- All paths use `Path` objects — no string concatenation
- `ensure_fixtures` is `scope="session"` and `autouse=True` so it runs exactly once per test run
- Directories are created with `mkdir(parents=True, exist_ok=True)`
- All `__init__.py` files are empty

**Output Request:**
Return all five files: `tests/conftest.py`, `tests/fixtures/generate_fixtures.py`, `tests/fixtures/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`.

---

### [T01-B] Create `tests/unit/test_schema.py` — Schema Layer Unit Tests

**Target File:** `tests/unit/test_schema.py`

**Context:** Tests for `backend/schema/units.py`, `backend/schema/events.py`, `backend/schema/manifest.py`, `backend/schema/migrations.py`, and `backend/schema/validation.py`. No audio, no models, no filesystem (except `SongManifest.from_file` which uses `tmp_path`). Pure logic validation.

**Objective:**
Comprehensive unit tests for all five schema modules.

**Technical Specifications:**

Implement the following test classes and their test methods:

**`TestUnits`** — tests for `backend.schema.units`:
- `test_midi_pitch_range_valid` — `MIDI_PITCH_MIN == 0`, `MIDI_PITCH_MAX == 127`
- `test_confidence_range` — `CONFIDENCE_MIN == 0.0`, `CONFIDENCE_MAX == 1.0`
- `test_ppq_standard` — `MIDI_PPQ == 480`
- `test_schema_version_is_string` — `SCHEMA_VERSION` is a non-empty string
- `test_stem_roles_contains_expected` — `"vocals"`, `"bass"`, `"drums"`, `"guitar"`, `"piano"`, `"other"` all in `STEM_ROLES`
- `test_event_types_contains_expected` — `"note"`, `"rest"`, `"chord"`, `"beat"`, `"key"` all in `EVENT_TYPES`

**`TestMusicalEventBase`** — tests for `MusicalEventBase` and its subclasses:
- `test_note_event_construction_valid` — build a valid `NoteEvent`; assert fields match
- `test_note_event_midi_pitch_clamp_low` — `midi_pitch=-1` → `ValidationError`
- `test_note_event_midi_pitch_clamp_high` — `midi_pitch=128` → `ValidationError`
- `test_note_event_end_before_start` — `end_time < start_time` → `ValidationError`
- `test_confidence_above_1` — `confidence=1.5` → `ValidationError`
- `test_confidence_below_0` — `confidence=-0.1` → `ValidationError`
- `test_event_id_auto_generated` — two `NoteEvent` instances have different `event_id` values
- `test_rest_event_construction` — valid `RestEvent`; duration_s > 0
- `test_chord_event_construction` — valid `ChordEvent` with root and quality
- `test_drum_hit_event_construction` — valid `DrumHitEvent` with known drum_type
- `test_beat_event_construction` — valid `BeatEvent`; `beat_number=1`, `is_downbeat=True`
- `test_key_event_construction` — valid `KeyEvent`; tonic="C", mode="major"
- `test_extra_fields_allowed` — construct a `NoteEvent` with an unknown extra field; it must not raise (ConfigDict extra="allow")
- `test_source_model_required` — constructing `NoteEvent` without `source_model` → `ValidationError`
- `test_schema_version_default` — `NoteEvent` without explicit `schema_version` gets `units.SCHEMA_VERSION`

**`TestSongManifest`** — tests for `SongManifest`:
- `test_minimal_manifest_parses` — build from a dict with only existing required fields (song_id, title, stems, etc.); no new fields required
- `test_new_fields_have_safe_defaults` — `schema_version`, `transcription_runs`, `artifacts` all present with safe defaults
- `test_extra_fields_tolerated` — dict with an unknown field (e.g. `"legacy_custom_field": "x"`) must parse without error
- `test_from_file_roundtrip(tmp_path)` — write a manifest dict to a JSON file; `SongManifest.from_file()` must parse it; `to_file()` must write it back; re-read and compare `song_id`
- `test_to_file_atomic(tmp_path)` — after `to_file()`, no `.tmp` file should remain on disk
- `test_from_file_missing_raises(tmp_path)` — `from_file()` on a non-existent path → `FileNotFoundError`
- `test_from_file_invalid_json_raises(tmp_path)` — file containing `"{{not json"` → raises (either `json.JSONDecodeError` or `ValidationError`)

**`TestMigrations`** — tests for `backend.schema.migrations`:
- `test_migrate_legacy_notes_basic` — feed a list of legacy note dicts; assert output is `list[NoteEvent]`; assert `start_time`, `midi_pitch`, `confidence` preserved correctly
- `test_migrate_legacy_notes_empty_list` — `[]` → `[]` (no crash)
- `test_migrate_legacy_beats_basic` — feed legacy beats dict; assert first element is a `BeatEvent`; assert all `start_time` values match beat timestamps
- `test_migrate_legacy_key_major` — `{"key": "C major", "confidence": 0.83}` → `KeyEvent(tonic="C", mode="major", confidence=0.83)`
- `test_migrate_legacy_key_minor` — `{"key": "F# minor", "confidence": 0.71}` → `KeyEvent(tonic="F#", mode="minor")`
- `test_migrate_legacy_lyrics_basic` — feed Whisper-format dict; assert output is `list[LyricEvent]`; assert word text and timestamps preserved
- `test_check_schema_version_returns_current` — dict with `"schema_version": "1.0"` → returns `"1.0"`
- `test_check_schema_version_missing` — `{"midi_pitch": 60, "time": 1.0}` → returns a legacy string (not a crash)
- `test_migrate_events_dispatcher_notes` — `migrate_events(legacy_notes_list, "notes", "vocals")` → returns `list[NoteEvent]`

**`TestValidation`** — tests for `backend.schema.validation`:
- `test_validate_song_id_valid` — `"abc-123_XYZ"` passes; returns unchanged
- `test_validate_song_id_path_traversal` — `"../evil"` → `HTTPException(400)`
- `test_validate_song_id_too_long` — 65-char string → `HTTPException(400)`
- `test_validate_song_id_empty` — `""` → `HTTPException(400)`
- `test_validate_manifest_valid` — valid dict → `SongManifest` returned
- `test_validate_manifest_missing_required` — dict missing `song_id` → `HTTPException(422)`
- `test_validate_schema_version_supported` — `{"schema_version": "1.0"}` → returns `"1.0"`
- `test_validate_schema_version_unsupported` — `{"schema_version": "99.0"}` → `HTTPException(422)`
- `test_validate_schema_version_missing` — `{}` → returns `"legacy"` (not an error)
- `test_validate_note_event_patch_valid` — `{"midi_pitch": 64}` → passes, returns dict
- `test_validate_note_event_patch_invalid_pitch` — `{"midi_pitch": 200}` → `HTTPException(400)`
- `test_validate_note_event_patch_unknown_key` — `{"color": "red"}` → `HTTPException(400)`

**Execution Constraints:**
- No audio, no network, no filesystem access (except `tmp_path` tests)
- Import `HTTPException` from `fastapi`; catch it directly in tests
- Use `pytest.raises(ValidationError)` for Pydantic errors; `pytest.raises(HTTPException)` for API boundary errors
- No mocks — test real implementations only
- All test functions must have a single clear assertion chain; avoid multi-assertion sprawl

**Output Request:**
Return ONLY `tests/unit/test_schema.py`.

---

### [T01-C] Create `tests/unit/test_transcription_config.py` — Transcription Config Unit Tests

**Target File:** `tests/unit/test_transcription_config.py`

**Context:** Tests for `backend/transcription/config.py` — the `TranscriptionConfig` Pydantic model, `ENGINE_REGISTRY`, and `is_engine_available()`. No audio, no models installed. `is_engine_available` is tested with known-available modules (`librosa`) and known-absent ones.

**Objective:**
Unit tests for all public interfaces in `backend/transcription/config.py`.

**Technical Specifications:**

**`TestTranscriptionConfig`**:
- `test_default_construction` — `TranscriptionConfig(stem_type="vocals")` succeeds with all defaults
- `test_quality_profile_valid_values` — all three of `"fast"`, `"standard"`, `"high_quality"` are accepted
- `test_quality_profile_invalid` — `quality_profile="ultra"` → `ValidationError`
- `test_onset_threshold_range` — values outside [0.0, 1.0] raise `ValidationError`
- `test_config_hash_is_deterministic` — same config built twice → identical `config_hash`
- `test_config_hash_changes_with_config` — different `onset_threshold` → different `config_hash`
- `test_config_hash_excludes_device` — two configs identical except `device` → same `config_hash` (device doesn't affect cache key)
- `test_config_hash_excludes_source_model` — two configs identical except `source_model` → same `config_hash`
- `test_stem_type_must_be_stem_role` — `stem_type="theremin"` → `ValidationError` (validated against `STEM_ROLES`)
- `test_chunk_duration_positive` — `chunk_duration_s=0` → `ValidationError`
- `test_minimum_note_length_positive` — `minimum_note_length_ms=-10` → `ValidationError`

**`TestEngineRegistry`**:
- `test_registry_contains_all_expected_engines` — keys include `"pyin"`, `"basic_pitch"`, `"piano_kong"`, `"adtlib"`, `"mt3"`
- `test_pyin_is_not_polyphonic` — `ENGINE_REGISTRY["pyin"]["polyphonic"] == False`
- `test_basic_pitch_is_polyphonic` — `ENGINE_REGISTRY["basic_pitch"]["polyphonic"] == True`
- `test_mt3_is_disabled` — `ENGINE_REGISTRY["mt3"].get("enabled") == False`
- `test_all_entries_have_license_field` — every entry in `ENGINE_REGISTRY` has a `"license"` key
- `test_all_entries_have_data_cost` — every entry has a `"data_cost_mb"` key with an int or float value
- `test_pyin_has_zero_data_cost` — `ENGINE_REGISTRY["pyin"]["data_cost_mb"] == 0`

**`TestIsEngineAvailable`**:
- `test_pyin_available` — `is_engine_available("pyin")` → `True` (librosa is always installed in MWTN)
- `test_nonexistent_engine` — `is_engine_available("not_a_real_engine")` → `False`
- `test_never_raises` — calling `is_engine_available` with any string, including `None`-ish values like `""`, never raises; always returns `bool`
- `test_mt3_unavailable_by_default` — `is_engine_available("mt3")` → `False` (JAX not installed in MWTN standard env)

**Execution Constraints:**
- Do not install `basic_pitch`, `piano_kong`, or `adtlib` for these tests — test the unavailability path
- `is_engine_available("pyin")` must return `True` because `librosa` is a core MWTN dependency
- No mocking — test real availability checks

**Output Request:**
Return ONLY `tests/unit/test_transcription_config.py`.

---

### [T01-D] Create `tests/integration/test_transcription_pyin.py` — pYIN Engine Integration Tests

**Target File:** `tests/integration/test_transcription_pyin.py`

**Context:** Integration tests for the pYIN engine adapter (`backend/transcription/engines/pyin.py`). These tests use real synthetic audio from `tests/fixtures/audio/`. They do not require Colab or any optional model. pYIN is always available via librosa. Tests run in CI.

**Objective:**
Integration tests covering all acceptance criteria for the pYIN engine: correct note detection on clean audio, graceful handling of silence and noise, correct output types.

**Technical Specifications:**

All tests use the `conftest.py` fixtures. Mark the entire module:
```python
pytestmark = pytest.mark.integration
```

**`TestPYINEngineHealth`**:
- `test_health_check_passes` — `PYINEngine().health_check() == True`
- `test_model_info_shape` — `model_info()` returns dict with keys: `"engine"`, `"library"`, `"version"`, `"polyphonic"`
- `test_polyphonic_is_false` — `model_info()["polyphonic"] == False`
- `test_supports_vocals_fast` — `engine.supports("vocals", "fast") == True`
- `test_supports_bass_fast` — `engine.supports("bass", "fast") == True`
- `test_does_not_support_guitar` — `engine.supports("guitar", "fast") == False`
- `test_does_not_support_standard_profile` — `engine.supports("vocals", "standard") == False`

**`TestPYINTranscription`** — use `c_major_scale_path` and `silence_path` fixtures:

- `test_c_major_returns_note_events(c_major_scale_path)`:
  ```python
  config = TranscriptionConfig(stem_type="vocals", quality_profile="fast")
  events = PYINEngine().transcribe(str(c_major_scale_path), config)
  assert len(events) > 0
  assert all(isinstance(e, NoteEvent) for e in events)
  ```

- `test_c_major_note_count_approximate(c_major_scale_path)`:
  - The scale has 8 notes; pYIN may not detect all perfectly
  - Assert `5 <= len(events) <= 10` (loose bounds — pure sine is clean but pYIN has onset/offset heuristics)

- `test_c_major_pitches_are_in_range(c_major_scale_path)`:
  - All `note.midi_pitch` values must be in `[60, 72]` (C4 to C5 inclusive)

- `test_events_sorted_by_start_time(c_major_scale_path)`:
  - `start_times = [e.start_time for e in events]`
  - `assert start_times == sorted(start_times)`

- `test_all_events_have_required_fields(c_major_scale_path)`:
  - Every event has non-empty `source_model`, `track_id == "vocals"`, `confidence` in `[0.0, 1.0]`, `schema_version == SCHEMA_VERSION`

- `test_silence_returns_empty_or_low_confidence(silence_path)`:
  ```python
  config = TranscriptionConfig(stem_type="vocals", quality_profile="fast", minimum_confidence=0.3)
  events = PYINEngine().transcribe(str(silence_path), config)
  # Silence may produce 0 events OR all events below confidence threshold
  assert len(events) == 0 or all(e.confidence < 0.5 for e in events)
  ```

- `test_missing_file_raises_file_not_found(tmp_path)`:
  ```python
  config = TranscriptionConfig(stem_type="vocals", quality_profile="fast")
  with pytest.raises(FileNotFoundError):
      PYINEngine().transcribe(str(tmp_path / "does_not_exist.wav"), config)
  ```

- `test_minimum_confidence_filter(c_major_scale_path)`:
  - Run with `minimum_confidence=0.99` → likely 0 events (nothing exceeds 99% confidence)
  - Run with `minimum_confidence=0.0` → more events than with default threshold
  - Assert count with 0.0 >= count with default

- `test_minimum_duration_filter(c_major_scale_path)`:
  - Run with `minimum_note_length_ms=5000` (5 seconds) → 0 events (no note is 5 seconds long)
  - Assert `len(events) == 0`

- `test_source_model_contains_librosa_version(c_major_scale_path)`:
  ```python
  import librosa
  events = PYINEngine().transcribe(...)
  assert librosa.__version__ in events[0].source_model
  ```

**Execution Constraints:**
- Tolerance: pYIN on pure sine waves is reliable but not sample-perfect — use ranges, not exact counts
- Do not assert exact pitch values unless the note is A4 (440 Hz), where MIDI pitch 69 is deterministic
- No mocking — real librosa inference on real WAV files
- Tests must complete in under 30 seconds total

**Output Request:**
Return ONLY `tests/integration/test_transcription_pyin.py`.

---

### [T01-E] Create `tests/integration/test_transcription_basic_pitch.py` and `tests/requirements-test.txt`

**Target Files:** `tests/integration/test_transcription_basic_pitch.py`, `tests/requirements-test.txt`

**Context:** Integration tests for the Basic Pitch engine adapter. Basic Pitch may not be installed in the CI environment. These tests are skipped gracefully when `basic_pitch` is not installed — never fail because of an absent optional dependency. They do run in any environment where `pip install basic-pitch` has been run.

**Objective:**
Integration tests for the Basic Pitch adapter with automatic skip when the library is absent. Also create the test requirements file.

**Technical Specifications:**

**Skip decorator (place at the top of the module):**
```python
basic_pitch_available = pytest.importorskip(
    "basic_pitch",
    reason="basic-pitch not installed. Run: pip install basic-pitch"
)
```
`pytest.importorskip` skips the entire module if the import fails — no individual `skipif` needed on each test.

```python
pytestmark = pytest.mark.integration
```

**`TestBasicPitchEngineHealth`**:
- `test_health_check_passes` — `BasicPitchEngine().health_check() == True` (we're inside the skip guard so it must be installed)
- `test_model_info_polyphonic_true` — `model_info()["polyphonic"] == True`
- `test_model_info_has_version` — `"version"` key present in `model_info()`
- `test_supports_vocals_standard` — `engine.supports("vocals", "standard") == True`
- `test_supports_piano_high_quality` — `engine.supports("piano", "high_quality") == True`
- `test_does_not_support_fast_profile` — `engine.supports("vocals", "fast") == False` (fast → pYIN)
- `test_does_not_support_drums` — `engine.supports("drums", "standard") == False`

**`TestBasicPitchTranscription`**:

- `test_c_major_returns_note_events(c_major_scale_path)`:
  - Returns `list[NoteEvent]`, length > 0
  - All are `NoteEvent` instances

- `test_c_major_pitches_in_range(c_major_scale_path)`:
  - All pitches in `[60, 72]` (the scale spans C4–C5)

- `test_events_have_schema_fields(c_major_scale_path)`:
  - Every event: `source_model` contains `"basic_pitch"`, `schema_version == SCHEMA_VERSION`, `confidence` in `[0.0, 1.0]`

- `test_major_triad_detects_multiple_simultaneous_notes(major_triad_path)`:
  ```python
  config = TranscriptionConfig(stem_type="piano", quality_profile="standard",
                               minimum_confidence=0.2, minimum_note_length_ms=100.0)
  events = BasicPitchEngine().transcribe(str(major_triad_path), config)
  # A C major triad (C4+E4+G4) — Basic Pitch should detect at least 2 of 3 notes
  assert len(events) >= 2, f"Expected ≥2 simultaneous notes, got {len(events)}"
  pitches = {e.midi_pitch for e in events}
  # At least two of C4(60), E4(64), G4(67) should be present
  expected = {60, 64, 67}
  assert len(pitches & expected) >= 2
  ```

- `test_silence_produces_no_events(silence_path)`:
  ```python
  config = TranscriptionConfig(stem_type="vocals", quality_profile="standard",
                               minimum_confidence=0.3)
  events = BasicPitchEngine().transcribe(str(silence_path), config)
  assert len(events) == 0
  ```

- `test_events_sorted_by_start_time(c_major_scale_path)`:
  - Same pattern as pYIN test

- `test_confidence_filter_works(c_major_scale_path)`:
  - With `minimum_confidence=0.99` → fewer events than with `minimum_confidence=0.0`

- `test_missing_file_raises(tmp_path)`:
  - `FileNotFoundError` or `RuntimeError` — Basic Pitch may wrap the error; assert one of these two types

**`tests/requirements-test.txt`**:
```
# Test-only dependencies — do not add to backend/requirements.txt
pytest>=8.0
pytest-asyncio>=0.23
httpx>=0.27          # FastAPI test client
numpy>=1.24          # already in backend; listed here for clarity
soundfile>=0.12      # already in backend
mir_eval>=0.7        # musical accuracy metrics — test only, ~5 MB install
pyyaml>=6.0          # already in backend after Plan 02-H

# Optional — install manually to run Basic Pitch tests:
# basic-pitch>=0.3.1
# Optional — install manually to run Piano Kong tests:
# piano-transcription-inference>=1.0.0
# Optional — install manually to run ADTLib tests:
# adtlib
```

**Execution Constraints:**
- `pytest.importorskip("basic_pitch")` is the only mechanism needed — no `@pytest.mark.skipif`
- Tolerance on polyphony test: `>= 2` of 3 notes, not exact 3 (Basic Pitch on a pure sum of sines may alias)
- Do not assert `end_time` values — Basic Pitch offset detection is less reliable than onset

**Output Request:**
Return BOTH files: `tests/integration/test_transcription_basic_pitch.py` and `tests/requirements-test.txt`.
