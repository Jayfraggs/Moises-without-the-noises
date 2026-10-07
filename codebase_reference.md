# Codebase Reference

## Extract panel model selection

- `frontend/js/ui/extractPanel.js`: loads `API.getConfig()` and renders only model-supported output stems.
- `docs/features/extract-panel-user-guide.md`: user-facing explanation of each Extract & Analyse tab.

## Harmonic context

`backend.audio.harmonic_context` provides a time-ranged `KeyMap` plus
key-aware enharmonic spelling. It migrates legacy global-key `key.json` files
and preserves their compatible `key` and `confidence` fields when caching.

`backend.audio.chord_detection` uses optional offline `autochord` inference
with a local librosa template fallback, then persists canonical beat-aligned
`ChordEvent` records in `chords.json`. `backend.main` exposes `GET /keymap`,
`PATCH /key`, `GET /chords/detect`, and `PATCH /chords/{chord_id}`; the legacy
cached-only `GET /chords` route remains unchanged.

The Colab notebook runs harmonic key-map and chord cells after beat analysis;
autochord installation is optional and the chord pipeline falls back to local
librosa templates.

The requested React harmonic UI lives under `frontend/src/components/HarmonicAnalysis`.
`HarmonicPanel` fetches key maps and cached chords, uses `/chords/detect` for
on-demand analysis, and delegates synchronized key/chord rendering and edits to
`KeyDisplay` and `ChordChart`.

## Colab beat and meter analysis

`colab/mwtn_notebook.ipynb` installs madmom and delegates rhythm analysis to
`backend.audio.beat_tracker.load_or_analyze_beats`. That function invokes
`analyze_rhythm`, uses madmom when available, falls back to librosa, and writes
the versioned `beats.json` cache. The notebook retains `beats_result` for
compatibility with existing downstream cells.

## Solfa resolution

`backend.solfa.resolve_solfa` copies canonical musical events and attaches a
movable-do `solfa` value from the supplied tonic and major/minor mode. It uses
La-based minor by default, preserves rest events as `None`, and returns a
`SolfaResult` containing the resolved events and normalized key context.

`GET /api/songs/{song_id}/stems/{stem_name}/solfa` adapts the existing note
artifact format, resolves solfège from `key.json`, and atomically caches the
response as `solfa_{stem_name}.json`. The cache is reused only when it is at
least as new as both source artifacts.

The active client is vanilla JavaScript under `frontend/static`, not React.
`SolfaPanel` fetches the bass stem solfège result after a song loads and is
advanced by Studio's existing transport tick. Its lane sizes notes by duration,
shows time gaps as dotted rests, and centers the active cell with a CSS transform.

`colab/mwtn_pipeline.py` writes `solfa_<stem>.json` after key and note artifacts
are available. The notebook contains the equivalent zero-network cell before its
output assembly step, so Colab ZIPs carry the same API-compatible solfège data.
## Setup Script Encoding Repair

`activate.ps1` is the Windows setup entry point. It creates or repairs the venv,
installs requirements, and uses ASCII-safe output for reliable PowerShell parsing.
## 2026-10-06 — Vanilla frontend migration

- `frontend/index.html`, `frontend/css/`, and `frontend/js/` are the direct-served frontend.
- `frontend/js/main.js` loads the existing vanilla studio application.
- `frontend/js/state/store.js` is the shared observable store for future UI modules.
- FastAPI serves `frontend/` directly; no Vite build is required.
- Harmonic analysis is rendered by `frontend/js/harmonic.js` into `#harmonicPanel` and styled by `frontend/css/harmonic.css`.
- Chord detection builds missing beat analysis on demand; responsive layout overrides are in `frontend/css/responsive.css`.
## Solfa colours (2026-10-06)

- `frontend/js/utils/solfa.js`: shared `SOLFA_COLOURS`, `getSolfaColour`, and setting resolver.
- `frontend/js/solfa.js`: applies shared colours to the active vanilla solfa timeline.

## Notebook export generation (2026-10-06)

- `backend/jobs/notebook_generator.py` defines `NotebookSettings` and `generate_notebook`.
- The generator deep-copies `colab/mwtn_notebook.ipynb`, replaces only the cell tagged `parameters`, and returns UTF-8 notebook JSON bytes.
- User-controlled strings are JSON-escaped as Python literals. `BACKEND_URL` remains blank for the user to fill in from Colab.
- `POST /api/jobs/generate-notebook` returns the generated notebook download and `X-MWTN-Job-ID`; `POST /api/jobs/generate-params-text` returns clipboard-ready parameter source and setup instructions.
- `frontend/js/ui/runPanel.js` owns the three-path notebook execution modal and job polling; `frontend/js/api.js` owns notebook/job requests.
