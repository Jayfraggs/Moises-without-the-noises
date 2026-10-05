# Plan 07 — MIDI and MusicXML Score Generation

## Motive

MuseScore must receive a structured musical document, not raw audio. MIDI is the universal playback and interchange format; MusicXML is the primary score-oriented interchange format for notation software. Both must be generated from the same canonical `MusicalEvent` representation (Plan 01), ensuring they are always consistent with each other and with the solfa output.

---

## Libraries

### MIDI Generation
**mido** — MIT license, pure Python, no binary dependencies
```bash
pip install mido
```
Alternative: **pretty_midi** (MIT) — higher-level API, built on mido
```bash
pip install pretty_midi
```

### MusicXML Generation
**music21** — BSD license, comprehensive music theory + notation library
```bash
pip install music21
```
music21 can also generate MIDI, so it handles both formats from one library.

**Recommendation:** Use music21 as the primary export library for both MIDI and MusicXML. It has the richest MusicXML support and handles tuplets, ties, dynamics, lyrics, and chord symbols correctly.

---

## Process

### 1. Score-building layer
Build a score model from canonical MusicalEvents before any file export:

```python
class MWTNScore:
    metadata: ScoreMetadata        # title, composer, BPM, key, time_sig
    parts: list[ScorePart]         # one per stem/instrument
    
class ScorePart:
    instrument: str
    stem_id: str
    measures: list[Measure]
    
class Measure:
    number: int
    notes: list[NotationNote]      # with quantized positions
    rests: list[NotationRest]
    chords: list[ChordSymbol]      # attached at beat positions
    lyrics: list[LyricSyllable]    # for vocal parts
```

### 2. Track/stave grouping
- One `ScorePart` per separated stem
- Assign clef by instrument:
  - Treble clef: vocals, guitar, piano right-hand
  - Bass clef: bass, piano left-hand (if chords detected in lower register)
  - Percussion clef: drums

### 3. Apply musical metadata
- Key signature from Plan 05 key_map
- Time signature from Plan 04 meter detection
- Tempo marking from Plan 04 tempo_map
- Instrument name from stem type

### 4. Convert quantized events to notation durations
- Use `quantized_duration_name` from Plan 04
- Handle ties: split events that cross barlines, linked with tie notation
- Handle tuplets: group events tagged with `tuplet` metadata

### 5. Generate rests
- Fill gaps between notes within each measure
- Ensure each measure's note+rest total equals the time signature

### 6. Voices
When two notes overlap within the same part (polyphonic material):
- Assign to separate voices (voice 1 and voice 2 minimum)
- For piano: support up to 4 voices per staff

### 7. Chord symbols
From Plan 05 chord events:
- Attach chord symbols above the melody staff
- Use standard chord symbol notation (C, Dm, G7, Fmaj7, etc.)

### 8. Lyrics
From Plan 09 (lyrics alignment):
- Attach syllable-level lyrics to vocal note events
- Handle melismas (one syllable across multiple notes: use extender lines in MusicXML)
- Handle multiple syllables on one note: use a space or separate lyric verse

### 9. MusicXML generation via music21

```python
import music21 as m21

score = m21.stream.Score()
# ... build parts from MWTNScore
score.write('musicxml', fp='output.xml')
```

### 10. MusicXML validation
Before exposing any generated MusicXML:
- Run `music21`'s internal validation
- Check that the file opens without structural errors
- Store validation result in the artifact registry

### 11. MIDI generation via music21

```python
score.write('midi', fp='output.mid')
```

MIDI track mapping:
- One MIDI track per stem
- Channel assignment: melodic instruments on channels 1–9; drums on channel 10
- Velocity from note event `velocity` field (default 64 if not present)

### 12. Artifact versioning
Generated files are versioned artifacts in the artifact registry (Plan 01):
- `artifacts/<song_id>/scores/melody_v1.xml`
- `artifacts/<song_id>/scores/full_score_v1.xml`
- `artifacts/<song_id>/midi/melody_v1.mid`
- Each artifact records `source_run_id`, `config_hash`, `schema_version`

### 13. Separate export targets
Support independent generation of:
- `melody` — single melodic line (vocal or highest-pitched instrument)
- `vocal_with_lyrics` — vocal stem + lyric syllables
- `piano` — piano stem (treble + bass staves if polyphonic)
- `guitar` — guitar stem (tab notation in future; standard notation for v1)
- `bass` — bass clef single staff
- `full_score` — all available stems as a conductor score

### 14. Deterministic generation
Identical canonical events + identical config → identical output files.  
This enables cache hit detection via output hash comparison.

---

## API Endpoints to Add

```
POST /api/songs/{song_id}/generate/musicxml
  body: { "target": "melody | vocal | piano | guitar | bass | full_score" }
  returns: { "artifact_id": "...", "status": "queued | complete | failed" }

GET  /api/songs/{song_id}/artifacts/{artifact_id}/download
  returns: file stream

GET  /api/songs/{song_id}/artifacts
  returns: list of available generated artifacts
```

---

## Files to Create

```
backend/
  export/
    __init__.py
    score_builder.py      # MWTNScore builder from MusicalEvents
    musicxml_exporter.py  # music21-based MusicXML generator
    midi_exporter.py      # music21-based MIDI generator
    validation.py         # MusicXML structural validation
```

Modify:
- `backend/main.py` — add export and artifact endpoints
- `colab/mwtn_notebook.ipynb` — add music21 install cell + export cell

---

## Colab / Mobile Data Implications

| Action | Data Cost | Notes |
|---|---|---|
| `pip install music21` | ~30 MB | One-time per Colab session |
| `pip install mido pretty_midi` | ~5 MB | Optional if using music21 only |
| MusicXML output file size | ~50–500 KB per song | Included in output zip |
| MIDI output file size | ~10–100 KB per song | Included in output zip |

Output files are included in the existing Colab output zip — no additional upload/download cost.

---

## Expected Results

- MWTN generates editable MIDI files usable in any DAW
- MWTN generates MusicXML files openable in MuseScore without structural errors
- Multiple stems become separate score parts/staves
- Lyrics and chord symbols are embedded where confidence permits
- All generated artifacts are versioned and traceable

---

## Acceptance Criteria

- [ ] Generated MIDI imports correctly into MuseScore and plays back
- [ ] Generated MusicXML opens in MuseScore without structural errors
- [ ] A simple melody renders with correct pitch and rhythm
- [ ] Multi-stem songs produce separate parts in the score
- [ ] Lyrics align correctly with vocal notes
- [ ] Chord symbols appear above the melody staff
- [ ] Tied notes are generated for events crossing barlines
- [ ] Generation is deterministic for identical source data
- [ ] Artifacts are registered in the artifact registry with source run metadata
