# Architecture — Moises without the Noises

This document summarizes the repository layout, high-level architecture, and key design decisions.

## Repository layout

- `backend/` — Python FastAPI service. Hosts the REST API, serves the built frontend under `frontend/dist`, and provides endpoints for listing songs, serving stems, lyrics, beats, key, and starting local imports (`/api/import`). Audio processing helpers live in `backend/audio/` and separation logic in `separation.py`.
- `frontend/` — React app (Vite). Source is in `frontend/src/`. The built static site lands in `frontend/dist` and is mounted by the backend when present.
- `electron/` — Electron wrapper and packaging scripts for desktop distribution.
- `colab/` — Colab notebook and helper scripts (`mwtn_notebook.ipynb`, `mwtn_pipeline.py`) used to run heavy ML tasks (Demucs, Whisper) on GPU and produce the final zip expected by the app.
- `data/` and `backend/data/` — Runtime data storage for processed songs. Each song gets a folder named by `song_id` containing stems, `manifest.json`, and optional `lyrics.json`, `beats.json`, `key.json`, and `notes_<stem>.json` files.
- `storage/` — auxiliary storage used by the project (not required for core behavior).
- `docs/` — Project documentation (this file).

## Core concepts

- Processing pipeline: heavy/slow ML steps (separation, transcription, melodic analysis) are performed by the Colab notebook (recommended). The notebook produces a zip containing a folder per `song_id` with a `manifest.json` the backend reads automatically.
- Local import: `POST /api/import` accepts an uploaded file and runs Demucs locally (slower, background job). The import job writes the same on-disk layout so the rest of the app can operate identically regardless of import path.
- Manifest-driven: the backend discovers songs by the presence of `manifest.json` in `backend/data/<song_id>/`. The manifest lists available stems and metadata (bpm, key, has_lyrics, etc.).

## API surface (high level)

- `GET /api/songs` — list available manifests
- `GET /api/songs/{song_id}/manifest` — read manifest
- `GET /api/songs/{song_id}/stems/{stem_name}` — download a stem WAV
- `GET /api/songs/{song_id}/lyrics` — Whisper word-level timestamps (if available)
- `GET /api/songs/{song_id}/beats` — returns BPM and beat timestamps (computed on-demand and cached)
- `GET /api/songs/{song_id}/key` — returns detected musical key (computed on-demand and cached)
- `GET /api/songs/{song_id}/stems/{stem_name}/export` — server-side pitch-shift / time-stretch
- `POST /api/import` — upload and run local separation as a background job

## Architectural decisions & rationale

- Separation of concerns: heavy ML processing is designed to run outside the API process (Colab or background worker thread). This keeps the API responsive and avoids long-running web requests.
- Manifest-first design: using filesystem manifests avoids extra metadata storage or a database for v1. It simplifies deployment (drop a folder → app picks it up).
- FastAPI backend: lightweight, async-capable, easy static-file mounting for the frontend, and simple job-status endpoints for background imports.
- Frontend as static SPA: the UI is a single-page app built with Vite/React; the backend serves the built artifacts for a single-process deployment model.
- Pragmatic caching: expensive computations (beats, key) are computed on-demand and cached as JSON files (`beats.json`, `key.json`) to avoid recomputation.
- Cross-origin: CORS is open (`allow_origins=['*']`) for ease of local development and Electron use; tighten for production as needed.

## Data format (manifest and common files)

- `manifest.json` (per song): contains `song_id`, `title`, `stems` (list), `notes_available`, flags `has_lyrics`, `has_beats`, `has_key`, and summary fields such as `bpm` and `key` when available.
- Stems: WAV files named `<stem>.wav` (e.g., `vocals.wav`, `drums.wav`).
- Optional analysis files: `lyrics.json`, `beats.json`, `key.json`, `notes_<stem>.json`.

## Operational notes

- Recommended workflow: run `colab/mwtn_notebook.ipynb` on Colab GPU, copy the resulting zip into `backend/data/` (extract so `backend/data/<song_id>/manifest.json` exists). This is the fastest, most reliable path for v1.
- Local developers can use `POST /api/import` to import a song without Colab, but expect long runtimes on CPU.
- Be mindful of large file sizes: stems are tens of megabytes each. Avoid downloading stems on mobile data.

## Next steps / improvements

- Add a background worker (Celery/RQ) for imports and async analysis to decouple from the API process.
- Add optional database index for manifests to speed large libraries and enable search.
- Harden production CORS, add authentication, and rate-limiting for public deployments.

## Feature docs

The `docs/` folder now includes per-feature documentation pages. Each page focuses on one major subsystem, explains responsibilities, references the relevant backend endpoints and frontend components, and notes any offline or data-cost constraints.

- [Playback](Playback.md)
- [Stems](Stems.md)
- [Import](Import.md)
- [Notes](Notes.md)
- [Lyrics](Lyrics.md)
- [Beats](Beats.md)
- [Key Detection](Key-Detection.md)
- [Audio Engine](Audio-Engine.md)
- [API](API.md)
- [Frontend](Frontend.md)
- [Electron](Electron.md)
- [Contribution Guide](Contribution.md)

---

If you'd like, I can open a PR, run a quick linter, or expand any section (deployment, CI, or contributor guide).
