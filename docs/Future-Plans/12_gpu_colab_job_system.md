# Plan 12 — GPU/Colab Processing and Job Orchestration

## Motive

High-quality separation and AMT models are computationally expensive and cannot run on a 16 GB laptop without significant memory pressure. MWTN's existing Colab workflow handles this, but the expanded pipeline introduces multiple new stages (separation, per-stem transcription, beat/harmonic analysis, score generation) that need a **formal job protocol** so the notebook, the backend, and the user are never out of sync.

---

## Core Design: Versioned Job Manifest

A **processing job** is a JSON document that defines everything needed to produce a complete MWTN project artifact from a source audio file. The Colab notebook reads this manifest, executes the stages, and produces an output zip with a companion result manifest.

### Job Input Manifest

```json
{
  "schema_version": "1.0",
  "job_id": "<uuid>",
  "project_id": "<song_id>",
  "source_file": "original.mp3",
  "source_hash": "<sha256>",
  "requested_stems": ["vocals", "bass", "drums", "guitar", "piano", "other"],
  "separation_model": "htdemucs_6s",
  "separation_profile": "standard",
  "transcription": {
    "vocals":  { "engine": "basic_pitch", "quality": "standard" },
    "bass":    { "engine": "pyin",        "quality": "fast" },
    "drums":   { "engine": "adtlib",      "quality": "standard" },
    "guitar":  { "engine": "basic_pitch", "quality": "standard" },
    "piano":   { "engine": "basic_pitch", "quality": "standard" }
  },
  "analysis": {
    "beat_tracking": true,
    "key_detection": true,
    "chord_detection": true,
    "lyrics": true,
    "use_whisperx": false
  },
  "output_schema_version": "1.0",
  "created_at": "<ISO8601>"
}
```

### Job Stages and Status

```json
{
  "stages": {
    "upload":           { "status": "complete", "completed_at": "..." },
    "separation":       { "status": "running",  "started_at": "...", "progress": 0.6 },
    "transcription":    { "status": "queued" },
    "beat_analysis":    { "status": "queued" },
    "harmonic_analysis":{ "status": "queued" },
    "score_generation": { "status": "queued" },
    "packaging":        { "status": "queued" }
  }
}
```

Valid status values: `queued | running | complete | failed | skipped`

Each stage also records:
- `started_at`, `completed_at`
- `error` (string, null if no error)
- `artifacts_produced` (list of relative paths)

---

## Colab Notebook Structure (Updated)

The notebook is reorganized into clearly labeled cells matching the job stages:

```
Cell 01 — Environment setup (pip installs, imports)
Cell 02 — Mount Google Drive
Cell 03 — Load job manifest
Cell 04 — Source hash check (resume detection)
Cell 05 — Source separation (Demucs)
Cell 06 — Stem validation
Cell 07 — Transcription dispatch (per stem)
  Cell 07a — Vocals (Basic Pitch or pYIN)
  Cell 07b — Bass (pYIN)
  Cell 07c — Piano (Basic Pitch or Piano Kong)
  Cell 07d — Guitar (Basic Pitch)
  Cell 07e — Drums (ADTLib)
Cell 08 — Beat + downbeat tracking (madmom)
Cell 09 — Key + chord analysis (autochord + librosa)
Cell 10 — Lyrics transcription + alignment (Whisper + pyphen)
Cell 11 — Score generation (music21 → MIDI + MusicXML)
Cell 12 — Artifact packaging + manifest finalization
Cell 13 — Upload to Google Drive
```

Each cell:
1. Checks the job manifest to see if this stage is already complete (resume detection)
2. Executes only if not already complete
3. Updates stage status in the manifest on completion or failure
4. On failure: writes error to manifest and prints a clear diagnostic; does NOT crash the notebook

### Resume Logic

```python
def should_run_stage(manifest: dict, stage_name: str) -> bool:
    stage = manifest['stages'].get(stage_name, {})
    if stage.get('status') == 'complete':
        print(f"[{stage_name}] Already complete — skipping.")
        return False
    return True
```

---

## Artifact Packaging

