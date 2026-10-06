---

## PLAN 05 — Agent Prompt Suite + Tests + UI + Scripts
### Key, Scale, Chord and Harmonic Analysis

Seven implementation prompts, three test prompts, one UI prompt, one scripts prompt.

**Prerequisite:** Plans 01–04 complete.

---

### [P05-A] Create `backend/audio/harmonic_context.py` — Key Map and Enharmonic Spelling

**Target File:** `backend/audio/harmonic_context.py`

**Context:** MWTN's existing `key_detection.py` returns a single global key string (`"C major"`). Plan 05 extends this into a time-varying `key_map` — a list of `KeyEvent` objects each covering a time range — and adds an enharmonic spelling resolver that picks the correct accidental for a given pitch class based on the active key. Both are prerequisite inputs for the solfa engine (Plan 06) and MusicXML export (Plan 07).

**Objective:**
Create the harmonic context module: key map construction from segmented analysis, active-key lookup, and enharmonic spelling resolution.

**Technical Specifications:**

**Pitch class tables:**
```python
# Pitch class to note name, no accidentals
PITCH_CLASS_TO_NAME = {0:"C",1:"C#",2:"D",3:"D#",4:"E",5:"F",6:"F#",7:"G",8:"G#",9:"A",10:"A#",11:"B"}

# Enharmonic equivalents: pitch_class → {context: preferred_name}
ENHARMONIC_MAP: dict[int, dict[str, str]] = {
    1:  {"sharps": "C#",  "flats": "Db"},
    3:  {"sharps": "D#",  "flats": "Eb"},
    6:  {"sharps": "F#",  "flats": "Gb"},
    8:  {"sharps": "G#",  "flats": "Ab"},
    10: {"sharps": "A#",  "flats": "Bb"},
}

# Keys that prefer flats (circle of fifths, flat side)
FLAT_KEYS = {"F","Bb","Eb","Ab","Db","Gb","Cb","D","G","Bf","Gm","Cm","Fm","Bbm","Ebm","Abm"}

# Scale degrees for each mode (semitones from tonic)
SCALE_INTERVALS: dict[str, list[int]] = {
    "major":      [0,2,4,5,7,9,11],
    "minor":      [0,2,3,5,7,8,10],
    "dorian":     [0,2,3,5,7,9,10],
    "mixolydian": [0,2,4,5,7,9,10],
    "phrygian":   [0,1,3,5,7,8,10],
}
```

`note_name_to_pitch_class(name: str) -> int`:
```python
"""
Map a note name string to pitch class (0=C, 1=C#/Db, ..., 11=B).
Handles: "C", "C#", "Db", "F#", "Bb", "Ab", etc.
Raises ValueError on unrecognized input.
"""
```
Mapping:
```python
_NAME_MAP = {
    "C":0,"C#":1,"Db":1,"D":2,"D#":3,"Eb":3,"E":4,"Fb":4,"F":5,"F#":6,
    "Gb":6,"G":7,"G#":8,"Ab":8,"A":9,"A#":10,"Bb":10,"B":11,"Cb":11,"B#":0,
}
```

`get_key_preference(tonic: str) -> str`:
```python
"""Return "flats" or "sharps" based on the key tonic."""
return "flats" if tonic in {"F","Bb","Eb","Ab","Db","Gb"} else "sharps"
```

`spell_pitch(midi_pitch: int, tonic: str, mode: str) -> str`:
```python
"""
Given a MIDI pitch, return the spelled note name appropriate for the active key.
e.g. midi_pitch=70, tonic="F", mode="major" → "Bb"
     midi_pitch=70, tonic="B", mode="major" → "A#"
"""
pitch_class = midi_pitch % 12
if pitch_class not in ENHARMONIC_MAP:
    return PITCH_CLASS_TO_NAME[pitch_class]  # no ambiguity
pref = get_key_preference(tonic)
return ENHARMONIC_MAP[pitch_class][pref]
```

`get_scale_degrees(tonic: str, mode: str) -> list[int]`:
```python
"""Return list of pitch classes in the scale, in order."""
tonic_pc = note_name_to_pitch_class(tonic)
intervals = SCALE_INTERVALS.get(mode, SCALE_INTERVALS["major"])
return [(tonic_pc + i) % 12 for i in intervals]
```

`is_chromatic(midi_pitch: int, tonic: str, mode: str) -> bool`:
```python
"""Return True if the pitch is not in the diatonic scale for this key."""
scale_pcs = get_scale_degrees(tonic, mode)
return (midi_pitch % 12) not in scale_pcs
```

`KeyMapEntry` — dataclass:
```python
@dataclass
class KeyMapEntry:
    tonic: str
    mode: str
    confidence: float
    start_s: float
    end_s: float | None          # None = until end of audio
    source: str = "krumhansl_schmuckler"
    manually_overridden: bool = False

    def to_dict(self) -> dict: ...
    def covers_time(self, time_s: float) -> bool:
        return self.start_s <= time_s and (self.end_s is None or time_s < self.end_s)
```

`KeyMap` — dataclass:
```python
@dataclass
class KeyMap:
    entries: list[KeyMapEntry]
    schema_version: str = "1.0"

    def get_key_at(self, time_s: float) -> KeyMapEntry:
        """Return the active key entry at a given time. Falls back to first entry."""
        for entry in reversed(self.entries):
            if entry.covers_time(time_s):
                return entry
        return self.entries[0]  # fallback

    def spell_pitch_at(self, midi_pitch: int, time_s: float) -> str:
        """Spell a pitch using the active key at time_s."""
        entry = self.get_key_at(time_s)
        return spell_pitch(midi_pitch, entry.tonic, entry.mode)

    def to_dict(self) -> dict: ...

    @classmethod
    def from_dict(cls, data: dict) -> "KeyMap": ...

    @classmethod
    def from_single_key(cls, tonic: str, mode: str, confidence: float, source: str = "krumhansl_schmuckler") -> "KeyMap":
        """Convenience constructor from a global key."""
        return cls(entries=[KeyMapEntry(tonic=tonic, mode=mode, confidence=confidence, start_s=0.0, end_s=None, source=source)])
```

