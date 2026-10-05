# Plan 04 — Beat, Tempo, Meter and Musical Quantization

## Motive

Raw transcription gives events in seconds. Professional notation requires musical positions: measures, beats, subdivisions, note durations, rests, and time signatures. MWTN needs a dedicated **rhythm layer** between raw transcription (Plan 02) and any notation output (Plan 07).

The existing BPM detector (librosa `beat_track`) gives a single tempo value and beat grid. This plan expands it to handle tempo changes, downbeat detection, time-signature detection, and full quantization to notation-ready positions.

---

## Process

### 1. Preserve existing BPM detector as one analysis source
- Keep `backend/audio/bpm.py` and its cached `beats.json`
- Use its output as the initial tempo/beat input

### 2. Add full beat tracking (beat + downbeat)
Use **madmom** or **librosa** `beat_tracker` depending on availability:

**Option A — madmom** (preferred for downbeat detection)
```bash
pip install madmom
```
- `madmom.features.beats.RNNBeatProcessor` — beat positions
- `madmom.features.downbeats.RNNDownBeatProcessor` — downbeat + time signature

**Option B — librosa** (already installed, lighter)
```python
tempo, beats = librosa.beat.beat_track(y=audio, sr=sr, units='time')
```
- No downbeat detection; approximate from beat regularity

**Recommendation:** Use madmom for the Colab pipeline (GPU available) and librosa as the CPU fallback.

### 3. Detect downbeats
Downbeats are essential for assigning measure numbers to beats.
- Primary: madmom `RNNDownBeatProcessor`
- Fallback: first beat of every N-beat group (N = detected time signature numerator)

### 4. Support tempo changes
Rather than one global BPM, build a **tempo map**:

```json
{
  "tempo_map": [
    { "beat_index": 0,  "time_s": 0.0,  "bpm": 120.0 },
    { "beat_index": 64, "time_s": 32.1, "bpm": 132.0 }
  ]
}
```

### 5. Detect or allow user selection of time signature
- Primary detector: madmom `RNNDownBeatProcessor` returns meter estimate
- Supported automatically: 2/4, 3/4, 4/4, 6/8
- Fallback: default to 4/4 with a UI flag indicating it was assumed
- User can override time signature in the UI (see Plan 11)

### 6. Build a beat grid from detected timing
A beat grid is the mapping between:
- `beat_index` (integer, 0-based)
- `time_s` (float, seconds)
- `measure_number` (integer, 1-based)
- `beat_in_measure` (integer, 1-based)
- `subdivision_resolution` (ticks per beat, default 24)

### 7. Quantization
Map each raw note `start_time` and `end_time` onto beat grid positions.

**Configurable quantization strength:**
- `strict` — snap to nearest grid point regardless of deviation
- `humanized` (default) — only snap if within a configurable tolerance window (default ±15% of beat duration); leave expressive timing if beyond tolerance
- `off` — preserve raw timing, add quantized position as advisory only

**Never destructively overwrite raw timing.** Always store both:
```json
{
  "start_time": 1.243,
  "end_time":   1.872,
  "quantized_start": { "measure": 1, "beat": 3, "subdivision": 0 },
  "quantized_end":   { "measure": 1, "beat": 4, "subdivision": 0 },
  "quantized_duration_name": "quarter",
  "quantization_confidence": 0.91
}
```

### 8. Duration normalization
Recognize standard notation durations from quantized lengths:

| Duration name | Subdivisions (at 24 ppb) |
|---|---|
| whole | 96 |
| half | 48 |
| dotted half | 72 |
| quarter | 24 |
| dotted quarter | 36 |
| eighth | 12 |
| dotted eighth | 18 |
| sixteenth | 6 |
| thirty-second | 3 |
| quarter triplet | 16 |
| eighth triplet | 8 |

### 9. Ties for notes crossing bar lines
Any note whose quantized position begins in one measure and ends in the next is split at the barline into two tied notes.

### 10. Triplet detection
If a group of 3 notes fits within one beat with near-equal spacing and the combined duration equals 2/3 of a beat:
- Flag as likely triplet
- Record `"tuplet": { "type": 3, "in_beats": 2, "confidence": 0.85 }`

### 11. Rest generation
After quantization, gaps between consecutive notes on the same voice are filled with rest events.

### 12. Measure validation
After quantization, each measure's note+rest durations must sum to exactly the time-signature total. If they don't:
- Flag the measure as `"validation_error": "rhythmic_total_mismatch"`
- Allow downstream systems to handle gracefully

### 13. Manual correction path
- Time signature can be overridden via `PATCH /api/songs/{song_id}/meter`
- Individual note quantization can be overridden in Plan 10 (confidence/review)

---

## Output Format (extends MusicalEvent from Plan 01)

Add to every `NoteEvent` and `RestEvent`:

```json
{
  "quantized_start": {
    "measure": 2,
    "beat": 1,
    "subdivision": 0,
    "tick": 480
  },
  "quantized_duration_ticks": 480,
  "quantized_duration_name": "quarter",
  "dotted": false,
  "tied_from_previous": false,
  "tied_to_next": false,
  "tuplet": null,
  "quantization_confidence": 0.88,
  "quantization_mode": "humanized"
}
```

---

## Files to Create / Modify

```
backend/
  audio/
    beat_tracker.py       # full beat + downbeat tracking (madmom + librosa fallback)
    quantizer.py          # event quantization engine
    meter.py              # time signature detection + beat grid builder
    duration_mapper.py    # maps tick counts to notation duration names
```

Modify:
- `backend/audio/bpm.py` — integrate with new beat grid; preserve existing output format
- `backend/main.py` — add meter override endpoint; expose beat grid endpoint
- `colab/mwtn_notebook.ipynb` — add madmom install cell; update beat tracking cell

---

## Colab / Mobile Data Implications

| Action | Data Cost | Notes |
|---|---|---|
| `pip install madmom` | ~50 MB | One-time per Colab session |
| Beat tracking inference | Negligible | Runs on separated mix or original audio |

No significant data cost beyond the madmom install.

---

## Expected Results

- Transcribed events can be expressed as conventional musical rhythm
- Generated notation has valid measures
- Timing errors can be corrected without losing the original transcription
- Expressive passages are not automatically flattened to obviously wrong quantization
- MusicXML generation (Plan 07) has a reliable rhythmic foundation

---

## Acceptance Criteria

- [ ] A simple 4/4 melody produces correct measures and note values
- [ ] Notes crossing measure lines generate valid tied pairs
- [ ] Tempo changes are representable in the tempo map
- [ ] Quantization mode is togglable (`strict` / `humanized` / `off`)
- [ ] Raw and quantized timing are both preserved and separately accessible
- [ ] Measures containing rhythmic total mismatches are flagged, not silently corrupted
