# Plan 05 — Key, Scale, Chord and Harmonic Analysis

## Motive

Key detection already exists in MWTN (Krumhansl-Schmuckler via librosa). Complete score and solfa generation require a stronger harmonic context:

- **Solfa** depends on the active tonal center at every note (Plan 06)
- **Chord notation** requires chord events aligned to musical time (Plan 07)
- **Transposition** requires functionally correct relationships, not just pitch offsets
- **Local key changes** (modulations) affect notation spelling throughout a song

---

## Process

### 1. Audit existing key detection
- Review `backend/audio/key_detection.py` (Krumhansl-Schmuckler)
- Document what it currently returns and where it's consumed

### 2. Define a canonical key object

```json
{
  "tonic": "G",
  "mode": "major",
  "confidence": 0.83,
  "analysis_start_s": 0.0,
  "analysis_end_s": null,
  "source": "krumhansl_schmuckler",
  "manually_overridden": false
}
```

Supported modes: `major`, `minor`, `dorian`, `mixolydian`, `phrygian` (expand later as needed)

### 3. Support local key changes / modulations

Represent key as a **time-varying map**, not a single global value:

```json
{
  "key_map": [
    { "start_s": 0.0,  "end_s": 64.2, "tonic": "C", "mode": "major", "confidence": 0.91 },
    { "start_s": 64.2, "end_s": null,  "tonic": "A", "mode": "minor", "confidence": 0.78 }
  ]
}
```

For simple songs, the key map has one entry.

### 4. Open-source chord detection options

#### Option A — Chordino / NNLS-Chroma (Vamp plugin via sonic-annotator)
Requires Vamp host; complex setup. Not recommended for v1.

#### Option B — librosa chroma + rule-based chord templates ⭐ Recommended for v1
```python
import librosa
chroma = librosa.feature.chroma_cqt(y=audio, sr=sr)
# Template-match against major/minor triads
```
- Produces chord candidates (root + quality) with confidence
- Fast, no additional dependencies
- Quality: adequate for simple pop/rock harmonic analysis

#### Option C — autochord
```bash
pip install autochord
```
- Neural chord recognition, supports 170+ chord types
- MIT license
- Small model (~20 MB)
- Better than template matching for complex chords

#### Option D — chord-extractor (wrapper around Chordino)
Requires Vamp plugins — skip for v1.

**Recommendation:** Use autochord as primary, librosa chroma as fallback if autochord unavailable.

### 5. Define a chord event structure

```json
{
  "event_type": "chord",
  "root": "G",
  "quality": "major",
  "extensions": ["7"],
  "alteration": null,
  "inversion": 0,
  "bass_note": "G",
  "start_time": 4.0,
  "end_time": 6.0,
  "beat_aligned_start": { "measure": 2, "beat": 1 },
  "confidence": 0.87,
  "source_model": "autochord_0.1.0"
}
```

### 6. Chord detection pipeline
- Run chord detection on the **full mix** (better harmonic content than isolated stems)
- Optionally validate against piano/guitar stems if available
- Align detected chords to the beat grid from Plan 04
- Report chord candidates (top 2) when confidence is below threshold (< 0.6)

### 7. Enharmonic spelling
Store the enharmonic decision separately from raw MIDI pitch:
- `midi_pitch: 70` → could be `Bb` or `A#`
- Resolve based on key context: in F major → `Bb`; in B major → `A#`
- Store `"spelled_pitch": "Bb"` as a separate field

### 8. User correction of key and chords
- `PATCH /api/songs/{song_id}/key` — override global or local key
- `PATCH /api/songs/{song_id}/chords/{chord_id}` — override individual chord
- Override is stored separately from model output; original preserved
- Correction triggers recomputation of dependent solfa (Plan 06)

### 9. Recompute solfa on key change
When the key map changes (user override or re-analysis):
- Mark all solfa events derived from that key range as stale
- Recompute solfa asynchronously

---

## Files to Create / Modify

```
backend/
  audio/
    chord_detection.py    # chord detection pipeline (autochord + librosa fallback)
    harmonic_context.py   # key map builder + enharmonic spelling resolver
```

Modify:
- `backend/audio/key_detection.py` — extend to produce key_map (time-varying), not just global key
- `backend/main.py` — add chord endpoints; add key override endpoint
- `backend/schema/events.py` — add ChordEvent and KeyEvent models (from Plan 01)
- `colab/mwtn_notebook.ipynb` — add autochord install cell + chord detection cell

---

## Colab / Mobile Data Implications

| Action | Data Cost | Notes |
|---|---|---|
| `pip install autochord` | ~30 MB | One-time per session; small neural model |
| Chord detection inference | Negligible | Runs on full-mix audio |

---

## Expected Results

- MWTN knows not only the global key but the active tonal context throughout a song
- Chord charts can be generated and exported
- Solfa uses the correct tonic and scale at every note
- Transpositions preserve functional harmonic relationships
- Users can correct harmonic analysis without re-running separation

---

## Acceptance Criteria

- [ ] Global key is represented as a key_map with confidence
- [ ] Chord events align to beat grid positions
- [ ] Key changes / modulations can be represented in the key_map
- [ ] User key override triggers dependent solfa recomputation
- [ ] Chord confidence is visible in the chord event structure
- [ ] Enharmonic spelling uses key context to choose accidentals
- [ ] Existing key detection endpoint remains backward-compatible