`build_key_map_from_segments(
    audio_path: str | Path,
    segment_duration_s: float = 30.0,
) -> KeyMap`:
```python
"""
Analyze key in overlapping segments to detect modulations.
Uses librosa Krumhansl-Schmuckler on each segment.
Returns KeyMap with one entry per detected segment (merged when consecutive segments share the same key).
"""
```
Implementation:
1. Load audio: `y, sr = librosa.load(str(audio_path), sr=None, mono=True)`
2. Slide a window of `segment_duration_s` with 50% overlap across the audio
3. For each segment: `chromagram = librosa.feature.chroma_cqt(y=segment, sr=sr)` → `librosa.key_time_signatures()` equivalent (use the chroma correlation approach from existing `key_detection.py`)
4. For each segment, determine tonic + mode + confidence (reuse logic from `backend/audio/key_detection.py`)
5. Merge consecutive segments with the same `tonic + mode`
6. Return `KeyMap`

`load_or_build_key_map(audio_path: Path, cache_path: Path, force: bool = False) -> KeyMap`:
```python
"""Load from cache_path (key.json) if exists and new-format; otherwise build and cache."""
```
- If cache exists and has `"key_map"` field → `KeyMap.from_dict(data)`
- If cache exists but only has legacy `"key"` string → `KeyMap.from_single_key(...)` (migrate in-place)
- If no cache or `force=True` → call `build_key_map_from_segments` → write to `cache_path`

Write format (`key.json`):
```json
{
  "schema_version": "2.0",
  "key_map": [...],
  "key": "C major",
  "confidence": 0.91
}
```
Always include legacy `"key"` and `"confidence"` fields for backward compatibility.

**Execution Constraints:**
- All `librosa` at module top level (always available)
- `note_name_to_pitch_class` raises `ValueError` on unrecognized input — never silently return 0
- `KeyMap.from_dict` must handle both legacy format (`{"key": "C major"}`) and new format (`{"key_map": [...]}`)
- `build_key_map_from_segments` handles audio shorter than one segment duration (just analyzes the whole file as one segment)
- Do not modify `backend/audio/key_detection.py` — it remains the backward-compat endpoint handler

**Output Request:**
Return ONLY `backend/audio/harmonic_context.py`.

---

### [P05-B] Create `backend/audio/chord_detection.py` — Chord Detection Pipeline

**Target File:** `backend/audio/chord_detection.py`

**Context:** Chord detection runs on the full mix (or a mix stem if available) and produces `ChordEvent` objects aligned to the beat grid from Plan 04. The primary engine is autochord (MIT, neural, ~20 MB); the fallback is librosa chroma with rule-based template matching. The module is self-contained and swaps transparently between engines.

**Objective:**
Implement chord detection with autochord (primary) and librosa chroma (fallback), producing beat-aligned `ChordEvent` objects.

**Technical Specifications:**

**Chord quality normalization** — autochord returns strings like `"C:maj"`, `"G:min"`, `"F:7"`. Parse these:
```python
def parse_chord_label(label: str) -> tuple[str, str, list[str]]:
    """
    Parse autochord chord label into (root, quality, extensions).
    "C:maj"   → ("C", "major", [])
    "G:min"   → ("G", "minor", [])
    "F:7"     → ("F", "dominant7", ["7"])
    "Bb:maj7" → ("Bb", "major7", ["7"])
    "N"       → ("N", "none", [])   # no chord / silence
    """
```

Quality mapping:
```python
QUALITY_MAP = {
    "maj": "major", "min": "minor", "dim": "diminished",
    "aug": "augmented", "7": "dominant7", "maj7": "major7",
    "min7": "minor7", "dim7": "diminished7", "hdim7": "half-diminished7",
    "sus2": "sus2", "sus4": "sus4", "": "major",
}
```

**Librosa template fallback:**
```python
CHORD_TEMPLATES: dict[str, np.ndarray] = {
    # major triads: root, major third (4 semitones), perfect fifth (7 semitones)
    "major": np.array([1,0,0,0,1,0,0,1,0,0,0,0], dtype=float),
    # minor triads: root, minor third (3), perfect fifth (7)
    "minor": np.array([1,0,0,1,0,0,0,1,0,0,0,0], dtype=float),
}
```

`detect_chords_autochord(audio_path: str | Path) -> list[tuple[float, float, str, float]]`:
```python
"""
Returns list of (start_s, end_s, chord_label, confidence).
Raises ImportError if autochord not installed.
"""
# Lazy import
import autochord
chords = autochord.recognize(str(audio_path))
# autochord returns list of (start, end, chord_label) — no per-chord confidence
# Use 1.0 as confidence for all neural outputs (model doesn't expose it)
return [(float(c[0]), float(c[1]), c[2], 1.0) for c in chords]
```

`detect_chords_librosa(audio_path: str | Path, hop_length: int = 4096) -> list[tuple[float, float, str, float]]`:
```python
"""
Librosa chroma + template matching fallback.
Returns list of (start_s, end_s, chord_label, confidence).
"""
y, sr = librosa.load(str(audio_path), sr=None, mono=True)
chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length)
times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=hop_length)

results = []
for i, frame_chroma in enumerate(chroma.T):
    best_root, best_quality, best_score = None, None, -1.0
    for root_pc in range(12):
        rolled = np.roll(frame_chroma, -root_pc)
        for quality, template in CHORD_TEMPLATES.items():
            score = float(np.dot(rolled, template) / (np.linalg.norm(rolled) * np.linalg.norm(template) + 1e-8))
            if score > best_score:
                best_score, best_root, best_quality = score, root_pc, quality

    root_name = PITCH_CLASS_TO_NAME[best_root]
    label = f"{root_name}:{best_quality[:3]}"
    start_s = float(times[i])
    end_s = float(times[i+1]) if i+1 < len(times) else start_s + (hop_length / sr)
    results.append((start_s, end_s, label, best_score))

# Merge consecutive identical chords
return _merge_consecutive_chords(results)
```

`_merge_consecutive_chords(raw: list[tuple]) -> list[tuple]`:
- Merge adjacent entries with the same chord label
- Output: one entry per chord change

