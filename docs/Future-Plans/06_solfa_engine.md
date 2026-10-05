# Plan 06 — Movable-Do Solfa Extraction and Display

## Motive

The distinctive user-facing goal of the MWTN song-to-score expansion is turning an existing recording into a **practical solfa representation** — not just conventional sheet music. This is directly useful for ear training, singing practice, and music learning in Nigerian and West African contexts where solfa-based instruction is standard.

Solfa must be **derived from musical pitch + tonal context**, not guessed directly from audio. This ensures it is always consistent with the generated score and chord analysis.

---

## What Solfa Is (for implementors)

**Movable-do (tonic sol-fa)** assigns scale-degree names relative to the current key:

| Scale degree | Major | Solfège name | Abbrev |
|---|---|---|---|
| 1 | Tonic | Do | d |
| 2 | Supertonic | Re | r |
| 3 | Mediant | Mi | m |
| 4 | Subdominant | Fa | f |
| 5 | Dominant | Sol | s |
| 6 | Submediant | La | l |
| 7 | Leading tone | Ti | t |

In **C major**: C=Do, D=Re, E=Mi, F=Fa, G=Sol, A=La, B=Ti  
In **D major**: D=Do, E=Re, F#=Mi, G=Fa, A=Sol, B=La, C#=Ti

The same melody always produces the same solfa syllables regardless of the key it's performed in. This is the core utility.

**Chromatic alterations** (raised/lowered degrees):
| Raised | Lowered |
|---|---|
| Di (↑Do) | De (↓Re) |
| Ri (↑Re) | Ra |
| — | Me (↓Mi) |
| Fi (↑Fa) | — |
| Si (↑Sol) | Se (↓La) |
| Li (↑La) | Le |
| — | Te (↓Ti) |

**Minor keys** (natural minor / relative minor):
- La-based minor is most common in movable-do pedagogy
- Do-based minor (where Do = tonic of minor key) is also supported via a config option

---

## Process

### 1. Input: canonical note events + active key
- Source: `list[NoteEvent]` from Plan 02 (transcription)
- Key: `key_map` from Plan 05 (harmonic context)
- For each note, look up the active key at `note.start_time`

### 2. Convert MIDI pitch to scale degree
```python
def midi_to_scale_degree(midi_pitch: int, key: KeyEvent) -> int:
    tonic_pitch_class = note_name_to_pitch_class(key.tonic)  # e.g. C=0, D=2
    pitch_class = midi_pitch % 12
    degree = (pitch_class - tonic_pitch_class) % 12
    return degree  # 0–11
```

### 3. Map scale degree to solfa syllable
```python
MAJOR_DEGREE_TO_SOLFA = {
    0:  ("Do",  "d"),
    1:  ("Di",  "di"),  # raised 1 / chromatic passing
    2:  ("Re",  "r"),
    3:  ("Me",  "me"),  # lowered 3 (chromatic)
    4:  ("Mi",  "m"),
    5:  ("Fa",  "f"),
    6:  ("Fi",  "fi"),  # raised 4
    7:  ("Sol", "s"),
    8:  ("Le",  "le"),  # lowered 6
    9:  ("La",  "l"),
    10: ("Te",  "te"),  # lowered 7
    11: ("Ti",  "t"),
}
```

### 4. Define a SolfaEvent

```json
{
  "event_type": "solfa",
  "source_note_id": "<uuid of the NoteEvent>",
  "syllable": "Sol",
  "syllable_abbrev": "s",
  "scale_degree": 7,
  "midi_pitch": 67,
  "octave": 4,
  "active_key": { "tonic": "C", "mode": "major" },
  "start_time": 2.401,
  "end_time": 2.875,
  "quantized_start": { "measure": 1, "beat": 3 },
  "quantized_duration_name": "quarter",
  "confidence": 0.91,
  "is_chromatic": false,
  "is_uncertain": false
}
```

`is_uncertain` is set to `true` when the source note confidence < 0.5.

### 5. Minor key handling
Configuration option: `solfa_minor_mode: "la_based" | "do_based"`

