---

## PLAN 04 — Agent Prompt Suite + Tests
### Beat, Tempo, Meter and Musical Quantization

Six implementation prompts, three test prompts. All local — zero Colab cost.

**Prerequisite:** Plans 01, 02, 03 complete. All prompts import from `backend.schema.*`.

---

### [P04-A] Create `backend/audio/duration_mapper.py` — Tick-to-Duration Name Mapping

**Target File:** `backend/audio/duration_mapper.py`

**Context:** MWTN's quantizer (Plan 04) maps note timings onto a beat grid measured in ticks (24 ticks per beat = 1 subdivision). Once a note's duration is expressed in ticks, it needs a human-readable name (`"quarter"`, `"dotted eighth"`, etc.) for MusicXML generation and display. This is a pure lookup module — no audio, no models, no I/O.

**Objective:**
Create the duration mapping module as a standalone pure-Python module with no external dependencies beyond stdlib.

**Technical Specifications:**

Constants:
```python
TICKS_PER_BEAT = 24          # subdivisions per quarter note
TICKS_PER_WHOLE = 96         # 4 beats × 24 ticks
```

`DURATION_TABLE: list[tuple[int, str, bool]]` — ordered from longest to shortest, each entry is `(ticks, name, dotted)`:
```python
DURATION_TABLE = [
    (96, "whole",           False),
    (72, "half",            True),   # dotted half
    (48, "half",            False),
    (36, "quarter",         True),   # dotted quarter
    (32, "quarter",         False),  # quarter triplet (2/3 of a beat × 3 = 2 beats worth, but per-note = 32/24 beat)
    (24, "quarter",         False),
    (18, "eighth",          True),   # dotted eighth
    (16, "eighth",          False),  # eighth triplet
    (12, "eighth",          False),
    (9,  "sixteenth",       True),   # dotted sixteenth
    (8,  "sixteenth",       False),  # sixteenth triplet
    (6,  "sixteenth",       False),
    (3,  "thirty-second",   False),
]
```

> Note to agent: The table has intentional ambiguity (two entries at 24, two at 12, etc.). The `ticks_to_duration_name` function uses the first exact match. The table is ordered so common durations (plain quarter = 24) come before less common ones (quarter triplet = 32 is listed before the plain quarter at 24 since 32 > 24 — actually reorder correctly). **Reorder the table strictly from highest tick count to lowest, removing any ambiguous duplicates.** Use this corrected table:

```python
DURATION_TABLE = [
    (96, "whole",           False),
    (72, "half",            True),
    (48, "half",            False),
    (36, "quarter",         True),
    (24, "quarter",         False),
    (18, "eighth",          True),
    (12, "eighth",          False),
    (9,  "sixteenth",       True),
    (6,  "sixteenth",       False),
    (3,  "thirty-second",   False),
]

TRIPLET_TABLE = [
    (32, "quarter",  "triplet"),   # 3 quarter triplets fill 2 beats
    (16, "eighth",   "triplet"),   # 3 eighth triplets fill 1 beat
    (8,  "sixteenth","triplet"),
]
```

**Functions:**

```python
def ticks_to_duration_name(ticks: int, tolerance: int = 1) -> tuple[str, bool, str | None]:
    """
    Map a tick count to (duration_name, dotted, tuplet_type).
    tuplet_type is None for normal durations, "triplet" for triplets.
    tolerance: accept a tick count within ±tolerance of a table entry.
    Returns ("unknown", False, None) if no match found.
    """
```
- Search `DURATION_TABLE` first for exact match (within tolerance)
- If not found, search `TRIPLET_TABLE`
- Return `("unknown", False, None)` if neither matches

```python
def duration_name_to_ticks(name: str, dotted: bool = False, tuplet: str | None = None) -> int:
    """
    Inverse lookup: name → tick count.
    Raises ValueError if name not found.
    """
```

```python
def ticks_to_quarter_length(ticks: int) -> float:
    """Convert tick count to music21 quarterLength float (quarter = 1.0)."""
    return ticks / TICKS_PER_BEAT
```

```python
def quarter_length_to_ticks(ql: float) -> int:
    """Convert music21 quarterLength to tick count. Rounds to nearest tick."""
    return round(ql * TICKS_PER_BEAT)
```

```python
def seconds_to_ticks(duration_s: float, tempo_bpm: float) -> int:
    """Convert a duration in seconds to ticks at a given tempo."""
    beats = duration_s * (tempo_bpm / 60.0)
    return round(beats * TICKS_PER_BEAT)
```

```python
def ticks_to_seconds(ticks: int, tempo_bpm: float) -> float:
    """Convert tick count to seconds at a given tempo."""
    beats = ticks / TICKS_PER_BEAT
    return beats * (60.0 / tempo_bpm)
```

**Execution Constraints:**
- Pure Python stdlib only — no numpy, no librosa, no pydantic
- `DURATION_TABLE` and `TRIPLET_TABLE` are module-level constants
- `ticks_to_duration_name` must never raise — always return a 3-tuple
- `duration_name_to_ticks` raises `ValueError` with a message listing valid names