`align_chords_to_beat_grid(
    chord_segments: list[tuple[float, float, str, float]],
    grid: BeatGrid,
    key_map: KeyMap,
) -> list[ChordEvent]`:
```python
"""
Snap each chord's start_time to the nearest beat.
Build ChordEvent objects with beat_aligned_start populated.
Skip "N" (no chord) segments.
"""
```
For each segment:
1. Skip if label is `"N"` or `"N/A"` or similar silence label
2. Parse label → `root, quality, extensions`
3. Find nearest beat in grid: `beat_entry = grid.get_beat_at_time(start_s)`
4. Build `ChordEvent`:
   ```python
   ChordEvent(
       start_time=float(start_s),
       end_time=float(end_s),
       root=root,
       quality=quality,
       extensions=extensions,
       beat_aligned_start={"measure": beat_entry.measure_number, "beat": beat_entry.beat_in_measure},
       confidence=float(confidence),
       source_model=source_model_name,
       track_id="mix",
   )
   ```

`detect_chords(
    audio_path: str | Path,
    grid: BeatGrid,
    key_map: KeyMap,
) -> list[ChordEvent]`:
```python
"""
Top-level: try autochord, fall back to librosa.
"""
try:
    import autochord as _ac  # availability check
    raw = detect_chords_autochord(audio_path)
    source_model = f"autochord_{_ac.__version__}"
except ImportError:
    raw = detect_chords_librosa(audio_path)
    source_model = f"librosa_chroma_{librosa.__version__}"

return align_chords_to_beat_grid(raw, grid, key_map)
```

`load_or_detect_chords(
    audio_path: Path,
    cache_path: Path,
    grid: BeatGrid,
    key_map: KeyMap,
    force: bool = False,
) -> list[ChordEvent]`:
- If `cache_path` exists and not `force`: load `ChordEvent` list from JSON
- Otherwise: call `detect_chords()` → serialize to `cache_path` → return

**Execution Constraints:**
- `autochord` imports must be lazy (inside functions only)
- `librosa` at module top level
- Import `ChordEvent` from `backend.schema.events`; import `BeatGrid` from `backend.audio.meter`; import `KeyMap` from `backend.audio.harmonic_context`
- Import `PITCH_CLASS_TO_NAME` from `backend.audio.harmonic_context`
- `detect_chords_librosa` must not crash on mono audio shorter than 2 × hop_length
- "N" segments (silence / no chord) must be filtered before returning `ChordEvent` list

**Output Request:**
Return ONLY `backend/audio/chord_detection.py`.

---

### [P05-C] Extend `backend/audio/key_detection.py` — Backward-Compatible Key Map Integration

**Target File:** `backend/audio/key_detection.py` (modify existing)

**Context:** The existing `key_detection.py` endpoint handler is called by `GET /api/songs/{song_id}/key` and currently computes/returns a simple `{"key": "C major", "confidence": 0.83}`. This must be preserved exactly. The extension wraps the new `harmonic_context.py` functions to also populate `key_map` in the response, while keeping the existing dict fields identical.

**Objective:**
Augment the existing `analyze_key()` or equivalent function in `key_detection.py` to also return a `key_map` field, and update `key.json` writes to the new v2 format. Do not change any function signature or existing return key names.

**Technical Specifications:**

Read the existing file first. It likely has a function like:
```python
def detect_key(y: np.ndarray, sr: int) -> dict:
    # Krumhansl-Schmuckler logic
    return {"key": "C major", "confidence": 0.83}
```

**Changes to make:**

1. Add import at top:
   ```python
   from backend.audio.harmonic_context import KeyMap, note_name_to_pitch_class, get_key_preference
   ```

2. After computing the existing `key` and `confidence` fields, parse the key string and build a minimal `KeyMap`:
   ```python
   # Parse "C major" → tonic="C", mode="major"
   parts = key_string.rsplit(" ", 1)
   tonic, mode = parts[0], parts[1] if len(parts) == 2 else "major"
   key_map = KeyMap.from_single_key(tonic=tonic, mode=mode, confidence=confidence)
   ```

3. Add `key_map` to the return dict:
   ```python
   return {
       "key": key_string,            # UNCHANGED
       "confidence": confidence,     # UNCHANGED
       "key_map": key_map.to_dict(), # NEW — additive only
       "schema_version": "2.0",     # NEW — additive only
   }
   ```

4. When writing `key.json`, use the new format that `harmonic_context.load_or_build_key_map()` can read back.

**Execution Constraints:**
- The existing `"key"` and `"confidence"` keys in the return dict must be unchanged — do not rename or restructure them
- The `"key_map"` key is purely additive — old code that ignores unknown keys continues to work
- If parsing the key string fails for any reason, log a warning and set `key_map = KeyMap.from_single_key("C", "major", 0.0)` as safe default
- Do not rewrite the entire file — apply surgical additions only

**Output Request:**
Return the complete modified `backend/audio/key_detection.py`.

---

### [P05-D] Wire Plan 05 into `backend/main.py` — New Endpoints Only

**Target File:** `backend/main.py` (additive only)

**Context:** Four new endpoints for Plan 05. No existing route is modified.

**Objective:**
Add key map, chord detection, and override endpoints.

**Technical Specifications:**

**Required new imports:**
```python
from backend.audio.harmonic_context import KeyMap, load_or_build_key_map
from backend.audio.chord_detection import detect_chords, load_or_detect_chords
```

**New endpoint 1 — `GET /api/songs/{song_id}/keymap`:**
```python
@app.get("/api/songs/{song_id}/keymap")
async def get_key_map(song_id: str):
    """Return the full key map (time-varying key analysis)."""
    song_id = validate_song_id(song_id)
    audio_path = _find_source_audio(DATA_DIR / song_id)  # helper defined below
    cache_path = DATA_DIR / song_id / "key.json"
    key_map = load_or_build_key_map(audio_path, cache_path)
    return key_map.to_dict()
```

