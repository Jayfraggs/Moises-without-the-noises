# Plan 01 — Musical Intelligence Architecture and Data Contracts

## Motive

MWTN already performs audio separation and several independent analysis operations. The next major capability is turning those outputs into a **coherent, versioned musical representation** that can feed notation, MIDI, solfa, chord analysis, and future editing features without coupling any of them together.

No single output format — not MuseScore, not MIDI, not MusicXML, not solfa — should become the canonical source of truth. The canonical representation must be a model-independent collection of musical events and metadata. Every output format is derived from it.

This prevents tight coupling to any one transcription model and allows better models to be introduced later without rewriting the frontend or score-generation layer.

---

## Process

### 1. Audit existing data flow
- Review `manifest.json` structure, existing `notes_<stem>.json`, `lyrics.json`, `beats.json`, `key.json`
- Map every field currently produced and consumed
- Identify which fields are authoritative vs derived

### 2. Define a versioned MusicalEvent model
Each event contains at minimum:

| Field | Type | Unit / Notes |
|---|---|---|
| `event_id` | string | UUID or deterministic hash |
| `track_id` | string | Ties to stem/instrument |
| `event_type` | enum | `note`, `rest`, `chord`, `drum_hit`, `lyric`, `beat`, `downbeat`, `section` |
| `start_time` | float | Seconds from audio start |
| `end_time` | float | Seconds (or null for instantaneous) |
| `midi_pitch` | int \| null | 0–127; null for non-pitched events |
| `frequency_hz` | float \| null | Raw detected frequency |
| `velocity` | int \| null | 0–127 MIDI velocity |
| `confidence` | float | [0.0, 1.0] |
| `source_model` | string | e.g. `"basic_pitch_0.3.1"` |
| `quantized_position` | object \| null | Beat/measure position; null until quantized |
| `schema_version` | string | e.g. `"1.0"` |

### 3. Define separate sub-types for each event category
- **NoteEvent**: pitch, duration, MIDI pitch, frequency, velocity, confidence, expressive pitch curve (optional)
- **RestEvent**: duration, quantized duration
- **ChordEvent**: root, quality, extensions, inversion, bass note, confidence, beat-aligned start/end
- **DrumHitEvent**: drum type (kick, snare, hi-hat, etc.), velocity, confidence
- **LyricEvent**: word text, syllable text, word index, syllable index, alignment confidence
- **BeatEvent**: beat number within measure, downbeat flag, tempo at this beat (BPM)
- **KeyEvent**: tonic, mode, confidence, analysis range (start/end time)
- **TempoEvent**: BPM, confidence, time range
- **SectionEvent**: label (intro, verse, chorus, bridge, outro), start/end time, confidence

### 4. Define the project-level manifest (extends existing manifest.json)

New fields to add (backward-compatible additions):

```json
{
  "schema_version": "1.0",
  "source_hash": "<sha256 of original audio>",
  "separation_engine": { "name": "demucs", "model": "htdemucs_6s", "version": "4.0.1" },
  "transcription_runs": [],
  "analysis_settings": {},
  "artifacts": {},
  "created_at": "<ISO8601>",
  "updated_at": "<ISO8601>",
  "quality_summary": {}
}
```

All existing fields are preserved unchanged.

### 5. Define an artifact registry
Every generated file (MIDI, MusicXML, JSON events, solfa, lyrics alignment) is registered as:

```json
{
  "artifact_id": "<uuid>",
  "artifact_type": "musicxml | midi | events_json | solfa | lyrics_alignment | beats | key",
  "file_path": "<relative path inside song folder>",
  "source_run_id": "<transcription run that produced it>",
  "schema_version": "1.0",
  "model": "<producing model>",
  "config_hash": "<hash of config used>",
  "created_at": "<ISO8601>",
  "is_stale": false
}
```

### 6. Establish explicit units throughout the codebase
- Audio time → **seconds** (float)
- MIDI pitch → **integer 0–127**
- Frequency → **Hz** (float)
- Tempo → **BPM** (float)
- Confidence → **[0.0, 1.0]** (float)
- Musical positions → **beat + subdivision** within measure (separate from raw time)
- PPQ for MIDI export → **480 ticks per quarter note** (standard)

### 7. Schema versioning and migration utilities
- Every file produced by mwtn embeds `"schema_version"`
- A migration registry maps old schema versions to upgrade functions
- The backend refuses to load files with unknown schema versions and returns a clear error

### 8. Add schema validation at all API boundaries
- Use **Pydantic v2** models for all request/response bodies
- Validate incoming manifests on `POST /api/import`
- Validate event payloads before writing to disk

### 9. Backward compatibility
- Existing `notes_<stem>.json`, `beats.json`, `key.json`, `lyrics.json` continue to load
- A one-time migration utility converts them to the new event format on first access
- Original files are preserved (never overwritten)

---

## Explicit Units Reference (put in `backend/schema/units.py`)

```python
# Canonical unit definitions — referenced by all backend modules
AUDIO_TIME_UNIT = "seconds"          # float
MIDI_PITCH_RANGE = (0, 127)          # int
FREQUENCY_UNIT = "hz"                # float
TEMPO_UNIT = "bpm"                   # float
CONFIDENCE_RANGE = (0.0, 1.0)        # float [0,1]
MIDI_PPQ = 480                       # ticks per quarter note
```

---

## Files to Create

```
backend/
  schema/
    __init__.py
    units.py           # canonical unit constants
    events.py          # Pydantic models for all MusicalEvent sub-types
    manifest.py        # extended Pydantic manifest model
    artifacts.py       # artifact registry model
    migrations.py      # schema version migration utilities
    validation.py      # validators for API boundary checks
```

---

## Expected Results

- MWTN has one canonical internal musical representation
- All existing features continue operating without modification
- Future transcription models can be swapped without changing the UI contract
- Every generated result is traceable to its model and configuration
- The system can detect stale artifacts and regenerate them
- Data contracts are explicit enough for both human developers and AI coding agents

---

## Acceptance Criteria

- [ ] A representative song can be fully described by the new schema
- [ ] Existing songs load without losing existing analysis data
- [ ] Schema validation rejects malformed musical events with a clear error
- [ ] Schema version is recorded in every project manifest
- [ ] At least one existing `notes_<stem>.json` result can be converted to the new event format
- [ ] Every generated artifact records its source run and configuration
- [ ] No existing API endpoint breaks