**Output Request:**
Return ONLY `backend/audio/duration_mapper.py`.

---

### [P04-B] Create `backend/audio/meter.py` — Beat Grid Builder and Time Signature Detection

**Target File:** `backend/audio/meter.py`

**Context:** A beat grid is the bridge between audio timestamps (seconds) and musical positions (measure, beat, subdivision). MWTN builds it from beat tracker output and uses it for quantization, MusicXML bar lines, and synchronized UI display. Time signature detection uses madmom's downbeat processor when available, falling back to a simple 4/4 assumption.

**Objective:**
Create the beat grid builder and time signature detector with madmom (primary) and librosa (fallback) backends.

**Technical Specifications:**

`TimeSig` — simple dataclass:
```python
from dataclasses import dataclass

@dataclass
class TimeSig:
    numerator: int    # beats per measure (2, 3, 4, 6)
    denominator: int  # beat unit (4 = quarter, 8 = eighth)

    def beats_per_measure(self) -> int:
        return self.numerator

    def ticks_per_measure(self) -> int:
        from backend.audio.duration_mapper import TICKS_PER_BEAT
        return self.numerator * TICKS_PER_BEAT
```

`SUPPORTED_TIME_SIGNATURES: list[TimeSig]`:
```python
SUPPORTED_TIME_SIGNATURES = [
    TimeSig(2, 4),
    TimeSig(3, 4),
    TimeSig(4, 4),
    TimeSig(6, 8),
]
```

`BeatGridEntry` — dataclass:
```python
@dataclass
class BeatGridEntry:
    beat_index: int       # 0-based absolute beat index
    time_s: float         # seconds from audio start
    measure_number: int   # 1-based
    beat_in_measure: int  # 1-based
    is_downbeat: bool
    tempo_bpm: float      # local tempo at this beat
```

`BeatGrid` — dataclass:
```python
@dataclass
class BeatGrid:
    entries: list[BeatGridEntry]
    time_sig: TimeSig
    tempo_map: list[dict]        # [{"beat_index": int, "time_s": float, "bpm": float}]
    assumed_time_sig: bool       # True if time signature was not detected, just assumed
    source: str                  # "madmom" | "librosa"

    def get_beat_at_time(self, time_s: float) -> BeatGridEntry | None:
        """Return the beat entry closest to time_s (before or at)."""
        ...

    def get_measure_range(self, measure_number: int) -> tuple[float, float] | None:
        """Return (start_s, end_s) for a given measure number."""
        ...

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict for caching as beats.json."""
        ...
```

`detect_time_signature(beat_times: list[float], downbeat_times: list[float]) -> tuple[TimeSig, bool]`:
- If `downbeat_times` is empty or only one entry → return `(TimeSig(4, 4), True)` (assumed)
- Compute mean number of beats between consecutive downbeats
- Round to nearest integer in {2, 3, 4, 6}
- Match to `SUPPORTED_TIME_SIGNATURES`; if no match, fall back to 4/4
- Return `(time_sig, assumed)` where `assumed=True` if fallback was used

`build_beat_grid(beat_times: list[float], downbeat_times: list[float], time_sig: TimeSig) -> BeatGrid`:
- Assign each beat to a measure based on downbeat positions
- Compute local BPM between consecutive beats (smooth with a window of 4 beats to reduce jitter):
  ```python
  def local_bpm(t1: float, t2: float) -> float:
      return 60.0 / max(t2 - t1, 0.001)
  ```
- Build a `BeatGridEntry` for each beat time
- Build `tempo_map`: record a new entry whenever BPM changes by more than 2 BPM
- Return complete `BeatGrid`

`track_beats_madmom(audio_path: str | Path, device: str = "cpu") -> tuple[list[float], list[float]]`:
```python
"""
Returns (beat_times, downbeat_times) using madmom RNNBeatProcessor + RNNDownBeatProcessor.
Raises ImportError if madmom not installed.
"""
```
Implementation:
```python
from madmom.features.beats import RNNBeatProcessor, DBNBeatTrackingProcessor
from madmom.features.downbeats import RNNDownBeatProcessor, DBNDownBeatTrackingProcessor

beat_proc = RNNBeatProcessor()(str(audio_path))
beat_times = DBNBeatTrackingProcessor(fps=100)(beat_proc).tolist()

downbeat_proc = RNNDownBeatProcessor()(str(audio_path))
downbeat_activations = DBNDownBeatTrackingProcessor(beats_per_bar=[2,3,4,6], fps=100)(downbeat_proc)
# downbeat_activations: array of [time, beat_in_bar]; downbeats where beat_in_bar == 1
downbeat_times = [float(row[0]) for row in downbeat_activations if int(row[1]) == 1]

return beat_times, downbeat_times
```