**New endpoint 2 — `PATCH /api/songs/{song_id}/key`:**
```python
@app.patch("/api/songs/{song_id}/key")
async def override_key(song_id: str, body: dict):
    """
    Override the detected key (globally or for a time range).
    Body: { "tonic": str, "mode": str, "start_s": float, "end_s": float | null }
    """
    song_id = validate_song_id(song_id)
    tonic = body.get("tonic")
    mode = body.get("mode", "major")
    start_s = float(body.get("start_s", 0.0))
    end_s = body.get("end_s")  # None = until end

    if not tonic:
        raise HTTPException(400, detail="'tonic' is required")
    if mode not in ("major","minor","dorian","mixolydian","phrygian"):
        raise HTTPException(400, detail=f"Unsupported mode: {mode!r}")

    cache_path = DATA_DIR / song_id / "key.json"
    key_map = load_or_build_key_map(_find_source_audio(DATA_DIR / song_id), cache_path)

    # Find or replace the entry covering start_s
    from backend.audio.harmonic_context import KeyMapEntry
    new_entry = KeyMapEntry(
        tonic=tonic, mode=mode, confidence=1.0,
        start_s=start_s, end_s=end_s,
        source="user_override", manually_overridden=True
    )
    # Insert: replace any entry that exactly matches start_s, else append
    key_map.entries = [e for e in key_map.entries if e.start_s != start_s]
    key_map.entries.append(new_entry)
    key_map.entries.sort(key=lambda e: e.start_s)

    # Write back
    import json as _json, os as _os
    data = key_map.to_dict()
    data["key"] = f"{tonic} {mode}"
    data["confidence"] = 1.0
    tmp = cache_path.with_suffix(".tmp")
    tmp.write_text(_json.dumps(data, indent=2))
    _os.replace(tmp, cache_path)

    return {"song_id": song_id, "key_map": key_map.to_dict(), "overridden": True}
```

**New endpoint 3 — `GET /api/songs/{song_id}/chords`:**
```python
@app.get("/api/songs/{song_id}/chords")
async def get_chords(song_id: str, force: bool = False):
    """Return chord events for a song. Detects if not cached."""
    song_id = validate_song_id(song_id)
    audio_path = _find_source_audio(DATA_DIR / song_id)
    cache_path = DATA_DIR / song_id / "chords.json"
    beats_path = DATA_DIR / song_id / "beats.json"
    key_path   = DATA_DIR / song_id / "key.json"

    if not beats_path.exists():
        raise HTTPException(422, detail="Beat analysis required first. Call POST /analyze/beats")

    from backend.audio.beat_tracker import load_or_analyze_beats
    grid = load_or_analyze_beats(audio_path, beats_path)
    key_map = load_or_build_key_map(audio_path, key_path)
    chords = load_or_detect_chords(audio_path, cache_path, grid, key_map, force=force)

    return {
        "song_id": song_id,
        "chord_count": len(chords),
        "chords": [c.model_dump(mode="json") for c in chords],
    }
```

**New endpoint 4 — `PATCH /api/songs/{song_id}/chords/{chord_id}`:**
```python
@app.patch("/api/songs/{song_id}/chords/{chord_id}")
async def override_chord(song_id: str, chord_id: str, body: dict):
    """
    Override a specific chord's root and/or quality.
    Body: { "root": str, "quality": str }
    Stores override in corrections.json (Plan 10 pattern).
    """
    song_id = validate_song_id(song_id)
    root = body.get("root")
    quality = body.get("quality")

    if not root and not quality:
        raise HTTPException(400, detail="Provide at least 'root' or 'quality' to override.")

    corrections_path = DATA_DIR / song_id / "corrections.json"
    import json as _json
    corrections = _json.loads(corrections_path.read_text()) if corrections_path.exists() else {"corrections": []}
    import uuid as _uuid
    from datetime import datetime as _dt
    corrections["corrections"].append({
        "correction_id": _uuid.uuid4().hex,
        "target_event_id": chord_id,
        "correction_type": "chord",
        "corrected_value": {"root": root, "quality": quality},
        "corrected_at": _dt.utcnow().isoformat() + "Z",
        "correction_source": "user",
    })
    corrections_path.write_text(_json.dumps(corrections, indent=2))
    return {"song_id": song_id, "chord_id": chord_id, "overridden": True}
```

**Helper function (add near top of endpoint section):**
```python
def _find_source_audio(song_dir: Path) -> Path:
    """Find the source audio file in a song directory. Raises 404 if absent."""
    source_dir = song_dir / "source"
    if source_dir.exists():
        files = list(source_dir.glob("original.*"))
        if files:
            return files[0]
    raise HTTPException(404, detail=f"No source audio found in {song_dir.name!r}. Import the song first.")
```

**Execution Constraints:**
- Additive only — no existing route modified
- `_find_source_audio` is a module-level helper, not a route
- chord override writes to `corrections.json` using the Plan 10 overlay pattern — this is intentional forward compatibility

**Output Request:**
Return the four new endpoint functions, the `_find_source_audio` helper, and their required imports as labeled code blocks. Do not return the full `main.py`.

---

### [P05-E] Update `colab/mwtn_notebook.ipynb` — Autochord Install + Chord Detection Cell

**Target File:** `colab/mwtn_notebook.ipynb` (additive)

**Context:** The notebook needs an autochord install cell and a chord + key analysis cell that produces `key.json` and `chords.json` in the expected format. These cells run after the beat tracking cells from Plan 04.

**Objective:**
Add three new notebook cells: autochord install, key map analysis, and chord detection.

**Technical Specifications:**

**Markdown cell (section header):**
```markdown
### Harmonic Analysis (Key Map + Chords)
Detects the key (with modulation support) and chord progressions.
**autochord** is the primary chord engine (~20 MB, MIT license).
Falls back to librosa chroma if autochord is unavailable.
Data cost: ~20 MB for autochord (Colab connection only).
```

**Code cell — Install autochord:**
```python
# Install autochord for neural chord recognition
# Data cost: ~20 MB — runs on Colab, not your mobile connection
print("Installing autochord...")
import subprocess
result = subprocess.run(["pip", "install", "autochord", "--quiet"], capture_output=True, text=True)
if result.returncode == 0:
    print("autochord installed.")
else:
    print(f"autochord install failed (will fall back to librosa): {result.stderr[:200]}")
```

