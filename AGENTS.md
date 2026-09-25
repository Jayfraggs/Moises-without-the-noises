agents.md — AI Agent Operating Contract
mwtn (Moises without the Noises)

This document is the single source of truth for any AI coding agent working on this codebase. Read it fully before touching a file. Deviating from these rules is a bug, not a style choice.

1. Project Identity

mwtn is an open-source, offline-first music practice tool. It separates audio into individual instrument stems (via Meta's Demucs) so musicians can practice along with isolated parts. Heavy ML inference runs on Google Colab. The local machine only plays back and displays results.

Primary users: Musicians practicing along to songs. The lead developer plays drums and is learning bass.

Non-negotiable constraint: The app must be fully functional with no active internet connection after initial setup. No CDN assets, no remote model fetches at runtime, no internet-dependent workflows in the hot path.

2. Repository Map
mwtn/
├── backend/                    # FastAPI service (Python)
│   ├── main.py                 # REST routes, static file mount, job orchestration
│   ├── separation.py           # Demucs local separation logic
│   ├── note_extraction.py      # Pitch/note analysis
│   └── audio/
│       ├── bpm.py              # librosa beat tracking
│       ├── key_detection.py    # Krumhansl-Schmuckler key detection
│       └── pitch.py            # Pitch-shift / time-stretch export
├── frontend/                   # React + Vite SPA
│   └── src/
│       ├── App.jsx             # Root component, state orchestration
│       ├── AudioEngine.js      # Web Audio API — playback, routing, stem mixing
│       ├── api.js              # Fetch wrappers to the FastAPI backend
│       └── components/
│           ├── SetupWizard.jsx         # Full-screen first-run wizard (Colab vs Local path selection)
│           ├── SetupWizard.css         # Standalone visual identity for the wizard
│           ├── TransportControls.jsx   # Play/pause/seek/loop/metronome controls
│           ├── StemControls.jsx        # Per-stem mute/solo/gain (alias: StemChannel)
│           ├── SpeedControl.jsx        # Playback rate presets + slider (authoritative speed control)
│           ├── PitchControl.jsx        # Semitone slider, key transposition preview, pitch export
│           ├── CountInControl.jsx      # Beat count-in selector (0/1/2/4 beats before playback)
│           ├── ExportPanel.jsx         # Export modal (single stem, custom mix, mix + click)
│           ├── ChordDisplay.jsx        # Chord/tab display synced to playback position
│           ├── NoteDisplay.jsx         # Hardware-tuner note readout, synced via rAF
│           ├── LyricsPanel.jsx         # Word-level lyric sync (expects words[], getCurrentTime)
│           ├── SongInfoBar.jsx         # Key / BPM badge row
│           ├── SongSelector.jsx        # Song library sidebar list
│           └── ImportSong.jsx          # Local file upload → POST /api/import
├── electron/
│   └── main.js                 # Thin Electron shell — no business logic here
├── colab/
│   ├── mwtn_notebook.ipynb     # Primary processing pipeline (GPU)
│   └── mwtn_pipeline.py        # Helper script called by the notebook
├── backend/data/               # Runtime song data (gitignored)
│   └── <song_id>/
│       ├── manifest.json
│       ├── vocals.wav
│       ├── drums.wav
│       ├── bass.wav
│       ├── guitar.wav
│       ├── piano.wav
│       ├── other.wav
│       ├── lyrics.json         # optional
│       ├── beats.json          # optional, cached on-demand
│       ├── key.json            # optional, cached on-demand
│       └── notes_<stem>.json   # optional, one per stem
└── docs/
    ├── architecture.md
    └── agents.md               # THIS FILE
3. Technology Stack
Layer	Technology	Version constraint
Frontend framework	React + Vite	Current stable
Audio playback	Web Audio API	Browser-native, no wrapper libs
Backend framework	FastAPI	Current stable
Audio analysis	librosa	Current stable
Stem separation	Demucs htdemucs_6s	Meta, 6-stem model
Transcription	OpenAI Whisper	Word-level timestamps
Key detection	Krumhansl-Schmuckler	Implemented in key_detection.py
Desktop shell	Electron	Thin wrapper only
Processing environment	Google Colab	GPU, Drive-cached model weights
Font stack	System fonts only	See §8
4. API Contract

All backend routes are prefixed /api/. CORS is open (allow_origins=['*']). Do not tighten this without explicit instruction — Electron requires it.

Endpoints
Method	Path	Description
GET	/api/songs	List all songs with available manifests
GET	/api/songs/{song_id}/manifest	Full manifest JSON for a song
GET	/api/songs/{song_id}/stems/{stem_name}	Download stem WAV
GET	/api/songs/{song_id}/lyrics	Word-level timestamp JSON (Whisper output)
GET	/api/songs/{song_id}/beats	BPM + beat timestamps (computed on-demand, cached)
GET	/api/songs/{song_id}/key	Detected key string (computed on-demand, cached)
GET	/api/songs/{song_id}/stems/{stem_name}/export	Server-side pitch-shift / time-stretch WAV
POST	/api/import	Upload file → run local Demucs separation (background job)
Manifest schema (manifest.json)
json
{
  "song_id": "string",
  "title": "string",
  "stems": ["vocals", "drums", "bass", "guitar", "piano", "other"],
  "notes_available": ["bass", "vocals"],
  "has_lyrics": true,
  "has_beats": true,
  "has_key": true,
  "bpm": 120.0,
  "key": "C major"
}

Agents must not add fields to this schema without updating both main.py and mwtn_notebook.ipynb. These two are always in sync — violating this is a critical bug.

lyrics.json schema
json
[
  { "word": "string", "start": 0.0, "end": 0.25 }
]
beats.json schema
json
{
  "bpm": 120.0,
  "beats": [0.5, 1.0, 1.5]
}
notes_<stem>.json schema
json
[
  { "time": 0.0, "note": "A2", "duration": 0.25 }
]

Note names are monophonic, single string (e.g., "A2", "C#4"). No tab notation. No sheet music. No chords.

5. Data Flow
[Google Colab]
    Demucs htdemucs_6s → stems (WAV)
    Whisper           → lyrics.json
    librosa           → beats.json (or on-demand)
    K-S algorithm     → key.json   (or on-demand)
    pitch tracking    → notes_<stem>.json
         ↓
    ZIP → user downloads → extracts to backend/data/<song_id>/
         ↓
[FastAPI backend]
    Discovers manifest.json → serves stems/metadata via REST
         ↓
[React frontend]
    api.js fetches manifest, then BPM/key/lyrics in parallel (Promise.all)
    AudioEngine.js loads stem WAVs → Web Audio API
    Components render sync'd display (lyrics, notes, beats)

Critical: Stem playback initialization must never be blocked by metadata fetches. Parallel Promise.all for BPM, key, and lyrics. Stems load independently.

6. Architectural Rules — Non-Negotiable

These are hard constraints. No agent may violate them without explicit written approval in the task prompt.

6.1 Separation of concerns
AudioEngine.js owns all Web Audio API logic. No audio node creation anywhere else.
api.js owns all HTTP calls. No fetch() calls in components or App.jsx directly.
main.py owns all route definitions. No business logic in route handlers — delegate to modules in audio/ and separation.py.
6.2 Offline-first
No CDN URLs in any source file (fonts, scripts, icons, anything).
No model weights downloaded at runtime by the frontend or backend. All model weights are pre-cached in Google Drive for the Colab path, or pre-installed for local path.
No external API calls from the frontend except to localhost (the local FastAPI backend).
6.3 Manifest drives discovery
The backend must never assume a song exists without reading its manifest.json.
No hardcoded song IDs, stem names, or file paths anywhere.
6.4 Backend ↔ Colab sync
manifest.json schema, lyrics.json schema, beats.json schema, and notes_<stem>.json schema are shared contracts between main.py and mwtn_notebook.ipynb.
Any schema change requires updating both files in the same task. Agents must flag this explicitly when it applies.
6.5 Note display is precomputed, not real-time
Note extraction runs in Colab or local import. It is never computed during playback.
Notes are displayed as a single note name string (e.g., "A2") synced via requestAnimationFrame, matching the pattern in NoteDisplay.jsx.
Do not implement real-time FFT-based note detection.
6.6 Electron is a thin shell
electron/main.js only launches the backend process and loads localhost. No audio logic, no file parsing, no business logic of any kind in Electron.
6.7 No database for v1
Song discovery is filesystem-only via manifest.json presence. Do not introduce SQLite, Postgres, or any ORM unless explicitly tasked.
7. Frontend Patterns
State ownership (App.jsx)

App.jsx owns all cross-component state:

currentSong — active manifest object
isPlaying, currentTime, duration — transport state
stems — map of stem name → { buffer, gainNode, muted, solo }
lyrics, beats, key, bpm — metadata from API

Components receive props and callbacks. They do not manage song or transport state internally.

Async data loading pattern
js
// Correct: parallel, non-blocking
const [lyrics, beats, key] = await Promise.all([
  api.getLyrics(songId),
  api.getBeats(songId),
  api.getKey(songId),
]);

// Wrong: serial, blocks stem load
const lyrics = await api.getLyrics(songId);
const beats = await api.getBeats(songId);
Lyric sync pattern

Use requestAnimationFrame to find the active word, identical to how NoteDisplay.jsx syncs notes. Do not use setInterval.

Error states

Every component that fetches data must render a non-crashing fallback when data is null or the fetch fails. A missing lyrics.json is expected — it is not an error condition.

8. Visual Design Rules

The aesthetic is dark mixing console / hardware tuner. Think rack unit, not app store.

Typography
System font stack only. No Google Fonts, no web fonts, no CDN fonts.
Stack: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif for UI text.
Monospace stack for note names, BPM readouts, time displays: 'SF Mono', 'Fira Code', 'Consolas', monospace.
Color palette (reference — derive CSS variables from these)
Token	Value	Use
--bg-base	
#0f0f0f	App background
--bg-surface	
#1a1a1a	Cards, panels
--bg-elevated	
#242424	Controls, inputs
--accent	
#e8a020	Active state, VU meters, beat markers
--accent-dim	
#7a5210	Inactive meters
--text-primary	
#f0f0f0	Primary labels
--text-secondary	#888	Secondary / metadata labels
--text-muted	#444	Disabled states
--stem-vocals	
#6ea8fe	Vocals stem color
--stem-drums	
#fd7e6e	Drums stem color
--stem-bass	
#a78bfa	Bass stem color
--stem-guitar	
#4ade80	Guitar stem color
--stem-piano	
#fbbf24	Piano stem color
--stem-other	
#94a3b8	Other stem color
Component design rules
Stem faders are vertical sliders. Not horizontal. Not toggles.
The note display mimics a hardware tuner readout — large monospace character centered in a dark panel.
Beat markers are thin vertical lines on a timeline track, colored --accent.
Lyric words highlight individually on playback. Not the whole line.
No border-radius above 4px anywhere. This is a tool, not a consumer app.
No animations except: lyric word transition (opacity), VU meter level (height). Nothing else moves.
9. Task Prompt Format

When the lead architect generates tasks, they follow this format. Agents must read every field before writing code.

### [TASK CODE] Task Title

**Target Files:** `path/to/file.ext`
**Context:** Brief operational background.

**Objective:**
Clear statement of what needs to be implemented or refactored.

**Technical Specifications:**
- Requirement 1
- Requirement 2

**Execution Constraints:**
- Do not alter existing exports unless specified.
- Maintain error propagation patterns across the API bridge.

**Output Request:**
Return ONLY the modified/created code file blocks.

Task codes follow the pattern: FE-## (frontend), BE-## (backend), NB-## (notebook), EL-## (Electron), DX-## (developer experience / tooling).

10. Known Limitations (Document, Don't Fix)

These are accepted trade-offs for v1. Do not attempt to solve them unless explicitly tasked.

Limitation	Location	Note
Pitch-shifting at non-1× playback speed degrades quality	audio/pitch.py, README	Known librosa constraint
Note detection is monophonic only	note_extraction.py, README	Works for bass/melody, not chords
Local import is 15–40 minutes on CPU (no GPU)	ImportSong.jsx warning, README	User is warned in UI
Electron shell is not code-signed	electron/	Fine for open-source personal use
Stem files are 30–80 MB each	architecture.md	Documented; avoid on mobile data

When a component touches any of these areas, it must surface the limitation to the user in plain language — not silently fail.

11. What Agents Must Never Do
Never add fetch() calls directly in components. Use api.js.
Never add internet-dependent resources (CDN links, remote model fetches, external font URLs) to any source file.
Never block stem playback on metadata resolution.
Never implement real-time note detection during playback.
Never change manifest.json schema in only one of main.py or mwtn_notebook.ipynb.
Never add business logic to electron/main.js.
Never introduce a database (SQLite, Postgres, etc.) without explicit task authorization.
Never remove the local CPU import path (POST /api/import). It must coexist with the Colab path.
Never suppress or swallow errors silently. Log to console, propagate to UI as appropriate.
Never use setInterval for playback synchronization. Use requestAnimationFrame.
12. Data Bandwidth Awareness

The lead developer frequently works on mobile data. Agents must annotate any task or operation that triggers significant data transfer.

Operation	Approximate size	Classification
Download one song's stems (6 stems)	~200–400 MB	Avoid on mobile data
Colab model weights (first run, Drive cache miss)	~3.5 GB	Unmetered only
Colab model weights (Drive cache hit)	~0 MB	Safe
Processed song ZIP from Colab	~200 MB	Avoid on mobile data
API metadata responses (manifest, beats, key, lyrics)	< 1 MB	Safe

When a new workflow involves file transfers, the agent generating the task prompt must include a Data Cost note.

13. Processing Path Reference

Two paths exist. They produce identical on-disk output. The app does not know or care which path was used.

Path A — Google Colab (recommended)
Open colab/mwtn_notebook.ipynb in Colab.
Set UPLOAD_METHOD to 'drive', 'url', or 'widget'.
Run all cells. Notebook runs Demucs (htdemucs_6s), Whisper, BPM, key, and note extraction.
Download the ZIP output.
Extract into backend/data/ so that backend/data/<song_id>/manifest.json exists.
Path B — Local CPU import
Use the ImportSong component or POST /api/import directly.
Backend runs Demucs in a background thread. Expect 15–40 minutes.
Same output layout as Path A.

Both paths require no internet connection after the ZIP is in place (Path A) or after the local import completes (Path B).

14. Open-Source Standards

This project is public and open-source.

All dependencies must have OSI-approved licenses. Check before adding.
No API keys, credentials, or user data may be committed to the repository.
backend/data/ is gitignored. Never change this.
README must always reflect the current setup workflow accurately. If a task changes setup steps, update the README in the same PR.
Demucs (MIT), librosa (ISC), Whisper (MIT), FastAPI (MIT), React (MIT), Vite (MIT), Electron (MIT) — all clear.
15. File Modification Checklist

Before submitting any code change, verify:

 No CDN URLs introduced.
 No fetch() calls outside api.js.
 No new state management in leaf components.
 If manifest schema changed: both main.py and mwtn_notebook.ipynb updated.
 Error states handled for all async operations.
 requestAnimationFrame used for any playback-synchronized display (not setInterval).
 System font stack used. No web fonts.
 New dependencies have OSI-approved licenses and are documented.
 Any data-heavy operation is annotated with a Data Cost note.
 Known limitations (§10) are not silently broken or suppressed — they are surfaced to the user.