`track_beats_librosa(audio_path: str | Path) -> tuple[list[float], list[float]]`:
```python
"""
Returns (beat_times, downbeat_times) using librosa.
downbeat_times is approximate: every 4th beat from the first.
"""
import librosa, soundfile as sf
audio, sr = librosa.load(str(audio_path), sr=None, mono=True)
tempo, beat_frames = librosa.beat.beat_track(y=audio, sr=sr, units='frames')
beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
# Approximate downbeats: every 4th beat starting from beat 0
downbeat_times = beat_times[::4]
return beat_times, downbeat_times
```

`analyze_rhythm(audio_path: str | Path, device: str = "cpu") -> BeatGrid`:
```python
"""
Top-level function. Tries madmom first; falls back to librosa.
"""
try:
    beat_times, downbeat_times = track_beats_madmom(audio_path, device)
    source = "madmom"
except ImportError:
    beat_times, downbeat_times = track_beats_librosa(audio_path)
    source = "librosa"

time_sig, assumed = detect_time_signature(beat_times, downbeat_times)
grid = build_beat_grid(beat_times, downbeat_times, time_sig)
grid.source = source
return grid
```

**Execution Constraints:**
- All madmom imports inside `track_beats_madmom` — never at module top level
- `librosa` can be at module top level (always available in MWTN)
- `BeatGrid.to_dict()` must be JSON-serializable (no numpy types — convert to float/int)
- `get_beat_at_time` must handle `time_s` before the first beat (return first entry) and after the last (return last entry)
- Preserve existing `backend/audio/bpm.py` behavior — do not modify it

**Output Request:**
Return ONLY `backend/audio/meter.py`.

---

### [P04-C] Create `backend/audio/quantizer.py` — Event Quantization Engine

**Target File:** `backend/audio/quantizer.py`

**Context:** The quantizer takes raw `NoteEvent` and `RestEvent` objects (from Plan 02 transcription) and adds musical position information to each — measure, beat, subdivision, and duration name — without overwriting the original timing. It also generates rest events for gaps and handles notes that cross bar lines.

**Objective:**
Create the quantization engine that transforms time-domain events into notation-ready events.

**Technical Specifications:**

`QuantizationMode = Literal["strict", "humanized", "off"]`

`QuantizationConfig` — dataclass:
```python
@dataclass
class QuantizationConfig:
    mode: QuantizationMode = "humanized"
    humanized_tolerance: float = 0.15   # ±15% of beat duration
    subdivision_resolution: int = 24    # ticks per beat (must match TICKS_PER_BEAT)
    generate_rests: bool = True
    detect_triplets: bool = True
    triplet_tolerance: float = 0.1      # 10% timing deviation for triplet detection
```

`QuantizedPosition` — dataclass:
```python
@dataclass
class QuantizedPosition:
    measure: int         # 1-based
    beat: int            # 1-based within measure
    subdivision: int     # 0-based ticks within beat
    tick: int            # absolute ticks from song start
```

`quantize_time(time_s: float, grid: BeatGrid, config: QuantizationConfig) -> QuantizedPosition | None`:
- Find the nearest beat grid entry to `time_s`
- Compute offset in seconds from that beat: `offset_s = time_s - beat_entry.time_s`
- Convert offset to ticks: `offset_ticks = seconds_to_ticks(offset_s, beat_entry.tempo_bpm)`
- Snap: round `offset_ticks` to nearest tick
- If `mode == "humanized"`:
  - Compute beat duration in seconds: `beat_s = 60.0 / beat_entry.tempo_bpm`
  - If `abs(offset_s)` > `config.humanized_tolerance * beat_s`: do not snap, return the raw fractional position
- If `mode == "off"`: compute position without snapping
- Return `QuantizedPosition(measure, beat, subdivision, absolute_tick)`

`quantize_event(event: NoteEvent, grid: BeatGrid, config: QuantizationConfig) -> dict`:
```python
"""
Returns a dict of quantization fields to merge into the event.
Does NOT modify the original event.
"""
```
Output dict structure:
```python
{
    "quantized_start": { "measure": 2, "beat": 1, "subdivision": 0, "tick": 480 },
    "quantized_end":   { "measure": 2, "beat": 2, "subdivision": 0, "tick": 504 },
    "quantized_duration_ticks": 24,
    "quantized_duration_name": "quarter",
    "dotted": False,
    "tuplet": None,
    "tied_from_previous": False,
    "tied_to_next": False,
    "quantization_confidence": 0.91,
    "quantization_mode": config.mode,
}
```

`quantization_confidence` calculation:
- Compute how far `start_time` deviated from the nearest grid point as a fraction of beat duration
- `confidence = 1.0 - min(deviation_fraction, 1.0)`

`split_at_barline(event: NoteEvent, grid: BeatGrid, config: QuantizationConfig) -> list[dict]`:
```python
"""
If an event's quantized start and end fall in different measures, split it.
Returns a list of 1 or 2 quantization dicts.
If 2: first has tied_to_next=True, second has tied_from_previous=True.
"""
```

`detect_triplets(events: list[NoteEvent], grid: BeatGrid, config: QuantizationConfig) -> list[int]`:
```python
"""
Scan consecutive groups of 3 notes within a single beat.
Returns indices of events that form triplet groups.
Triplet criteria:
  - 3 consecutive notes within one beat duration
  - Near-equal spacing (each note ≈ 1/3 of beat duration)
  - Combined duration ≈ 2/3 of beat (within tolerance)
"""
```