**Code cell — Key map analysis:**
```python
# Key map analysis (time-varying key detection)
from pathlib import Path
from backend.audio.harmonic_context import load_or_build_key_map

AUDIO_PATH = Path(f"/content/mwtn/backend/data/{song_id}/source/original.mp3")
KEY_CACHE  = Path(f"/content/mwtn/backend/data/{song_id}/key.json")

print("Analyzing harmonic key structure...")
key_map = load_or_build_key_map(AUDIO_PATH, KEY_CACHE, force=True)

print(f"Key map entries: {len(key_map.entries)}")
for entry in key_map.entries:
    end_label = f"{entry.end_s:.1f}s" if entry.end_s else "end"
    print(f"  {entry.start_s:.1f}s → {end_label}: {entry.tonic} {entry.mode} (conf: {entry.confidence:.2f})")
```

**Code cell — Chord detection:**
```python
# Chord detection (autochord primary, librosa fallback)
from backend.audio.chord_detection import load_or_detect_chords
from backend.audio.beat_tracker import load_or_analyze_beats

BEATS_CACHE  = Path(f"/content/mwtn/backend/data/{song_id}/beats.json")
CHORDS_CACHE = Path(f"/content/mwtn/backend/data/{song_id}/chords.json")

grid    = load_or_analyze_beats(AUDIO_PATH, BEATS_CACHE)
key_map = load_or_build_key_map(AUDIO_PATH, KEY_CACHE)

print("Detecting chords...")
chords = load_or_detect_chords(AUDIO_PATH, CHORDS_CACHE, grid, key_map, force=True)
print(f"Chords detected: {len(chords)}")
if chords:
    print("First 5 chords:")
    for c in chords[:5]:
        print(f"  {c.start_time:.2f}s → {c.root} {c.quality} (conf: {c.confidence:.2f})")
```

**Output Request:**
Return the four cells as properly structured Jupyter notebook cell JSON objects (cell_type, source, metadata).

---

### [P05-F] Create `frontend/src/components/HarmonicAnalysis/` — Key and Chord UI Components

**Target Files:**
```
frontend/src/components/HarmonicAnalysis/
  KeyDisplay.jsx
  ChordChart.jsx
  HarmonicPanel.jsx
  HarmonicPanel.css
```

**Context:** Plan 05 gives MWTN a key map and chord event list. The UI must surface both in a dedicated Harmonic Analysis panel that fits within the existing dark DAW layout (dark mixing console aesthetic, system fonts, no external font CDN). The panel is synchronized to playback position — the active key and active chord highlight as the song plays.

**Objective:**
Create the harmonic analysis UI panel: a key display with override controls, a scrolling chord chart synchronized to playback, and a container panel that wires to the existing audio transport.

**Technical Specifications:**

**`KeyDisplay.jsx`:**

Props:
```javascript
{
  keyMap,        // array of { tonic, mode, confidence, start_s, end_s, manually_overridden }
  currentTime,   // float, seconds — from usePlaybackClock
  songId,        // string
  onKeyOverride, // callback(tonic, mode, start_s, end_s)
}
```

Behavior:
- Derive the active key entry from `keyMap` using `currentTime`
- Display: `[Tonic][Mode] • [Confidence%]` e.g. `C major • 91%`
- If `manually_overridden`, show a lock icon (🔒) beside the key name
- Show a dropdown `<select>` with all 12 notes for tonic override; a second `<select>` for mode (major / minor / dorian / mixolydian / phrygian)
- "Apply" button calls `onKeyOverride(tonic, mode, currentTime, null)` — overrides from current time to end
- If key map has > 1 entry, show a small pill for each entry below the main display: `"0s–64s: C major"`, `"64s–end: A minor"`

Styling rules (inline with `HarmonicPanel.css`):
- Background: `#1a1a1a` (matches DAW panel)
- Active key name: `font-size: 1.4rem; font-weight: 600; color: #e0e0e0`
- Confidence: `font-size: 0.75rem; color: #888`
- Override controls hidden behind a `[✏️ Override]` toggle button — don't clutter the default view
- Modulation pills: `font-size: 0.7rem; background: #2a2a2a; border-radius: 4px; padding: 2px 6px`

**`ChordChart.jsx`:**

Props:
```javascript
{
  chords,        // array of ChordEvent objects
  currentTime,   // float, seconds
  duration,      // float, total song duration in seconds
  onChordOverride, // callback(chordId, root, quality)
}
```

Behavior:
- Render chords as horizontal blocks on a timeline
- Each block width is proportional to chord duration (`(end_time - start_time) / duration * 100%`)
- Active chord (the one covering `currentTime`) is highlighted: brighter background + bottom border accent
- Chord label inside each block: `Root + quality abbreviation` — e.g. `C`, `Dm`, `G7`, `Fmaj`
- Quality abbreviation map:
  ```javascript
  const QUAL_ABBR = {
    major: "", minor: "m", diminished: "dim", augmented: "aug",
    dominant7: "7", major7: "maj7", minor7: "m7",
    "half-diminished7": "ø7", sus2: "sus2", sus4: "sus4",
  };
  ```
- Click a chord block → show a small inline override form (root select + quality select + Apply button)
- Low-confidence chords (`confidence < 0.6`): slightly muted background + dashed bottom border
- "No chord" regions (gaps) render as empty dark space

Styling:
- Timeline bar height: `52px`
- Font: `system-ui, sans-serif; font-size: 0.8rem; font-weight: 500`
- Active chord: `background: #2d4a6b; border-bottom: 2px solid #4a9eff`
- Normal chord: `background: #252525; border: 1px solid #333`
- Low-confidence chord: `background: #1f1f1f; border: 1px dashed #444`
- Quality color tinting via CSS custom properties on each block:
  - major: `--chord-hue: 210` (blue)
  - minor: `--chord-hue: 280` (purple)
  - dominant7: `--chord-hue: 30` (amber)
  - diminished: `--chord-hue: 0` (red)

**`HarmonicPanel.jsx`:**

Props:
```javascript
{ songId, currentTime, duration, isVisible }
```

