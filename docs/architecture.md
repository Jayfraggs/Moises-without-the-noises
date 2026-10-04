# Architecture — Moises without the Noises (mwtn)

This document covers repository layout, system architecture, API surface,
data formats, and every significant design decision. Keep it in sync with
the code — when you change a contract, update this file in the same commit.

---

## Repository layout

```
mwtn/
├── backend/               Python FastAPI service
│   ├── main.py            REST routes, background job orchestration
│   ├── separation.py      Multi-engine audio source separation
│   ├── ingest.py          ZIP ingestion (Colab output + raw-stems)
│   ├── note_extraction.py Monophonic pitch tracking → note timeline
│   ├── audio/
│   │   ├── bpm.py         Beat & tempo detection (librosa)
│   │   ├── key_detection.py  Krumhansl-Schmuckler key detection
│   │   ├── pitch.py       Pitch-shift / time-stretch for export
│   │   └── mixer.py       Stem mixing for server-side export
│   ├── data/              Runtime song library (one dir per song_id)
│   ├── tests/             pytest test suite
│   └── requirements.txt   Python dependencies
│
├── frontend/              React + Vite SPA
│   ├── src/
│   │   ├── App.jsx        Root component — state, routing, sidebar
│   │   ├── App.css        Global styles + design tokens
│   │   ├── AudioEngine.js Web Audio API engine (playback, VU, waveform)
│   │   ├── api.js         HTTP bridge to backend
│   │   ├── setupTests.js  Vitest global setup
│   │   ├── hooks/
│   │   │   ├── useOnboarding.js      First-run setup wizard state
│   │   │   └── useKeyboardShortcuts.js  Global DAW keyboard shortcuts
│   │   └── components/
│   │       ├── SongSelector.jsx      Searchable library list with pills
│   │       ├── ImportZip.jsx         Drag-drop ZIP ingest (new)
│   │       ├── ImportSong.jsx        Local file import with model selector
│   │       ├── ImportDrive.jsx       Drive-folder scan and ingest
│   │       ├── WaveformView.jsx      Canvas waveform + playhead + loop overlay
│   │       ├── MetaCards.jsx         BPM / Key / Duration / Model info pills
│   │       ├── StemPresence.jsx      Per-stem RMS energy bars
│   │       ├── StemControls.jsx      Channel strip with VU meter + colour stripe
│   │       ├── TransportControls.jsx Play/pause, seek, loop markers, metronome
│   │       ├── SpeedControl.jsx      Playback speed presets + slider
│   │       ├── PitchControl.jsx      Semitone shift with key transposition
│   │       ├── ChordDisplay.jsx      Chord timeline (synced scroll)
│   │       ├── NoteDisplay.jsx       Per-stem note timeline
│   │       ├── LyricsPanel.jsx       Karaoke panel with word-level sync
│   │       ├── ExportPanel.jsx       Mix export modal (stems, click, pitch)
│   │       ├── SongInfoBar.jsx       Song title + BPM/key/model badges
│   │       ├── SongDetail.jsx        Full song view (stems, transport, panels)
│   │       ├── CountInControl.jsx    Count-in pre-roll selector
│   │       ├── SetupWizard.jsx       First-run onboarding wizard
│   │       └── Settings.jsx          Drive config + post-wizard settings
│   ├── vite.config.js     Vite + Vitest config (jsdom, setupFiles)
│   └── package.json
│
├── electron/              Thin Electron desktop wrapper
│   └── main.js            Window creation + IPC for Drive config
│
├── colab/
│   ├── mwtn_notebook.ipynb  GPU processing pipeline (all engines)
│   └── mwtn_pipeline.py     Helper script for Colab session
│
└── docs/
    └── architecture.md    This file
```

---

## Core concepts

### Processing paths

Two paths produce songs. Both write the same on-disk layout; the rest
of the app is identical regardless of which path was used.

**Colab pipeline (recommended)**
Run `colab/mwtn_notebook.ipynb` on a free Colab GPU. Select your
separation engine and Whisper model in Cell 3, upload the audio in
Cell 4, and run all cells. The notebook produces a ZIP containing a
`<song_id>/` folder with stems, analysis files, and `manifest.json`.
Drop that ZIP into `backend/data/` and extract it there — or use the
new ZIP drag-drop in the UI. Typical GPU runtime: under 2 minutes for
a 4-minute song.

**Local import (slow path)**
`POST /api/import?model=<model_name>` accepts an audio file and runs
the selected separation engine on this machine via `separation.py`.
On a CPU-only laptop expect 15–40 minutes per song. All engines work
locally but download their model weights on first run (see data costs
below). A background thread runs the job; poll `GET /api/import/{job_id}/status`.