- **la_based** (default): The minor tonic = La. So A minor: A=La, B=Ti, C=Do, D=Re, E=Mi, F=Fa, G=Sol
- **do_based**: The minor tonic = Do. So A minor: A=Do, B=Re, C=Me, D=Fa, E=Sol, F=Le, G=Te

### 6. Octave representation
Include register information:
```json
{ "octave": 4, "octave_notation": "Sol₄" }
```
Octave subscript notation for display when range matters.

### 7. Rest preservation
Rests in the source note events become rest markers in the solfa sequence:
```json
{ "event_type": "solfa_rest", "duration_name": "quarter", "start_time": 1.5 }
```

### 8. Recompute on key change
When the key map changes (Plan 05 user override or re-analysis):
- Mark all `SolfaEvent` objects derived from the changed key range as `is_stale: true`
- Trigger background recomputation
- Notify frontend via the existing job status pattern

### 9. Low-confidence handling
If source note `confidence < 0.5`:
- Set `SolfaEvent.is_uncertain = true`
- Display uncertain syllables with visual distinction in UI (e.g., lighter color, dashed underline)

### 10. Export options
- Plain text: `Do Re Mi Sol Mi | Re Mi Fa La Fa`
- JSON: full SolfaEvent array
- Synchronized with playback position (Plan 11)

### 11. Fixed-do option (for future expansion)
Fixed-do assigns C=Do regardless of key. Store as a separate config mode, but do not prioritize implementation. Movable-do is the primary and only required implementation for v1.

---

## Algorithm Summary

```python
def compute_solfa(
    note_events: list[NoteEvent],
    key_map: list[KeyEvent],
    config: SolfaConfig
) -> list[SolfaEvent]:
    solfa_events = []
    for note in sorted(note_events, key=lambda n: n.start_time):
        active_key = get_key_at_time(key_map, note.start_time)
        degree = midi_to_scale_degree(note.midi_pitch, active_key)
        syllable, abbrev = degree_to_solfa(degree, active_key.mode, config)
        solfa_events.append(SolfaEvent(
            source_note_id=note.event_id,
            syllable=syllable,
            syllable_abbrev=abbrev,
            scale_degree=degree,
            midi_pitch=note.midi_pitch,
            active_key=active_key,
            start_time=note.start_time,
            end_time=note.end_time,
            confidence=note.confidence,
            is_uncertain=note.confidence < 0.5,
            is_chromatic=degree not in {0, 2, 4, 5, 7, 9, 11}
        ))
    return solfa_events
```

---

## Files to Create

```
backend/
  solfa/
    __init__.py
    engine.py        # compute_solfa() and helpers
    config.py        # SolfaConfig Pydantic model
    mappings.py      # degree-to-syllable tables (major + minor)
```

Add endpoint:
- `GET /api/songs/{song_id}/solfa` — returns SolfaEvent array
- `GET /api/songs/{song_id}/solfa?stem=vocals` — stem-specific

---

## Colab / Mobile Data Implications

**None.** Solfa computation is pure Python math — no model, no GPU, no data download. Runs instantly on any existing note event output.

---

## Expected Results

A melody C–D–E–G–E in C major:
```
Do  Re  Mi  Sol  Mi
```
The same melody in D major:
```
Do  Re  Mi  Sol  Mi
```
A melody C–Bb–G in C major:
```
Do  Te  Sol
```

This makes MWTN useful for:
- Ear training in any key
- Singing practice and vocal warm-up
- Nigerian/West African solfa-based music learning
- Teaching music theory through familiar recordings

---

## Acceptance Criteria

- [ ] Solfa is generated from canonical NoteEvents, not independently from audio
- [ ] Changing the key map correctly changes movable-do output
- [ ] Rests are represented in the solfa sequence
- [ ] Chromatic notes produce correct altered syllables
- [ ] Low-confidence notes are flagged as `is_uncertain`
- [ ] La-based minor mode works correctly
- [ ] Solfa recomputes when the key changes
- [ ] Output is available via API in both full JSON and plain text formats