State:
```javascript
const [keyMap, setKeyMap] = useState([]);
const [chords, setChords] = useState([]);
const [loading, setLoading] = useState(false);
const [error, setError] = useState(null);
const [analyzing, setAnalyzing] = useState(false);
```

On mount / songId change:
```javascript
useEffect(() => {
  fetchKeyMap();
  fetchChords();
}, [songId]);
```

`fetchKeyMap()`: `GET /api/songs/{songId}/keymap` → setKeyMap
`fetchChords()`: `GET /api/songs/{songId}/chords` → setChords(data.chords)

`handleAnalyze()`:
```javascript
// Trigger chord detection if not yet run
setAnalyzing(true);
await fetch(`/api/songs/${songId}/chords?force=true`);
await fetchChords();
setAnalyzing(false);
```

Layout:
```
┌─ Harmonic Analysis ────────────────────────────── [Analyze ▶] ─┐
│  Key: C major • 91% 🔒       [✏️ Override]                      │
│  [0s–end: C major]                                              │
├─────────────────────────────────────────────────────────────────┤
│  Chord Chart:                                                   │
│  [C    ][Am   ][F    ][G   ][C    ][Am  ][Dm  ][G7  ]          │
└─────────────────────────────────────────────────────────────────┘
```

When `chords` is empty and not loading, show:
```jsx
<div className="harmonic-empty">
  <p>No chord analysis yet.</p>
  <button onClick={handleAnalyze}>Detect Chords</button>
</div>
```

**`HarmonicPanel.css`** — all styles for the above three components. Use CSS custom properties for theming:
```css
.harmonic-panel {
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  padding: 12px 16px;
  font-family: system-ui, sans-serif;
}
```
Define all component classes here. No external CSS framework.

**Execution Constraints:**
- No external dependencies — no chart libraries, no CSS frameworks, no external font CDN
- `currentTime` is passed in from the parent via `usePlaybackClock` — do not implement a new clock inside this component
- All API calls use the base URL from `import { API_BASE } from '../../api'` (existing MWTN pattern)
- Active chord detection is a pure JS array scan — O(n) is fine for typical chord counts (<200)
- Override forms must call `PATCH /api/songs/{songId}/key` and `PATCH /api/songs/{songId}/chords/{chordId}` then refresh state

**Output Request:**
Return all four files: `KeyDisplay.jsx`, `ChordChart.jsx`, `HarmonicPanel.jsx`, `HarmonicPanel.css`.

---

### [P05-G] Update `run.ps1` and `activate.ps1`

**Target Files:** `run.ps1`, `activate.ps1`

**Context:** Plans 01–05 have introduced new Python modules, a new YAML config file, and new optional dependencies (`autochord`, `madmom`). The startup scripts need to reflect the new optional install hints and validate the new config file exists. The guiding principles from the existing scripts:
- No local model downloads (Colab-only)
- Clear separation between required and optional dependencies
- Mobile-data-aware messaging

**Objective:**
Update both scripts to reflect the expanded pipeline.

**Technical Specifications:**

**`activate.ps1` changes:**

1. Add a section after the existing venv activation that checks for new required packages:
```powershell
# --- Required packages check ---
Write-Host "Checking required packages..." -ForegroundColor Cyan
$required = @("fastapi", "uvicorn", "librosa", "soundfile", "pydantic", "pyyaml", "music21")
foreach ($pkg in $required) {
    $check = python -c "import $pkg" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Missing: $pkg — run: pip install $pkg" -ForegroundColor Yellow
    }
}
```

2. Add an optional packages section (informational only — do not install):
```powershell
# --- Optional packages (feature-gated, install manually if needed) ---
Write-Host ""
Write-Host "Optional packages (not required to start):" -ForegroundColor DarkGray
$optional = @{
    "basic_pitch"                    = "Polyphonic transcription (AMT) — pip install basic-pitch"
    "piano_transcription_inference"  = "High-quality piano transcription — pip install piano-transcription-inference"
    "madmom"                         = "Beat/downbeat tracking — pip install madmom"
    "autochord"                      = "Neural chord detection — pip install autochord"
    "adtlib"                         = "Drum transcription — pip install adtlib"
}
foreach ($mod in $optional.Keys) {
    $check = python -c "import $mod" 2>&1
    $status = if ($LASTEXITCODE -eq 0) { "✓ installed" } else { "✗ not installed" }
    Write-Host ("  [{0}] {1}" -f $status, $optional[$mod]) -ForegroundColor DarkGray
}
```

3. Check that `transcription_config.yaml` exists:
```powershell
$configPath = Join-Path $PSScriptRoot "backend\transcription_config.yaml"
if (-not (Test-Path $configPath)) {
    Write-Host ""
    Write-Host "Warning: transcription_config.yaml not found." -ForegroundColor Yellow
    Write-Host "         Transcription engine defaults will be used." -ForegroundColor Yellow
}
```

**`run.ps1` changes:**

1. Add health check banner after backend starts (give it 2 seconds to come up):
```powershell
Start-Sleep -Seconds 2
Write-Host ""
Write-Host "--- MWTN Health Check ---" -ForegroundColor Cyan
try {
    $health = Invoke-RestMethod -Uri "http://localhost:8000/api/health" -TimeoutSec 5
    Write-Host ("  Backend:    {0}" -f $health.status.ToUpper()) -ForegroundColor Green
    foreach ($check in $health.checks.PSObject.Properties) {
        $st = $check.Value.status
        $color = if ($st -eq "ok") { "Green" } elseif ($st -eq "not_installed") { "DarkGray" } else { "Yellow" }
        Write-Host ("  {0,-20} {1}" -f $check.Name, $st) -ForegroundColor $color
    }
} catch {
    Write-Host "  Could not reach backend health endpoint." -ForegroundColor Yellow
    Write-Host "  Backend may still be starting up." -ForegroundColor DarkGray
}
Write-Host "-------------------------" -ForegroundColor Cyan
Write-Host ""
```

2. Add a mobile data reminder banner:
```powershell
Write-Host "💡 Mobile data tip: Heavy processing runs on Google Colab, not locally." -ForegroundColor DarkCyan
Write-Host "   Only upload/download costs apply (~60-200 MB per song via Colab)." -ForegroundColor DarkGray
Write-Host ""
```

