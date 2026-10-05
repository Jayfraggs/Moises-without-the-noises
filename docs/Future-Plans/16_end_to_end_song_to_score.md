# Plan 16 — End-to-End Song-to-Score Workflow

## Motive

After all individual features are implemented and tested independently, MWTN needs a single **orchestration workflow** that turns an existing recording into a usable musical document with minimal manual intervention. This is the final integration layer and should not be implemented until the underlying contracts (Plans 01–13) are stable.

---

## The Target User Experience

> **Drop an existing song into MWTN → select a processing profile → wait for analysis → receive stems, note events, chords, lyrics, solfa, MIDI, and an editable MusicXML score → open the score in MuseScore for final engraving or editing.**

The workflow must **degrade gracefully**. If guitar transcription is unavailable or fails, MWTN should still produce vocal melody, bass, chords, lyrics, solfa, and all other successful outputs — not fail the entire job.

---

## Complete Pipeline Sequence

### Phase 1 — Intake
1. User imports MP3 / WAV / FLAC / M4A via `POST /api/import` or the Import Song UI
2. Backend validates the file (Plan 15)
3. Backend computes `sha256(source_audio)` for cache checking
4. Backend creates a project record + job manifest
5. Backend inspects audio properties: duration, sample rate, channels, bitrate
6. Backend estimates initial BPM and key candidates (fast pre-analysis using existing librosa path)
7. User sees the song in the library with status `processing`

### Phase 2 — Profile Selection
8. User selects a processing profile (or accepts the default):
   - `Fast` — pYIN vocals/bass + existing BPM + Krumhansl-Schmuckler key
   - `Standard` — Basic Pitch all stems + madmom beats + autochord chords (recommended)
   - `High Quality` — Piano Kong piano + WhisperX lyrics + everything from Standard
9. User optionally selects which stems to transcribe (skip guitar if not needed)
10. Job manifest is finalized and dispatched

### Phase 3 — Processing (Colab or Local)

#### For Colab path:
10. User runs the updated Colab notebook with the job manifest
11. Notebook executes stages in order (Plan 12):
    - Source separation (Plan 03)
    - Stem validation
    - Transcription per stem (Plan 02)
    - Beat + downbeat tracking (Plan 04)
    - Key + scale analysis (Plan 05)
    - Chord detection (Plan 05)
    - Lyric transcription + alignment (Plan 09)
    - Score generation: MIDI + MusicXML (Plan 07)
    - Artifact packaging
12. User downloads the output zip from Google Drive
13. User drops the zip into MWTN (or `POST /api/import` with the zip)

#### For local path:
10. `POST /api/import` with source audio triggers background job
11. Stages run sequentially in a background thread
12. Progress is available via `GET /api/songs/{song_id}/job/status`

### Phase 4 — Import and Validation
14. Backend validates the output zip (Plan 15)
15. Backend checks schema versions
16. Backend imports all artifacts into the project directory
17. Backend runs consistency checks (Plan 10):
    - Flag suspicious note events
    - Compute per-event confidence
    - Compute overall quality score
18. Backend merges all outputs into the canonical MusicalEvent representation (Plan 01)
19. Backend applies any existing corrections (Plan 10)

### Phase 5 — Presentation
20. Frontend loads the song in the Score workspace (Plan 11)
21. User sees:
    - Waveform + stem controls (existing MWTN UI)
    - Staff notation (OSMD rendering of generated MusicXML)
    - Solfa view (synchronized syllable display)
    - Chord chart
    - Lyrics view
    - Note timeline (with confidence colors)
22. Playback cursor advances across all synchronized views

### Phase 6 — Review and Correction
23. User reviews flagged low-confidence events (Plan 10)
24. User corrects pitch/duration errors in the note timeline
25. User corrects chord or key if needed
26. Backend recomputes dependent artifacts (solfa, MusicXML, MIDI) asynchronously
27. Score view shows "Regenerating…" state while recomputing

### Phase 7 — Export
28. User chooses export target:
    - `Open in MuseScore` — opens generated MusicXML in MuseScore (Plan 08)
    - `Export MusicXML` — download `.xml`
    - `Export MIDI` — download `.mid`
    - `Export Solfa` — copy plain text or download JSON
    - Existing MWTN exports: stem WAV, custom mix, mix + click track

---

## Graceful Degradation Matrix

| Missing/failed component | Impact | Fallback |
|---|---|---|
| Guitar transcription fails | No guitar stave in score | Other staves proceed normally |
| Chord detection unavailable | No chord symbols in MusicXML | Score generates without chord symbols |
| Lyric alignment fails | Lyrics not embedded in MusicXML | MusicXML generates without lyrics; karaoke view still works from Whisper timestamps |
| Drum transcription fails | No drum part in score | Other parts proceed normally |
| Piano Kong not installed | Piano transcribed by Basic Pitch | Quality label shows "Standard" not "High Quality" |
| MuseScore not installed | Open in MuseScore grayed out | Download MusicXML offered instead |
| madmom not installed | Beat tracking falls back to librosa | Quality may be lower; user informed |
| WhisperX not installed | Lyrics use standard Whisper timestamps | Alignment accuracy is lower |