`generate_rests(events: list[NoteEvent], grid: BeatGrid) -> list[RestEvent]`:
```python
"""
For gaps between quantized events on the same track, generate RestEvents.
A gap >= 1 tick triggers a rest.
Returns list of RestEvent objects (Plan 01 schema).
"""
```

`validate_measure(measure_events: list, time_sig: TimeSig) -> dict`:
```python
"""
Check that all note + rest durations in a measure sum to the time signature total.
Returns {"valid": bool, "total_ticks": int, "expected_ticks": int, "error": str | None}
"""
```

`quantize_events(
    events: list[NoteEvent],
    grid: BeatGrid,
    config: QuantizationConfig | None = None,
) -> list[dict]`:
```python
"""
Top-level function. Quantizes all events, handles bar-line splits,
detects triplets, generates rests, validates measures.
Returns list of dicts — each dict is the original event.model_dump()
merged with its quantization fields.
"""
```
Steps:
1. Default `config = QuantizationConfig()` if None
2. Sort events by `start_time`
3. For each event: call `quantize_event` → get quantization dict → check for barline split → `split_at_barline` if needed
4. If `config.detect_triplets`: call `detect_triplets` and add `tuplet` field to matching events
5. If `config.generate_rests`: call `generate_rests` and insert into event list, sorted by time
6. Group by measure → call `validate_measure` → attach `measure_validation` to events in that measure
7. Return complete merged event dicts sorted by `quantized_start.tick`

**Execution Constraints:**
- Import from `backend.audio.duration_mapper` and `backend.audio.meter`
- Import `NoteEvent`, `RestEvent` from `backend.schema.events`
- All output dicts contain the original event fields + quantization fields — never lose original `start_time`, `end_time`, `midi_pitch`
- `quantize_time` never raises — returns `None` if the event falls outside the grid entirely
- Triplet detection only runs when at least 3 events exist in the same beat

**Output Request:**
Return ONLY `backend/audio/quantizer.py`.

---

### [P04-D] Create `backend/audio/beat_tracker.py` — Unified Beat Analysis Entry Point

**Target File:** `backend/audio/beat_tracker.py`