3. Update the Electron launch section to handle the case where the `electron/` directory doesn't have a built binary gracefully:
```powershell
$electronExe = Join-Path $PSScriptRoot "electron\node_modules\.bin\electron.cmd"
if (Test-Path $electronExe) {
    Write-Host "Launching Electron shell..." -ForegroundColor Cyan
    Start-Process -FilePath $electronExe -ArgumentList "." -WorkingDirectory (Join-Path $PSScriptRoot "electron")
} else {
    Write-Host "Electron not built — opening browser UI instead." -ForegroundColor DarkGray
    Start-Process "http://localhost:5173"
}
```

**Execution Constraints:**
- Both scripts must remain runnable on Windows PowerShell 5.1 and PowerShell 7+
- No `curl` — use `Invoke-RestMethod` for HTTP
- The optional package check is read-only and informational — it must never attempt to install anything
- `activate.ps1` changes are purely additive — existing venv activation logic is untouched
- `run.ps1` health check failure must be non-fatal (try/catch, warn and continue)

**Output Request:**
Return the complete updated `run.ps1` and `activate.ps1`.

---

Now the tests.

---

### [T05-A] Create `tests/unit/test_harmonic_context.py` — Harmonic Context Unit Tests

**Target File:** `tests/unit/test_harmonic_context.py`

**Context:** Pure unit tests for `backend/audio/harmonic_context.py`. No audio, no models. Tests cover pitch class mapping, enharmonic spelling, scale degree computation, and KeyMap logic.

**Technical Specifications:**

```python
pytestmark = pytest.mark.unit
```

**`TestNoteNameToPitchClass`**:
- `test_c_is_0` — `note_name_to_pitch_class("C") == 0`
- `test_c_sharp_is_1` — `note_name_to_pitch_class("C#") == 1`
- `test_db_is_1` — `note_name_to_pitch_class("Db") == 1` (enharmonic)
- `test_f_sharp_is_6` — `note_name_to_pitch_class("F#") == 6`
- `test_bb_is_10` — `note_name_to_pitch_class("Bb") == 10`
- `test_b_is_11` — `note_name_to_pitch_class("B") == 11`
- `test_unknown_raises` — `note_name_to_pitch_class("X")` → `ValueError`
- `test_all_12_pitch_classes_covered` — calling with every note in the map returns 0–11

**`TestSpellPitch`**:
- `test_c_major_uses_sharps` — `spell_pitch(61, "G", "major") == "C#"` (G major uses sharps)
- `test_f_major_uses_flats` — `spell_pitch(70, "F", "major") == "Bb"` (F major uses flats)
- `test_b_major_uses_sharps` — `spell_pitch(70, "B", "major") == "A#"`
- `test_unambiguous_pitch_unchanged` — `spell_pitch(60, "C", "major") == "C"` (C has no enharmonic issue)
- `test_natural_notes_unchanged` — D, E, F, G, A, B return their natural names regardless of key