**ZIP drag-drop (new)**
`POST /api/ingest/upload` accepts a ZIP file directly from the browser.
Handles two ZIP shapes:
1. Colab-pipeline ZIP — has `manifest.json`. Extracted as-is.
2. Raw-stems ZIP — loose WAV files, no manifest. Stems are
   auto-detected by filename (see naming conventions below) and a
   manifest is generated. Handles UVR5, audio-separator, Spleeter,
   and Audacity exports.

### Manifest-driven discovery

The backend discovers songs by scanning `backend/data/` for directories
containing `manifest.json`. No database, no registration step — drop a
folder in and the app picks it up on the next `GET /api/songs` call.

### Stem naming conventions (ZIP drag-drop)

When a raw-stems ZIP has no manifest, stems are identified by filename:

| Canonical stem | Recognised filenames (case-insensitive) |
|---|---|
| `vocals` | vocals, vocal, vox, lead_vocals, voice, singer |
| `drums` | drums, drum, beat, percussion, perc, kick |
| `bass` | bass, bass_guitar, bass_line |
| `guitar` | guitar, gtr, guitars, electric_guitar, acoustic_guitar |
| `piano` | piano, keys, keyboard, keyboards, synth |
| `instrumental` | accompaniment, backing, backing_track, music, inst, no_vocals |
| *(anything else)* | kept as-is, lowercased |

---

## Separation engines

All engines are MIT-licensed. Demucs is installed by default; the
others are opt-in (install the matching pip package, then select
the model in the UI or notebook).

| Model key | Engine | Stems | Best for | pip install | First-run download |
|---|---|---|---|---|---|
| `htdemucs_ft` | Demucs (Meta) | 4 | Fast, clean default | *(included)* | ~2.0 GB |
| `htdemucs_6s` | Demucs (Meta) | 6 | Guitar + piano tracks | *(included)* | ~2.3 GB |
| `spleeter:2stems` | Spleeter (Deezer) | 2 | Karaoke only, fastest on GPU | `spleeter` | ~1.0 GB |
| `spleeter:4stems` | Spleeter (Deezer) | 4 | Speed over quality | `spleeter` | ~1.1 GB |
| `spleeter:5stems` | Spleeter (Deezer) | 5 | + piano split | `spleeter` | ~1.2 GB |
| `umxl` | Open-Unmix (Inria) | 4 | Research baseline, stable | `openunmix torchaudio` | ~0.4 GB |
| `umxhq` | Open-Unmix (Inria) | 4 | MUSDB18-HQ reproducible | `openunmix torchaudio` | ~0.4 GB |
| `mdx-vocalft` | MDX-Net (UVR) | 2 | Clean vocals on reverb-heavy material | `audio-separator[cpu]` | ~0.35 GB |
| `mdx-inst-hq3` | MDX-Net (UVR) | 2 | Best instrumental extraction | `audio-separator[cpu]` | ~0.35 GB |
| `bs-roformer` | BS-RoFormer | 6 | Best overall quality (SOTA) | `bs-roformer-infer` | ~0.4 GB |
| `melband-roformer` | Mel-Band RoFormer | 2 | Best vocal isolation specifically | `melband-roformer-infer` | ~0.3 GB |

⚠️ **Mobile data note:** model downloads happen on first use. Run the
Colab notebook or local import on Wi-Fi for any engine with a download
over ~500 MB.

---

## API surface

### Config

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/config` | Available separation models, default model, engine metadata |

### Song library

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/songs` | List all songs (reads manifests from `data/`) |
| `GET` | `/api/songs/{song_id}/manifest` | Full manifest for one song |
| `DELETE` | `/api/songs/{song_id}` | Delete song directory (permanent) |

### Stems and analysis

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/songs/{song_id}/stems/{stem_name}` | Download stem WAV |
| `GET` | `/api/songs/{song_id}/stems/{stem_name}/notes` | Note timeline JSON |
| `GET` | `/api/songs/{song_id}/lyrics` | Whisper word-level timestamps |
| `PATCH` | `/api/songs/{song_id}/lyrics` | Atomic rewrite of lyrics timestamps (karaoke editor) |
| `GET` | `/api/songs/{song_id}/beats` | BPM + beat timestamps (computed on-demand, cached) |
| `GET` | `/api/songs/{song_id}/key` | Detected musical key (computed on-demand, cached) |
| `GET` | `/api/songs/{song_id}/chords` | Chord timeline JSON |

### Export

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/songs/{song_id}/stems/{stem_name}/export` | Single-stem export with optional pitch/stretch |
| `POST` | `/api/songs/{song_id}/export` | Multi-stem mix export with optional click track, pitch, stretch |