**Context:** `backend/audio/bpm.py` already runs librosa `beat_track` and caches `beats.json`. The new `meter.py` has a richer `analyze_rhythm()` function. This file unifies both: it calls `analyze_rhythm()`, produces the full `BeatGrid`, and writes a new-format `beats.json` that is backward-compatible with the existing format (so existing songs' cached beats still load without migration).

**Objective:**
Create a unified beat analysis entry point that wraps `meter.analyze_rhythm()`, caches the result, and is backward-compatible with the existing `beats.json` schema.

**Technical Specifications:**

`BEATS_JSON_SCHEMA_VERSION = "2.0"` — the new beat format version. Existing files have no `schema_version` (legacy).

`load_or_analyze_beats(
    audio_path: Path,
    cache_path: Path,
    force_reanalyze: bool = False,
    device: str = "cpu",
) -> BeatGrid`:
```python
"""
Load beats from cache if available and valid. Otherwise run full analysis.
cache_path: path to beats.json inside the song directory.
"""
```
Steps:
1. If not `force_reanalyze` and `cache_path.exists()`: try loading; if `schema_version == "2.0"`, deserialize into `BeatGrid` and return
2. If `schema_version` is missing (legacy): read existing `bpm` and `beats` fields; construct a minimal `BeatGrid` with 4/4 assumption and `assumed_time_sig=True`; do NOT reanalyze (preserve existing cached results)
3. Otherwise: call `analyze_rhythm(audio_path, device)` → `BeatGrid`
4. Write `BeatGrid.to_dict()` to `cache_path` with `schema_version: "2.0"` added
5. Return the grid

`write_beats_json(grid: BeatGrid, path: Path) -> None`:
```python
"""Write BeatGrid to disk as beats.json. Atomic write."""
data = grid.to_dict()
data["schema_version"] = BEATS_JSON_SCHEMA_VERSION
# also write legacy fields for backward compat with existing frontend consumers:
data["bpm"] = grid.tempo_map[0]["bpm"] if grid.tempo_map else 120.0
data["beats"] = [e.time_s for e in grid.entries]
tmp = path.with_suffix(".tmp")
tmp.write_text(json.dumps(data, indent=2))
os.replace(tmp, path)
```

`get_tempo_at_time(grid: BeatGrid, time_s: float) -> float`:
```python
"""Return BPM from the tempo map at a given timestamp."""
```
- Iterate `grid.tempo_map` in reverse; return the first entry with `time_s >= entry["time_s"]`
- If `time_s` is before all entries, return the first entry's BPM

**Execution Constraints:**
- Import `analyze_rhythm`, `BeatGrid` from `backend.audio.meter`
- Backward-compat write: always include legacy `bpm` and `beats` fields in the JSON output so the existing frontend `GET /api/songs/{song_id}/beats` endpoint continues working without any changes
- `force_reanalyze` bypasses the cache; existing data is overwritten
- Do not modify `backend/audio/bpm.py`

**Output Request:**
Return ONLY `backend/audio/beat_tracker.py`.

---

### [P04-E] Wire Plan 04 into `backend/main.py` — New Endpoints Only

**Target File:** `backend/main.py` (additive only)

**Context:** Two new endpoints for Plan 04: one to trigger full beat/meter analysis on demand, and one to allow the user to override the detected time signature. No existing routes are modified.

**Objective:**
Add two new endpoints to `main.py` for beat grid analysis and meter override.

**Technical Specifications:**

**Required new imports:**
```python
from backend.audio.beat_tracker import load_or_analyze_beats, write_beats_json
from backend.audio.meter import TimeSig, SUPPORTED_TIME_SIGNATURES
from backend.audio.quantizer import quantize_events, QuantizationConfig
```

**New endpoint 1 — `POST /api/songs/{song_id}/analyze/beats`:**
```python
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
```

**New endpoint 2 — `PATCH /api/songs/{song_id}/meter`:**
```python
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
```

**Execution Constraints:**
- Additive only — do not change any existing endpoint
- Use `validate_song_id` on every `song_id` param
- Both endpoints block synchronously (beat analysis is fast enough; madmom on 3min song < 5s)

**Output Request:**
Return the two new endpoint functions and their required imports as labeled code blocks. Do not return the full `main.py`.

---

### [P04-F] Update `colab/mwtn_notebook.ipynb` — Add madmom Beat Tracking Cell

**Target File:** `colab/mwtn_notebook.ipynb`

**Context:** The Colab notebook needs a madmom install cell and an updated beat tracking cell that uses `analyze_rhythm()` instead of the bare librosa call. The notebook structure uses sequential numbered cells. This prompt specifies the new cells to add; the agent inserts them at the correct positions.

**Objective:**
Add two new notebook cells to the Colab pipeline: a madmom install cell and a full beat/meter analysis cell that replaces the existing bare BPM cell.

**Technical Specifications:**

This is a JSON edit to `mwtn_notebook.ipynb`. The agent must:
1. Read the existing notebook
2. Find the cell that currently does BPM detection (it will contain `librosa.beat.beat_track` or reference to `bpm.py`)
3. Insert a new install cell **before** it
4. Replace (or augment) the existing BPM cell with a full beat analysis cell

**New Cell 1 — Install madmom (insert before beat tracking cell):**
```python
# Cell: Install madmom for beat + downbeat tracking
# Data cost: ~50 MB (one-time per Colab session)
print("Installing madmom...")
import subprocess
result = subprocess.run(
    ["pip", "install", "madmom", "--quiet"],
    capture_output=True, text=True
)
if result.returncode == 0:
    print("madmom installed successfully.")
else:
    print(f"madmom install failed (will fall back to librosa): {result.stderr[:200]}")
```

**New Cell 2 — Full beat/meter analysis (replace or augment existing BPM cell):**
```python
# Cell: Beat tracking + meter detection
# Uses madmom if available, falls back to librosa automatically.
# Output: beats.json with full beat grid, tempo map, and time signature.

import sys
sys.path.insert(0, '/content/mwtn/backend')  # adjust if repo path differs

from pathlib import Path
from backend.audio.beat_tracker import load_or_analyze_beats, write_beats_json

SONG_ID = song_id  # set from earlier cell
AUDIO_PATH = Path(f"/content/mwtn/backend/data/{SONG_ID}/source/original.mp3")  # adjust ext as needed
CACHE_PATH = Path(f"/content/mwtn/backend/data/{SONG_ID}/beats.json")

# Use GPU device if available
import torch
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {device}")

print("Analyzing beat structure...")
grid = load_or_analyze_beats(AUDIO_PATH, CACHE_PATH, force_reanalyze=True, device=device)

print(f"Time signature: {grid.time_sig.numerator}/{grid.time_sig.denominator}" +
      (" (assumed)" if grid.assumed_time_sig else " (detected)"))
print(f"Beats detected: {len(grid.entries)}")
print(f"Measures: {max(e.measure_number for e in grid.entries) if grid.entries else 0}")
print(f"Tempo map entries: {len(grid.tempo_map)}")
if grid.tempo_map:
    print(f"Initial tempo: {grid.tempo_map[0]['bpm']:.1f} BPM")
print(f"Analysis source: {grid.source}")
print("beats.json written.")
```

The agent should also add a fallback note as a markdown cell before the install cell:
```markdown
### Beat & Meter Analysis
Uses **madmom** (preferred) for beat tracking with downbeat detection and time signature estimation.
Falls back to **librosa** if madmom install fails.
Madmom install is ~50 MB — runs on Colab's connection, not yours.
```

**Execution Constraints:**
- Do not remove the existing librosa BPM cell — augment or mark it as superseded with a comment
- The new cells must run in the context where `song_id` is already defined from a prior cell
- `force_reanalyze=True` in the notebook cell — always run fresh on Colab (no stale cache issues)
- The agent returns the new cell JSON objects ready to splice into the notebook, not the full notebook

**Output Request:**
Return the three new cells as properly structured Jupyter notebook cell JSON objects (type, source, metadata fields), labeled clearly so the developer knows where to insert each one.

---

Now the tests.

---

### [T04-A] Create `tests/unit/test_duration_mapper.py` — Duration Mapping Unit Tests

**Target File:** `tests/unit/test_duration_mapper.py`

**Context:** `backend/audio/duration_mapper.py` is pure Python with no dependencies. Tests are completely deterministic and require no audio, no fixtures, no conftest setup beyond the module import.

**Objective:**
Comprehensive unit tests for all functions in `duration_mapper.py`.

**Technical Specifications:**

```python
pytestmark = pytest.mark.unit
```

**`TestDurationConstants`**:
- `test_ticks_per_beat` — `TICKS_PER_BEAT == 24`
- `test_ticks_per_whole` — `TICKS_PER_WHOLE == 96`
- `test_duration_table_sorted_descending` — tick counts in `DURATION_TABLE` are strictly descending
- `test_no_negative_ticks_in_table` — all tick values > 0

**`TestTicksToDurationName`**:
- `test_whole_note` — `ticks_to_duration_name(96)` → `("whole", False, None)`
- `test_half_note` — `ticks_to_duration_name(48)` → `("half", False, None)`
- `test_dotted_half` — `ticks_to_duration_name(72)` → `("half", True, None)`
- `test_quarter_note` — `ticks_to_duration_name(24)` → `("quarter", False, None)`
- `test_dotted_quarter` — `ticks_to_duration_name(36)` → `("quarter", True, None)`
- `test_eighth_note` — `ticks_to_duration_name(12)` → `("eighth", False, None)`
- `test_dotted_eighth` — `ticks_to_duration_name(18)` → `("eighth", True, None)`
- `test_sixteenth_note` — `ticks_to_duration_name(6)` → `("sixteenth", False, None)`
- `test_thirty_second` — `ticks_to_duration_name(3)` → `("thirty-second", False, None)`
- `test_quarter_triplet` — `ticks_to_duration_name(16)` → `("eighth", "triplet")` or similar; assert it doesn't return "unknown"
- `test_unknown_returns_unknown` — `ticks_to_duration_name(97)` → first element is `"unknown"`
- `test_never_raises_on_any_int` — call with every int 0–200; assert no exception raised
- `test_tolerance_accepts_near_match` — `ticks_to_duration_name(25, tolerance=2)` → `("quarter", False, None)` (25 is within 1 of 24)
- `test_tolerance_zero_strict` — `ticks_to_duration_name(25, tolerance=0)` → `"unknown"`

**`TestDurationNameToTicks`**:
- `test_quarter_to_ticks` — `duration_name_to_ticks("quarter") == 24`
- `test_dotted_quarter` — `duration_name_to_ticks("quarter", dotted=True) == 36`
- `test_whole_to_ticks` — `duration_name_to_ticks("whole") == 96`
- `test_unknown_name_raises` — `duration_name_to_ticks("hundredth")` → `ValueError`
- `test_roundtrip_all_durations` — for every entry in `DURATION_TABLE`, `ticks_to_duration_name(ticks)[0]` fed back to `duration_name_to_ticks` returns the same tick count

**`TestConversionFunctions`**:
- `test_ticks_to_quarter_length_quarter` — `ticks_to_quarter_length(24) == 1.0`
- `test_ticks_to_quarter_length_half` — `ticks_to_quarter_length(48) == 2.0`
- `test_quarter_length_to_ticks` — `quarter_length_to_ticks(1.0) == 24`
- `test_seconds_to_ticks_120bpm_quarter` — at 120 BPM a quarter note = 0.5s; `seconds_to_ticks(0.5, 120.0) == 24`
- `test_seconds_to_ticks_60bpm_whole` — at 60 BPM a whole note = 4.0s; `seconds_to_ticks(4.0, 60.0) == 96`
- `test_ticks_to_seconds_120bpm` — at 120 BPM, 24 ticks = 0.5s; `abs(ticks_to_seconds(24, 120.0) - 0.5) < 0.001`
- `test_roundtrip_seconds_at_120bpm` — `seconds_to_ticks(ticks_to_seconds(24, 120.0), 120.0) == 24`

**Output Request:**
Return ONLY `tests/unit/test_duration_mapper.py`.

---

### [T04-B] Create `tests/unit/test_meter.py` — Meter and Beat Grid Unit Tests

**Target File:** `tests/unit/test_meter.py`

**Context:** Tests for `backend/audio/meter.py` — time signature detection, beat grid construction, and the grid query methods. These tests use synthetic beat time lists built inline — no audio files needed for the pure logic tests. Integration tests (madmom/librosa on real audio) are in a separate file.

**Objective:**
Unit tests for `detect_time_signature`, `build_beat_grid`, and `BeatGrid` methods.

**Technical Specifications:**

```python
pytestmark = pytest.mark.unit
```

Helper at the top of the file:
```python
def make_beat_times(bpm: float, duration_s: float, start_s: float = 0.0) -> list[float]:
    """Generate synthetic beat times at a given BPM."""
    beat_interval = 60.0 / bpm
    times = []
    t = start_s
    while t < start_s + duration_s:
        times.append(round(t, 6))
        t += beat_interval
    return times

def make_downbeat_times(beat_times: list[float], beats_per_measure: int) -> list[float]:
    """Every Nth beat is a downbeat."""
    return [beat_times[i] for i in range(0, len(beat_times), beats_per_measure)]
```

**`TestTimeSig`**:
- `test_4_4_beats_per_measure` — `TimeSig(4, 4).beats_per_measure() == 4`
- `test_3_4_ticks_per_measure` — `TimeSig(3, 4).ticks_per_measure() == 72` (3 × 24)
- `test_6_8_ticks_per_measure` — `TimeSig(6, 8).ticks_per_measure() == 144` (6 × 24)

**`TestDetectTimeSignature`**:
- `test_4_4_from_clean_downbeats` — 16 beats at 120 BPM, downbeat every 4 beats → `TimeSig(4,4)`, `assumed=False`
- `test_3_4_from_clean_downbeats` — 12 beats, downbeat every 3 beats → `TimeSig(3,4)`, `assumed=False`
- `test_no_downbeats_assumes_4_4` — `downbeat_times=[]` → `TimeSig(4,4)`, `assumed=True`
- `test_one_downbeat_assumes_4_4` — single downbeat → `assumed=True`
- `test_noisy_downbeats_still_detects` — 16 beats, downbeats every 4 beats with ±20ms jitter → detects 4/4

**`TestBuildBeatGrid`**:
- `test_grid_entry_count_matches_beats` — 16 beat times → 16 `BeatGridEntry` objects
- `test_measure_numbers_correct_4_4` — beats 0-3 → measure 1; beats 4-7 → measure 2; etc.
- `test_measure_numbers_correct_3_4` — beats 0-2 → measure 1; beats 3-5 → measure 2
- `test_beat_in_measure_cycles` — for 4/4: `beat_in_measure` values cycle 1,2,3,4,1,2,3,4...
- `test_downbeat_flag_set_correctly` — entries with `beat_in_measure == 1` have `is_downbeat=True`
- `test_tempo_bpm_roughly_correct` — beat times at 120 BPM → each entry's `tempo_bpm` within ±5 of 120
- `test_tempo_map_has_at_least_one_entry` — even a constant-tempo grid has 1 tempo map entry
- `test_tempo_map_detects_change` — 8 beats at 120 BPM then 8 beats at 160 BPM → tempo map has ≥ 2 entries

**`TestBeatGridMethods`**:
- `test_get_beat_at_time_exact` — query exact beat time → returns that entry
- `test_get_beat_at_time_between_beats` — query time halfway between two beats → returns earlier beat
- `test_get_beat_at_time_before_first` — negative time → returns first entry (not None)
- `test_get_beat_at_time_after_last` — time past last beat → returns last entry
- `test_get_measure_range_valid` — measure 1's start_s ≈ 0.0; end_s ≈ start of measure 2
- `test_get_measure_range_invalid` — measure 9999 → `None`
- `test_to_dict_is_json_serializable` — `json.dumps(grid.to_dict())` doesn't raise
- `test_to_dict_contains_legacy_fields` — result has `"beats"` and `"bpm"` keys for backward compat

**Output Request:**
Return ONLY `tests/unit/test_meter.py`.

---

### [T04-C] Create `tests/unit/test_quantizer.py` — Quantizer Unit Tests

**Target File:** `tests/unit/test_quantizer.py`

**Context:** Tests for `backend/audio/quantizer.py`. The quantizer is the most logic-dense module in Plan 04 — it combines beat grid lookups, tick arithmetic, barline splitting, triplet detection, and rest generation. All tests use synthetically constructed `BeatGrid` and `NoteEvent` objects — no audio, no models.

**Objective:**
Comprehensive unit tests for all quantizer functions covering all quantization modes, edge cases, and musical correctness.

**Technical Specifications:**

```python
pytestmark = pytest.mark.unit
```

Helpers at the top of the file:
```python
def make_simple_grid(bpm: float = 120.0, measures: int = 4, time_sig: tuple = (4, 4)) -> BeatGrid:
    """Build a synthetic BeatGrid for testing."""
    from tests.unit.test_meter import make_beat_times, make_downbeat_times
    beat_times = make_beat_times(bpm, duration_s=(measures * time_sig[0] * 60.0 / bpm))
    downbeat_times = make_downbeat_times(beat_times, time_sig[0])
    ts = TimeSig(time_sig[0], time_sig[1])
    return build_beat_grid(beat_times, downbeat_times, ts)

def make_note(start_time: float, end_time: float, midi_pitch: int = 60, track_id: str = "vocals") -> NoteEvent:
    """Build a NoteEvent for testing."""
    return NoteEvent(
        start_time=start_time,
        end_time=end_time,
        midi_pitch=midi_pitch,
        confidence=0.9,
        source_model="test",
        track_id=track_id,
    )
```

**`TestQuantizeTime`**:
- `test_snaps_to_beat_start_strict` — time exactly on beat 1 of measure 1 at 120 BPM → `measure=1, beat=1, subdivision=0`
- `test_snaps_to_beat_start_humanized` — time 20ms before a beat (within tolerance at 120 BPM) → snaps to beat
- `test_humanized_does_not_snap_distant` — time at 60% of a beat duration from any grid point → no snap; raw fractional position returned
- `test_off_mode_no_snap` — `mode="off"` → always returns raw fractional position without snapping
- `test_returns_none_outside_grid` — time far beyond last beat → returns `None` or last grid entry (check behavior)

**`TestQuantizeEvent`**:
- `test_quarter_note_at_120bpm` — note from 0.0s to 0.5s at 120 BPM → `quantized_duration_name == "quarter"`, `quantized_duration_ticks == 24`
- `test_half_note_at_120bpm` — 0.0s to 1.0s → `"half"`, 48 ticks
- `test_whole_note_at_120bpm` — 0.0s to 2.0s → `"whole"`, 96 ticks
- `test_raw_timing_preserved` — original `start_time`, `end_time` present in output dict unchanged
- `test_confidence_is_float_in_range` — `quantization_confidence` between 0.0 and 1.0
- `test_quantization_mode_recorded` — `quantization_mode` field matches config mode
- `test_on_beat_has_high_confidence` — note exactly on a beat → `quantization_confidence >= 0.9`
- `test_off_beat_has_lower_confidence` — note 40% of beat duration off a beat → `quantization_confidence < 0.7`

**`TestSplitAtBarline`**:
- `test_note_within_measure_no_split` — quarter note within measure 1 → returns list of length 1, `tied_to_next=False`
- `test_note_crossing_barline_splits` — note from beat 4 of measure 1 to beat 2 of measure 2 → returns list of length 2
- `test_first_part_has_tied_to_next` — first dict in split result has `tied_to_next=True`
- `test_second_part_has_tied_from_previous` — second dict has `tied_from_previous=True`
- `test_split_durations_sum_to_original` — sum of `quantized_duration_ticks` in both parts equals the original note's tick duration

**`TestDetectTriplets`**:
- `test_three_equal_notes_per_beat_are_triplets` — 3 notes evenly spaced across one beat at 120 BPM (each ≈ 0.167s) → all 3 detected as triplets
- `test_four_notes_per_beat_not_triplets` — 4 equal notes per beat → no triplets detected
- `test_insufficient_notes_no_detection` — fewer than 3 notes → returns empty list

**`TestGenerateRests`**:
- `test_gap_between_notes_generates_rest` — note at 0.0–0.5s, next note at 1.0–1.5s → rest generated for 0.5–1.0s
- `test_no_gap_no_rest` — consecutive notes with no gap → no rest generated
- `test_rest_has_correct_start_and_duration` — rest's `start_time` matches end of preceding note; `duration_s` matches the gap

**`TestValidateMeasure`**:
- `test_valid_4_4_measure` — 4 quarter notes → `{"valid": True, "total_ticks": 96, "expected_ticks": 96}`
- `test_invalid_measure_too_short` — 3 quarter notes in a 4/4 bar → `{"valid": False, ...}`
- `test_invalid_measure_too_long` — 5 quarter notes in 4/4 → `{"valid": False}`

**`TestQuantizeEvents`**:
- `test_empty_list_returns_empty` — `quantize_events([], grid) == []`
- `test_sorted_output` — even if input is unsorted, output is sorted by `quantized_start.tick`
- `test_rests_inserted_for_gaps` — 2 notes with gap → output contains a rest event between them
- `test_all_events_have_quantized_fields` — every output dict has `quantized_start`, `quantized_duration_ticks`, `quantized_duration_name`
- `test_mode_off_preserves_raw_timing` — with `mode="off"`, output still has `start_time` unchanged
- `test_measure_validation_attached` — output dicts include `measure_validation` key

**Execution Constraints:**
- No audio files — all tests use synthetic grid and event construction
- Import helpers from `tests.unit.test_meter` for beat time generation (avoids duplication)
- All tests must run under 2 seconds total

**Output Request:**
Return ONLY `tests/unit/test_quantizer.py`.

---

**Complete implementation order for Plan 04:**

```
P04-A  duration_mapper.py     (no deps)
P04-B  meter.py               (deps: duration_mapper, madmom/librosa)
P04-C  quantizer.py           (deps: duration_mapper, meter, schema.events)
P04-D  beat_tracker.py        (deps: meter)
P04-E  main.py additions      (deps: beat_tracker, meter, quantizer)
P04-F  notebook update        (deps: beat_tracker)

T04-A  test_duration_mapper   (deps: duration_mapper only)
T04-B  test_meter             (deps: meter)
T04-C  test_quantizer         (deps: quantizer, meter, schema.events)
```