**`TestGetScaleDegrees`**:
- `test_c_major_scale_degrees` — `get_scale_degrees("C", "major") == [0,2,4,5,7,9,11]`
- `test_a_minor_scale_degrees` — `get_scale_degrees("A", "minor") == [9,11,0,2,4,5,7]` (relative to A=9)
- `test_g_major_includes_f_sharp` — `6 in get_scale_degrees("G", "major")` (F# = pitch class 6)
- `test_scale_always_7_degrees` — every valid tonic + mode combo returns exactly 7 pitch classes

**`TestIsChromatic`**:
- `test_c_in_c_major_not_chromatic` — `is_chromatic(60, "C", "major") == False`
- `test_c_sharp_in_c_major_is_chromatic` — `is_chromatic(61, "C", "major") == True`
- `test_f_sharp_in_g_major_not_chromatic` — `is_chromatic(66, "G", "major") == False`

**`TestKeyMapEntry`**:
- `test_covers_time_within_range` — entry start=0.0, end=60.0: `covers_time(30.0) == True`
- `test_covers_time_at_start` — `covers_time(0.0) == True`
- `test_covers_time_at_end_exclusive` — `covers_time(60.0) == False`
- `test_covers_time_open_end` — entry with `end_s=None`: `covers_time(9999.0) == True`
- `test_to_dict_serializable` — `json.dumps(entry.to_dict())` does not raise

**`TestKeyMap`**:
- `test_from_single_key_creates_one_entry` — `KeyMap.from_single_key("C","major",0.9).entries` has length 1
- `test_get_key_at_returns_correct_entry` — two-entry map; query each range → correct entry returned
- `test_get_key_at_before_first_returns_first` — `get_key_at(-1.0)` returns first entry
- `test_spell_pitch_at_uses_active_key` — map C major (0–60s) then A minor (60s–end); `spell_pitch_at(70, 30.0) == "Bb"` (flat in C major range); `spell_pitch_at(70, 65.0)` may differ
- `test_from_dict_roundtrip` — `KeyMap.to_dict()` → `KeyMap.from_dict()` → same entries
- `test_from_dict_legacy_format` — `{"key": "G major", "confidence": 0.8}` → `KeyMap` with one entry, `tonic="G"`, `mode="major"`

**Output Request:**
Return ONLY `tests/unit/test_harmonic_context.py`.

---

### [T05-B] Create `tests/unit/test_chord_detection.py` — Chord Detection Unit Tests

**Target File:** `tests/unit/test_chord_detection.py`

**Context:** Unit tests for pure logic in `backend/audio/chord_detection.py`: the chord label parser, quality map, template matching logic, and chord merging. Integration tests with real audio are skipped when `autochord` is absent.

**Technical Specifications:**

```python
pytestmark = pytest.mark.unit
```

**`TestParseChordLabel`**:
- `test_major_triad` — `parse_chord_label("C:maj") == ("C", "major", [])`
- `test_minor_triad` — `parse_chord_label("G:min") == ("G", "minor", [])`
- `test_dominant_seventh` — `parse_chord_label("F:7")` → quality contains "dominant7" or "7"
- `test_major_seventh` — `parse_chord_label("Bb:maj7")` → root `"Bb"`, quality `"major7"`
- `test_no_chord_silence` — `parse_chord_label("N")` → root `"N"`, quality `"none"` or similar
- `test_root_name_preserved` — `parse_chord_label("Db:min")[0] == "Db"`
- `test_unknown_quality_has_fallback` — does not raise; returns something for unrecognized quality suffix

**`TestMergeConsecutiveChords`**:
- `test_same_chord_merges` — two adjacent segments with same label → one merged segment
- `test_different_chords_not_merged` — C then G → both preserved
- `test_empty_list_returns_empty` — `_merge_consecutive_chords([]) == []`
- `test_merged_duration_covers_both` — merged segment's end_s equals the last segment's end_s
- `test_three_same_merges_to_one` — C, C, C → one segment spanning all three

**`TestAlignChordsToGrid`** (uses synthetic BeatGrid from `test_meter.py` helpers):
- `test_chord_gets_beat_aligned_start` — chord starting near beat 1 measure 2 → `beat_aligned_start == {"measure": 2, "beat": 1}` or close
- `test_silence_segments_filtered` — `"N"` segment not in output chord list
- `test_output_is_chord_events` — all output objects are `ChordEvent` instances
- `test_confidence_preserved` — confidence from raw segment carried into `ChordEvent.confidence`

**Integration test (auto-skip if autochord absent):**
```python
autochord = pytest.importorskip("autochord", reason="autochord not installed")
pytestmark_integration = pytest.mark.integration
```
- `test_detect_chords_autochord_returns_list(c_major_scale_path)` — basic smoke test: returns list (may be empty for a scale)
- `test_detect_chords_librosa_fallback(c_major_scale_path)` — always runs; `detect_chords_librosa()` returns non-empty list

**Output Request:**
Return ONLY `tests/unit/test_chord_detection.py`.

---

### [T05-C] Create `tests/integration/test_harmonic_pipeline.py` — End-to-End Harmonic Integration Tests

**Target File:** `tests/integration/test_harmonic_pipeline.py`

**Context:** Integration tests that exercise the full Plan 05 pipeline on synthetic audio: key map build → chord detection → beat alignment. Uses `c_major_scale_path` and `silence_path` from conftest. These tests run locally — no Colab, no optional models required for the core path (librosa fallback always runs).

**Technical Specifications:**

```python
pytestmark = pytest.mark.integration
```

**`TestKeyMapFromAudio`**:
- `test_c_major_scale_key_detection(c_major_scale_path, tmp_path)`:
  ```python
  cache = tmp_path / "key.json"
  key_map = load_or_build_key_map(c_major_scale_path, cache)
  assert len(key_map.entries) >= 1
  active = key_map.get_key_at(0.0)
  # C major scale should detect C as tonic (may not be perfect — accept C or Am)
  assert active.tonic in ("C", "A")  # relative major/minor ambiguity is expected
  assert active.mode in ("major", "minor")
  assert 0.0 <= active.confidence <= 1.0
  ```

- `test_key_map_caches_on_second_call(c_major_scale_path, tmp_path)`:
  ```python
  cache = tmp_path / "key.json"
  km1 = load_or_build_key_map(c_major_scale_path, cache)
  km2 = load_or_build_key_map(c_major_scale_path, cache)  # should load from cache
  assert km1.entries[0].tonic == km2.entries[0].tonic
  ```

- `test_key_cache_file_written(c_major_scale_path, tmp_path)`:
  ```python
  cache = tmp_path / "key.json"
  load_or_build_key_map(c_major_scale_path, cache)
  assert cache.exists()
  data = json.loads(cache.read_text())
  assert "key_map" in data
  assert "key" in data  # legacy field present
  ```

- `test_silence_produces_a_key_entry(silence_path, tmp_path)`:
  ```python
  # Silence should not crash; may return a low-confidence key
  cache = tmp_path / "key.json"
  key_map = load_or_build_key_map(silence_path, cache)
  assert len(key_map.entries) >= 1  # at least a fallback entry
  ```

**`TestChordDetectionPipeline`**:
- `test_librosa_fallback_runs_on_c_major(c_major_scale_path, tmp_path)`:
  ```python
  from tests.unit.test_meter import make_beat_times, make_downbeat_times
  from backend.audio.meter import build_beat_grid, TimeSig
  beat_times = make_beat_times(120.0, 4.0)
  dbt = make_downbeat_times(beat_times, 4)
  grid = build_beat_grid(beat_times, dbt, TimeSig(4, 4))
  key_map = KeyMap.from_single_key("C", "major", 0.9)
  chords = detect_chords(c_major_scale_path, grid, key_map)
  # A C major scale may not produce strong chord segments — accept empty or non-empty
  assert isinstance(chords, list)
  assert all(hasattr(c, "root") for c in chords)
  ```

- `test_chord_events_have_required_fields(c_major_scale_path, tmp_path)`:
  ```python
  # All ChordEvents have required schema fields
  for chord in chords:
      assert chord.root
      assert chord.quality
      assert 0.0 <= chord.confidence <= 1.0
      assert chord.start_time >= 0.0
  ```

- `test_chord_cache_written(c_major_scale_path, tmp_path)`:
  ```python
  cache = tmp_path / "chords.json"
  load_or_detect_chords(c_major_scale_path, cache, grid, key_map)
  assert cache.exists()
  ```

**Output Request:**
Return ONLY `tests/integration/test_harmonic_pipeline.py`.

---

**Complete implementation order for Plan 05:**

```
P05-A  harmonic_context.py          (no ML deps)
P05-B  chord_detection.py           (librosa always; autochord optional)
P05-C  key_detection.py (modify)    (additive augmentation)
P05-D  main.py additions            (4 new endpoints)
P05-E  notebook update              (3 cells)
P05-F  HarmonicAnalysis/ UI         (4 frontend files)
P05-G  run.ps1 + activate.ps1       (2 script updates)

T05-A  test_harmonic_context        (pure unit, no audio)
T05-B  test_chord_detection         (unit + optional integration)
T05-C  test_harmonic_pipeline       (integration, librosa path always runs)
```