### Import / ingest

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/import?model=<model>` | Upload audio → run separation locally (background job) |
| `GET` | `/api/import/{job_id}/status` | Poll local import job state and log |
| `POST` | `/api/ingest` | Ingest from local filesystem path (Electron / Drive scanner) |
| `POST` | `/api/ingest/upload` | Upload + ingest ZIP directly from browser (drag-drop) |

---

## AudioEngine

`frontend/src/AudioEngine.js` owns all Web Audio API logic. Key design points:

**Sync model** — `startTime` (AudioContext clock when playback began) +
`startOffset` (song position at that moment). `getCurrentTime()` derives
position from `(context.currentTime - startTime) * playbackRate`. No
counter, no drift.

**VU meters** — each stem has a dedicated `AnalyserNode` inserted between
its `GainNode` and the master `_mixGain`. `getStemRMS(name)` reads
`getFloatTimeDomainData()` each animation frame. Safe to call at 60 fps —
reads from the analyser's internal buffer with no allocation.

**Waveform thumbnail** — `getStemWaveform(name, numPoints)` downsamples the
decoded `AudioBuffer` to `numPoints` RMS values synchronously. Called once
after stem load; the result drives the `WaveformView` canvas.

**Pitch-preserving speed** — `setTempo(rate)` tries the SoundTouch
AudioWorklet's `tempo` parameter first (pitch-preserving). Falls back to
`setPlaybackRate()` (pitch-shifts) if the worklet is not loaded. `SpeedControl`
calls `setTempo()` so the caveat note is only shown when the worklet fallback
is active.

**Per-stem XHR progress** — `loadStem(name, url, onProgress)` uses
`XMLHttpRequest` (not `fetch`) because XHR exposes `onprogress` with
`lengthComputable`. `App.jsx` maps this to per-stem progress bars during
the initial stem download.

---

## Frontend state (App.jsx)

Key state slices and what they drive:

| State | Type | Drives |
|---|---|---|
| `songs` | `Song[]` | `SongSelector` list |
| `selectedSongId` | `string\|null` | Which song is loaded in the engine |
| `manifest` | `object\|null` | Stem list, metadata, available features |
| `stemUiState` | `{[name]: {muted, soloed, volume}}` | Channel strips, engine gain |
| `stemProgress` | `{[name]: 0..1}` | Per-stem download progress bars |
| `isPlaying` | `bool` | Transport, waveform, VU meters |
| `loopStart/loopEnd` | `number\|null` | WaveformView overlay, TransportControls |
| `activeStem` | `string\|null` | Which stem's waveform is shown |
| `bpm / keyInfo` | `object\|null` | MetaCards, PitchControl transposition |
| `backendOnline` | `bool` | Offline banner with retry button |
| `sidebarCollapsed` | `bool` | Sidebar width transition |

---

## Keyboard shortcuts

Active globally when no text input is focused.

| Key | Action |
|---|---|
| `Space` | Play / Pause |
| `←` / `→` | Seek ±5 s |
| `Shift ←` / `Shift →` | Seek ±30 s |
| `[` | Set loop A at current position |
| `]` | Set loop B at current position |
| `Escape` | Clear loop |
| `1`–`6` | Solo stem by index |
| `0` | Un-solo all stems |

---

## Data format

### `manifest.json`

```json
{
  "song_id": "my_song",
  "title": "My Song",
  "stems": ["vocals", "drums", "bass", "guitar", "piano", "other"],
  "notes_available": ["vocals", "bass"],
  "separation_model": "htdemucs_6s",
  "separation_engine": "demucs",
  "demucs_model": "htdemucs_6s",
  "stem_presence": { "vocals": 78.3, "drums": 100.0, "bass": 62.1 },
  "has_lyrics": true,
  "has_beats": true,
  "has_key": true,
  "bpm": 124.5,
  "key": "A minor"
}
```

`demucs_model` is a legacy alias for `separation_model`, kept so older
Colab-output ZIPs still work without re-processing.

`stem_presence` values are normalised RMS × 100 — the loudest stem is
100, others are relative. Shown as bars in the `StemPresence` component.

### Stems

WAV files at `backend/data/<song_id>/<stem_name>.wav`. No other format —
the Web Audio API decodes WAV natively without extra libraries.

### Optional analysis files

All cached in `backend/data/<song_id>/`:

| File | Written by | Content |
|---|---|---|
| `lyrics.json` | Colab / Whisper | Word-level timestamps, segments, language |
| `beats.json` | `GET /api/songs/{id}/beats` | BPM, beat times, downbeats |
| `key.json` | `GET /api/songs/{id}/key` | Key string, mode, confidence |
| `chords.json` | Colab (Cell 8b) | Chord timeline with timestamps |
| `notes_<stem>.json` | Colab / local import | Note timeline per stem |

---

## Testing

### Frontend (Vitest + Testing Library + jsdom)

```bash
cd frontend && npm test
```

Test files live in `src/components/__tests__/` and `src/hooks/`.
AudioContext and XMLHttpRequest are fully mocked — no real audio processing.

| File | What it covers |
|---|---|
| `AudioEngine.test.js` | getStemRMS, getStemWaveform, XHR progress, setTempo |
| `WaveformView.test.jsx` | Canvas mount, seek-on-click, loop props, null engine |
| `useKeyboardShortcuts.test.js` | All 11 shortcut cases + input-focus guard + unmount cleanup |
| `ImportZip.test.jsx` | Drag-drop, file validation, API call, error display, naming table |
| `MetaCards.test.jsx` | BPM/key/duration/model render, fallback to demucs_model |
| `StemPresence.test.jsx` | Card-per-stem, bar width, empty stems, missing data |
| `SongDetail.test.jsx` | Full mount, mute/solo/volume, loading state, lyric pill |
| `ImportDrive.test.jsx` | Drive scan flow |
| `Settings.test.jsx` | Drive config save/load |
| `StepDriveFolder.test.jsx` | Wizard step — folder config |
| `StepDriveInstall.test.jsx` | Wizard step — Drive install detection |

### Backend (pytest)

```bash
cd backend && pytest tests/ -v
```

| File | What it covers |
|---|---|
| `tests/test_ingest.py` | Colab ZIP, raw-stems ZIP, alias normalisation, edge cases (17 tests) |
| `tests/test_separation_models.py` | SUPPORTED_MODELS registry completeness, dispatch validation (16 tests) |

---

## Operational notes

**Recommended workflow (Colab)**
1. Open `colab/mwtn_notebook.ipynb` on Colab (Runtime → GPU).
2. Set `SEPARATION_MODEL` and `WHISPER_MODEL` in Cell 3.
3. Upload your audio file in Cell 4 and run all cells.
4. Download the output ZIP and drag it into the mwtn UI, or copy and
   extract it into `backend/data/`.

**Local development**
```bash
cd backend && uvicorn main:app --reload   # FastAPI on :8000
cd frontend && npm run dev               # Vite on :5173
```
Vite proxies `/api` to `:8000` so the frontend HMR server and backend
share a single origin in dev.

**Mobile data implications**

| Action | Approximate data cost |
|---|---|
| Downloading a 4-stem song (4 × ~30 MB) | ~120 MB |
| Downloading a 6-stem song | ~180 MB |
| Demucs htdemucs_6s model (first run) | ~2.3 GB — **Wi-Fi only** |
| Spleeter + TensorFlow (first run) | ~1.0 GB — **Wi-Fi only** |
| BS-RoFormer checkpoint (first run) | ~0.4 GB |
| Colab notebook + pip installs | ~2–3 GB per session — **Wi-Fi only** |

The UI shows a data-cost warning before any local import that would
trigger a model download, and the onboarding wizard flags mobile data
prominently on the system-scan step.

**Large file advisory**
Stem WAV files are 20–50 MB each. Avoid loading songs on mobile data.
The UI's `StemPresence` component shows which stems have significant
content before you download them — useful for deciding whether you
actually need all 6 stems for a given song.

---

## Known limitations

- **Speed without pitch preservation**: `setTempo()` routes through the
  SoundTouch AudioWorklet when it is loaded (pitch-preserving). If the
  worklet fails to load, `setPlaybackRate()` is the fallback and pitch
  shifts with speed. Documented in `SpeedControl` via a caveat note that
  is only shown in the fallback case.
- **Monophonic note detection**: `note_extraction.py` uses `librosa.pyin`
  which assumes one note at a time. Works well on isolated bass and vocals;
  produces garbage on chords or layered stems.
- **BPM on variable-tempo songs**: librosa's beat tracker returns a global
  average. Songs with significant tempo drift will have misaligned
  metronome clicks.
- **Spleeter Python version**: Spleeter requires Python 3.8–3.11 due to
  TensorFlow. Users on Python 3.12+ should choose a different engine.
- **Electron shell is thin**: packaging and auto-update are not implemented.
  The Electron wrapper provides a desktop window and Drive config IPC only.

---

## Next steps / future work

- Background worker (Celery/RQ) for imports to decouple from the API process
- Database index for manifests to support large libraries and search
- Production CORS hardening, authentication, and rate limiting
- Pitch-preserving time-stretch verification across all stem counts
- Video/CDG/LRC lyric export (explicitly v2+)
- Full Electron packaging with auto-update
