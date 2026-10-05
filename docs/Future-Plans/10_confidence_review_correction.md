# Plan 10 — Confidence, Error Detection and Human Review

## Motive

Automatic music transcription is inherently imperfect. A system that presents every prediction as fact will produce frustrating, untrustworthy scores. MWTN must make **uncertainty visible** and provide targeted tools for correcting the mistakes that matter most — without forcing the user to re-run expensive GPU jobs for simple musical edits.

---

## Confidence Normalization

All confidence values are normalized to **[0.0, 1.0]** regardless of source model.

| Model | Raw confidence format | Normalized to [0,1] |
|---|---|---|
| Basic Pitch | Frame-level probability [0,1] | Direct use |
| pYIN | Probability of voicing [0,1] | Direct use |
| autochord | Probability per chord class | Softmax → highest class |
| librosa key | Correlation score | Min-max normalize |
| madmom beat | Activation value [0,1] | Direct use |
| Whisper | Log-probability | `exp(log_prob)` clamp to [0,1] |

---

## Confidence-Bearing Fields

All of the following carry a `confidence: float` field in the schema:

| Event type | What confidence measures |
|---|---|
| NoteEvent | Pitch detection reliability |
| ChordEvent | Chord identity reliability |
| LyricAlignment | Syllable-to-note pairing accuracy |
| KeyEvent | Tonal center reliability |
| TempoEvent | Beat tracking reliability |
| BeatEvent | Individual beat position reliability |
| SolfaEvent | Inherited from source NoteEvent |

---

## Suspicious Event Detection

Run automatically after transcription. Flag events matching any of these patterns:

| Condition | Severity | Label |
|---|---|---|
| Note duration < 40ms | Warning | `too_short` |
| Note confidence < 0.35 | Warning | `low_confidence` |
| Note confidence < 0.2 | Error | `very_low_confidence` |
| Two notes overlap > 20ms on same voice | Warning | `overlap` |
| Pitch jump > 24 semitones between adjacent notes | Warning | `large_pitch_jump` |
| Polyphony > 6 simultaneous notes (non-drum stem) | Warning | `excessive_polyphony` |
| Note duration quantization error > 30% of beat | Warning | `quantization_mismatch` |
| Measure rhythmic total mismatch | Error | `bad_measure_total` |
| Chord confidence < 0.4 | Info | `uncertain_chord` |
| Key confidence < 0.5 | Info | `uncertain_key` |
| Lyric alignment confidence < 0.5 | Info | `uncertain_lyric` |

---

## Correction Data Model

Raw model output is **immutable**. User corrections are stored as a separate overlay:

```json
{
  "schema_version": "1.0",
  "corrections": [
    {
      "correction_id": "<uuid>",
      "target_event_id": "<note_or_chord_event_id>",
      "correction_type": "pitch | duration | delete | split | merge | chord | key | lyric",
      "original_value": { "midi_pitch": 64, "start_time": 1.24, "end_time": 1.72 },
      "corrected_value": { "midi_pitch": 65, "start_time": 1.24, "end_time": 1.72 },
      "corrected_at": "<ISO8601>",
      "correction_source": "user",
      "triggered_recompute": ["solfa", "musicxml", "midi"]
    }
  ]
}
```

File: `backend/data/<song_id>/corrections.json`

The pipeline applies corrections as a post-processing pass on top of raw model output, before any score or solfa generation. This means:
- Re-running transcription resets model output but preserves corrections
- Re-running expensive separation does not touch corrections
- Corrections can be exported and re-imported (portability)

---

## Supported Correction Operations

| Operation | What it changes |
|---|---|
| Move note (pitch) | Change `midi_pitch` + `frequency_hz` |
| Move note (time) | Change `start_time` / `end_time` |
| Change duration | Change `end_time` |
| Delete note | Mark event as `deleted: true` |
| Split note | Replace one event with two adjacent events |
| Merge notes | Replace two adjacent events with one combined event |
| Change chord | Override chord root/quality on a ChordEvent |
| Change key | Override key in key_map at a given time range |
| Correct lyric | Override syllable assignment on a LyricAlignment |
| Change review status | Mark a flagged event as `reviewed_ok` or `confirmed_error` |

---

## Downstream Recomputation

When a correction is applied, the system determines which derived artifacts are now stale:

| Correction type | Stale artifacts |
|---|---|
| Note pitch / duration | solfa, musicxml, midi |
| Note delete / split / merge | solfa, musicxml, midi |
| Chord change | musicxml (chord symbols), chord chart export |
| Key change | solfa (all events in range), musicxml (key signature) |
| Lyric correction | lyrics_alignment, musicxml lyrics |

Recomputation is triggered asynchronously. The frontend shows a "regenerating…" state on affected artifacts.

---

## Quality Indicator

A per-song overall quality score is computed as:
```
quality = mean(confidence of all NoteEvents) × (1 - ratio_of_flagged_events)
```
Displayed in the Score UI (Plan 11) as a simple percentage or color indicator.

---

## Audit Trail

All corrections are append-only:
- Undoing a correction appends an inverse correction, not a deletion
- Full history of all corrections is preserved in `corrections.json`
- The UI can show a diff of "model output vs current state"

---

## API Endpoints

```
GET  /api/songs/{song_id}/review
     returns: all flagged events with severity + label

PATCH /api/songs/{song_id}/notes/{event_id}
      body: { "correction_type": "pitch", "corrected_value": { "midi_pitch": 65 } }

DELETE /api/songs/{song_id}/notes/{event_id}
       (creates a delete correction, does not remove from raw output)

POST /api/songs/{song_id}/notes/{event_id}/split
     body: { "split_at_time": 1.45 }

POST /api/songs/{song_id}/notes
     body: { "midi_pitch": 60, "start_time": 2.1, "end_time": 2.5, "track_id": "vocals" }
     (insert new note — a user-authored event)

PATCH /api/songs/{song_id}/key
      body: { "start_s": 32.0, "tonic": "A", "mode": "minor" }

GET  /api/songs/{song_id}/corrections
     returns: full correction history

POST /api/songs/{song_id}/corrections/undo
     body: { "correction_id": "<uuid>" }
```

---

## Files to Create

```
backend/
  review/
    __init__.py
    detector.py        # suspicious event detection rules
    corrections.py     # correction overlay read/write/apply
    recompute.py       # stale artifact detection + async recompute trigger
```

---

## Colab / Mobile Data Implications

**None.** The review and correction system is pure backend logic — no model inference required. All corrections run on already-downloaded data. Zero additional data cost.

---

## Expected Results

- Users can quickly identify and fix the transcription mistakes that matter
- The system is honest about uncertainty — low-confidence predictions are visually distinct
- Corrections survive regeneration of unrelated artifacts
- The original model output remains recoverable at any time
- Human-edited scores can become significantly better than raw model output

---

## Acceptance Criteria

- [ ] Low-confidence events are visually identified in the UI with their severity level
- [ ] All supported correction operations apply cleanly and save to `corrections.json`
- [ ] Corrections update solfa, MIDI, and MusicXML outputs on next generation
- [ ] Undo works (restores previous value without deleting history)
- [ ] Original model output is recoverable regardless of correction history
- [ ] Suspicious event detection flags known problematic patterns
- [ ] Overall quality indicator is computed and exposed via API