Output zip structure:
```
mwtn_output_<song_id>.zip
├── manifest.json              # full job result manifest
├── source/
│   └── original.mp3
├── stems/
│   ├── vocals.wav
│   ├── bass.wav
│   ├── drums.wav
│   ├── guitar.wav
│   ├── piano.wav
│   └── other.wav
├── transcription/
│   ├── vocals_events.json
│   ├── bass_events.json
│   ├── piano_events.json
│   └── drums_events.json
├── analysis/
│   ├── beats.json
│   ├── key.json
│   ├── chords.json
├── lyrics/
│   ├── lyrics.json
│   └── lyrics_alignment.json
└── scores/
    ├── melody.xml
    ├── full_score.xml
    ├── melody.mid
    └── full_score.mid
```

---

## Backend Import

When the user drops the zip into `backend/data/` (or uses `POST /api/import`):

1. Validate that `manifest.json` exists and parses correctly
2. Check `schema_version` — reject unknown versions with a clear error
3. Validate that all artifacts listed in the manifest are present on disk
4. Check for any failed stages — report them, do not crash the import
5. Register the song in the backend's song index
6. Compute any missing analysis that wasn't in the zip (e.g., beat tracking if not requested)

```
POST /api/import
  body: multipart/form-data with the zip file
  returns: { "song_id": "...", "warnings": [...], "failed_stages": [...] }
```

---

## Compatibility Checks

The manifest records the producing environment:
```json
{
  "environment": {
    "python": "3.11.2",
    "demucs": "4.0.1",
    "basic_pitch": "0.3.1",
    "music21": "9.1.0",
    "torch": "2.2.0",
    "colab_runtime": "GPU T4"
  }
}
```

Backend validates that the schema version is supported before importing. If the manifest schema version is newer than what the backend understands, it reports a clear "please update MWTN" message.

---

## Local GPU Path

All job stages that currently run in Colab can also run locally if the user has a GPU. The same job manifest format is used. `POST /api/import` with a source file (not a zip) triggers local execution using the job manifest pipeline.

This path is slower and not recommended for most users, but the contract is identical.

---

## Files to Create / Modify

```
backend/
  jobs/
    __init__.py
    manifest.py        # job input/output manifest Pydantic models
    importer.py        # zip validation + import logic
    stages.py          # stage status tracking utilities

colab/
  mwtn_notebook.ipynb  # full restructure into stage-based cells
  mwtn_pipeline.py     # shared pipeline utilities imported by the notebook
```

---

## Colab / Mobile Data Implications

The job manifest itself is tiny (<5 KB). The main data costs are the model installs and per-song processing:

| Stage | First-session install cost | Per-song cost |
|---|---|---|
| Demucs htdemucs_6s | ~80 MB | — |
| Basic Pitch | ~50 MB deps + 17 MB weights | — |
| madmom | ~50 MB | — |
| autochord | ~30 MB | — |
| pyphen | ~5 MB | — |
| music21 | ~30 MB | — |
| Source audio upload | — | ~3–10 MB (MP3) |
| Output zip download | — | ~50–150 MB |

First session total: ~260 MB of installs (cached across reconnects if not cleared).
Per-song: ~60–160 MB upload + download combined.

> ⚠️ The output zip is now larger than before (~30–80 MB previously) because it includes transcription events, MusicXML, and MIDI. Advise users to download on unmetered connections.

---

## Expected Results

- A complete song can be processed remotely without manual file shuffling
- MWTN can import a completed processing package safely and validate it
- Jobs can resume after Colab disconnection from the last valid stage
- Local and Colab results follow the same schema and produce identical backend behavior

---

## Acceptance Criteria

- [ ] A complete job manifest can be exported and imported without data loss
- [ ] An interrupted job resumes from the last completed stage on notebook re-run
- [ ] Invalid or incomplete zips are rejected with a clear error message
- [ ] The manifest records the producing environment (model versions, runtime)
- [ ] Failed stages are reported without blocking the import of successful stages
- [ ] Backend import endpoint validates schema version before accepting the zip