---

## Job Status API

```
GET /api/songs/{song_id}/job/status
returns:
{
  "song_id": "...",
  "job_id": "...",
  "overall_status": "processing | complete | failed | partial",
  "stages": {
    "separation":        { "status": "complete", "stems_produced": 6 },
    "transcription":     { "status": "complete", "stems_transcribed": 5, "stems_failed": 1 },
    "beat_analysis":     { "status": "complete" },
    "harmonic_analysis": { "status": "complete" },
    "lyrics":            { "status": "complete" },
    "score_generation":  { "status": "complete", "artifacts": ["melody.xml", "full_score.xml"] }
  },
  "quality_score": 0.74,
  "warnings": ["guitar transcription failed: low stem quality"],
  "artifacts_available": ["stems", "transcription", "beats", "key", "chords", "lyrics", "musicxml", "midi", "solfa"]
}
```

---

## Reproducibility

Every processing run produces a complete audit record:

```json
{
  "run_id": "<uuid>",
  "song_id": "<song_id>",
  "job_manifest_hash": "<sha256 of input job manifest>",
  "completed_at": "<ISO8601>",
  "environment": {
    "demucs": "4.0.1",
    "basic_pitch": "0.3.1",
    "madmom": "0.16.1",
    "music21": "9.1.0"
  },
  "artifact_hashes": {
    "melody.xml": "<sha256>",
    "full_score.xml": "<sha256>",
    "melody.mid": "<sha256>"
  }
}
```

Given the same source audio and the same job manifest (model versions + config), the pipeline is deterministic and reproducible.

---

## One End-to-End Test (Plan 14 integration)

A single designated test song (synthetic, generated by `tests/fixtures/generate_fixtures.py`) runs the complete pipeline and checks:

- [ ] All 6 stems produced and validated
- [ ] Vocal transcription produces note events
- [ ] Beat tracking produces a beat grid
- [ ] Key detection returns the expected key
- [ ] Chord detection produces chord events
- [ ] Solfa events correspond to the transcribed notes in the correct key
- [ ] MusicXML passes structural validation
- [ ] MIDI imports without error
- [ ] All artifacts linked through the manifest
- [ ] Playback sync: solfa events align with note events in time
- [ ] Failed optional stages (e.g., no drums stem in test audio) do not crash the pipeline
- [ ] The complete run is reproducible from its job manifest

---

## Files to Create / Modify

```
backend/
  orchestration/
    __init__.py
    pipeline.py          # end-to-end job orchestration
    stage_runner.py      # per-stage execution + error isolation
    consistency.py       # post-import consistency checks
    reproducibility.py   # run record creation + audit log

colab/
  mwtn_notebook.ipynb    # final integrated version (all stage cells)
  mwtn_pipeline.py       # shared utilities used by the notebook
```

---

## Colab / Mobile Data Implications (Full Pipeline Summary)

| Item | Cost | Frequency |
|---|---|---|
| First-session installs (all models) | ~260 MB | Once per Colab session |
| Source audio upload | ~3–10 MB | Per song |
| Output zip download | ~80–200 MB | Per song |
| Colab GPU compute | Free tier: ~1–3h/day | Per session |

> ⚠️ The output zip is now significantly larger than the original MWTN output (~30–80 MB) because it includes transcription events, MusicXML, and MIDI files. Advise users to download on unmetered (WiFi) connections where possible.

> The Colab free tier GPU quota (typically T4, ~1–3 hours of GPU per day) is sufficient for processing 2–5 songs depending on length and profile. This is adequate for the intended use case (musician practicing individual songs).

---

## Expected Results

A user can:
1. Import an MP3 of any song they own
2. Run the Colab notebook (or wait for local processing)
3. Download the output zip
4. Drop it into MWTN
5. Immediately see synchronized stems, waveform, notes, chords, solfa, and notation
6. Correct the most obvious transcription errors using the note timeline
7. Export the result to MuseScore for professional editing

All of this without requiring any ML knowledge, local model installation, or GPU hardware.

---

## Acceptance Criteria

- [ ] One designated end-to-end test song completes the full pipeline without errors
- [ ] Every major artifact (stems, events, beats, key, chords, lyrics, solfa, MusicXML, MIDI) is present and linked in the manifest
- [ ] Generated MusicXML opens in MuseScore without structural errors
- [ ] Solfa view corresponds to the transcribed melody in the correct key
- [ ] MIDI playback corresponds to the note events
- [ ] Playback synchronization is consistent across all views
- [ ] A failed optional stage does not prevent successful stages from completing
- [ ] The complete processing run is reproducible from its job manifest + source audio
- [ ] The full workflow is documented in README with screenshots/GIF
