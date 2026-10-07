# Agent Logs

## 2026-09-24
### Fix torch Version Pin for Python 3.14 (TASK-002)
- Replaced `torch==2.4.1` with `torch==2.9.1+cpu` in `backend/requirements.txt` to ensure compatibility with Python 3.14 on CPU.
- Removed the version pin for `demucs` (was `demucs==4.0.1`) to use the latest release compatible with torch >= 2.0.

### Fix soundtouch-audio-worklet Build Error (TASK-003)
- Initially added `"soundtouch-audio-worklet": "^0.3.2"` to dependencies in `frontend/package.json`.
- Encountered a 404 error during `npm install` because the package is not on the registry.
- Reverted the addition in `frontend/package.json` (removed Part A).
- Implemented the fallback (Part B): Added `build.rollupOptions.external` array containing `'soundtouch-audio-worklet'` to `frontend/vite.config.js` so that the build passes and the pitch-shifting will silently no-op at runtime.

### Fix activate.ps1 Backend Dependency Issues
- Added `setuptools` to `backend/requirements.txt` to fix a `ModuleNotFoundError: No module named 'pkg_resources'` error that occurs when `pip` attempts to build the `openai-whisper` wheel under Python 3.14 environments.

### Comment Out Local-Only ML Dependencies (TASK-004)
- Commented out `torch`, `demucs`, `openai-whisper`, `ffmpeg-python` and `--extra-index-url` in `backend/requirements.txt` since they are only required for local ML inference.
- Left `fastapi`, `uvicorn`, `python-multipart`, `librosa`, `soundfile`, and `numpy` uncommented as they are used at runtime regardless of the separation path.

### Rebuild OnboardingWizard with System-Spec Detection (TASK-005)
- Rewrote `frontend/src/components/OnboardingWizard.jsx` into a 4-step wizard.
- Step 2 now uses `navigator` APIs to detect RAM, CPU threads, platform, and network connection type.
- Step 3 scores the system for local Demucs usage and highlights the recommended setup path (Colab vs Docker).
- Step 4 implements paginated setup instructions for the chosen path (6 sub-steps for Colab, 4 for Docker).
- Maintained the existing `onComplete` prop interface and inline CSS strategy as requested.

## 2026-09-24 (Bug-fix + Wizard rebuild session)

### Fix LyricsPanel prop mismatch — lyrics always showed "No lyrics available" (BUG-001)
- Root cause: `App.jsx` was passing `engine` and `lyrics` (the full API response object `{ available, words }`) to `LyricsPanel`, which expects `words` (the array) and `getCurrentTime` (a function).
- Fix: updated the `<LyricsPanel>` call in `App.jsx` to pass `words={lyrics?.words ?? null}` and `getCurrentTime={() => engine.getCurrentTime()}`.

### Fix duplicate disconnected speed control (BUG-002)
- Root cause: `TransportControls.jsx` contained its own local `speed` state and a `<select>` that called `engine.setPlaybackRate()` directly. This bypassed App's `playbackRate` state and `handleRateChange` entirely, making the two speed controls desynchronised.
- Fix: removed the local `speed` state, `handleSpeedChange` handler, `SPEED_STEPS` constant, and the speed `<select>` JSX block from `TransportControls`. The standalone `<SpeedControl>` component rendered below the transport is the authoritative speed control.

### Fix CountInControl — selected beat count never visually active (BUG-003)
- Root cause: `CountInControl.jsx` had no `value` prop and hardcoded `aria-pressed={false}` on every option button, so the currently selected beat count was never highlighted.
- Fix: added `value` prop to `CountInControl`; wired `aria-pressed={value === opt}`; applied amber background + dark text to the active button via inline style conditional. Updated `App.jsx` to pass `value={countInBeats}`.

### Add missing CSS — metronome controls, export panel, button variants (BUG-004)
- Root cause: `btn-toggle`, `transport__metronome-control`, `transport__metronome-volume`, `export-panel` (and sub-classes), `btn`, `btn-primary`, `btn-secondary`, `error-text`, `muted` had zero CSS rules. Metronome button, export panel, and all generic buttons were completely unstyled.
- Fix: appended all missing rule sets to `App.css`, using the existing design token system (`--bg`, `--surface`, `--surface-2`, `--border`, `--text`, `--text-dim`, `--amber`, `--teal`, `--red`, `--font-ui`, `--font-data`). No new tokens introduced.

### Rewrite PitchControl and SpeedControl to use design system (BUG-005)
- Root cause: both components used dense inline `style={{}}` objects with hardcoded hex values (`#121212`, `#f0f0f0`, `#e8a020`, etc.), bypassing the CSS token system entirely and visually diverging from the rest of the app.
- Fix: rewrote both components to use BEM-style CSS classes (`pitch-control__*`, `speed-control__*`). Added corresponding rule sets to `App.css` consuming the existing design tokens. No new dependencies.
- Also added a unified `controls-row` container in `App.jsx` that groups SpeedControl, CountInControl, and PitchControl in a single bordered panel with dividers, eliminating the loose `style={{ marginTop }}` inline layout that was there before.

### Replace OnboardingWizard with new full-screen SetupWizard (FEAT-001)
- Previous `OnboardingWizard` was a modal overlay anchored inside the app shell with inline styles; visually it lacked a distinct identity from the main app.
- New `SetupWizard` is a full-screen takeover with its own dedicated stylesheet (`SetupWizard.css`).
- Visual concept: recording-booth darkness — amber top-border glow (mirrors the hardware tuner LED motif), scanline background texture, spec table with ✓/↓ pass-fail indicators, highlighted recommendation card, amber-filled step progress bar.
- Steps: Welcome → System scan (auto-advances at 900 ms) → Path selection (Colab vs Local, scored from navigator APIs) → Step-by-step guide for chosen path (6 steps for Colab, 4 for Local).
- Files added: `frontend/src/components/SetupWizard.jsx`, `frontend/src/components/SetupWizard.css`.
- `OnboardingWizard.jsx` retained in the repo (not deleted) — the import in `App.jsx` now points to `SetupWizard`.
- `useOnboarding` hook and `localStorage` persistence unchanged.
- Build verified: `npm run build` produces zero errors or warnings (50 modules, 190 KB JS, 20 KB CSS).

## 2026-09-25

### Auto-rebuild on launch — stale dist fix (DX-001)
- Root cause: Electron loads `http://localhost:8000` which serves `frontend/dist/` (a compiled static bundle). Any `src/` changes made after the last `npm run build` were invisible at runtime.
- Fix (run.ps1): replaced the hard `dist/index.html` existence guard with a mtime-based staleness check.
  - Collects all files under `frontend/src/**`, `vite.config.js`, and `package.json`.
  - Compares the newest mtime against `frontend/dist/index.html`.
  - If `src` is newer → runs `cmd /c npm run build` in the `frontend/` directory (uses `cmd` to bypass PowerShell's execution-policy restrictions on npm) and aborts on failure.
  - If already up to date → skips build and prints "Frontend is up to date (no rebuild needed)."
  - If `dist` doesn't exist at all → builds unconditionally (first-run path).
- Fix (activate.ps1): added comments clarifying that the build in step 2 is a one-time first-run step; subsequent incremental rebuilds are handled automatically by `run.ps1`.
- Files modified: `run.ps1`, `activate.ps1`.

---

## Session: 2026-09-26 — stemdeck review + model selection

### Changes shipped

**Backend**
- `backend/separation.py` — Full rewrite. `run_separation()` now accepts `model_name` param (`htdemucs_ft` or `htdemucs_6s`). `SUPPORTED_MODELS` dict defines stems + description per model. `DEFAULT_MODEL = 'htdemucs_6s'`. Computes `stem_presence` (normalised RMS % per stem) after separation and writes it into `manifest.json`.
- `backend/main.py` — New `GET /api/config` endpoint returns available Demucs models + default to the frontend. `POST /api/import` now accepts `?model=` query param (validated against `SUPPORTED_MODELS`). Job record includes model name. `DELETE /api/songs/{song_id}` added. Lifespan hook cleans up orphan song dirs on startup.

**Frontend**
- `frontend/src/api.js` — `getAppConfig()` added. `importSong(file, model)` now passes `?model=` to the backend.
- `frontend/src/components/ImportSong.jsx` — Rewrites with model selector dropdown. Fetches available models from `/api/config` on mount; falls back to hardcoded list. Shows stems for selected model. Status row now shows STATE label above message.
- `frontend/src/components/MetaCards.jsx` — New component. Compact info pills: BPM (amber accent), KEY (+ mode), DURATION, MODEL. Inserted in App.jsx above TransportControls.
- `frontend/src/components/StemPresence.jsx` — New component. Per-stem horizontal energy bars driven by `manifest.stem_presence` (normalised RMS %). Colour-coded by stem type using CSS tokens.
- `frontend/src/components/StemControls.jsx` — `MiniMeter` added: per-channel VU meter canvas using rAF, green/amber/red zones, peak-hold decay. Colour stripe on left edge of each strip keyed to `--stem-color` token. `is-muted` dims entire strip. `is-soloed` lights stripe amber.
- `frontend/src/components/SongSelector.jsx` — Rewrite with live search (filters by title/song_id), BPM pill, key pill, model pill (4s/6s badge), keyboard-accessible list.
- `frontend/src/components/SongInfoBar.jsx` — Now shows song title (capitalised), plus `model-badge` for the Demucs model that processed the song.
- `frontend/src/App.jsx` — `sidebarCollapsed` state + toggle button (`‹`/`›`). MetaCards and StemPresence inserted after SongInfoBar. `getAppConfig` import added.
- `frontend/src/App.css` — CSS tokens for stem colours (`--stem-vocals/drums/bass/guitar/piano`). Styles for MetaCards, StemPresence, MiniMeter/stripe, ImportSong model selector, SongSelector search+pills, sidebar collapse.

**Colab notebook** (`colab/mwtn_notebook.ipynb`)
- Cell 7 (config): `htdemucs_ft` documented with full trade-off description; model-info summary print added.
- Cell 21 (manifest): `stem_presence` computed (normalised RMS per stem × 100) and written into `manifest.json`. Displayed in frontend StemPresence cards.

### What was deliberately NOT ported from stemdeck
- stemdeck's Electron-native tray icon and always-on-top toggle — out of scope for the thin Electron shell
- stemdeck's bundled yt-dlp download path — licensing/copyright risk for an open-source project
- stemdeck's hardcoded 2-stem model (htdemucs) — we have the superior 6s/ft selection already

---

## Session: 2026-09-26 — multi-engine separation support

### New engines added

All engines are MIT-licensed and opt-in (install on demand, not pulled into requirements.txt by default).

| Engine key(s) | Backend | Stems | pip install |
|---|---|---|---|
| `htdemucs_ft`, `htdemucs_6s` | Demucs (existing) | 4 / 6 | already in reqs |
| `spleeter:2stems`, `spleeter:4stems`, `spleeter:5stems` | Spleeter (Deezer) | 2/4/5 | `spleeter` |
| `umxl`, `umxhq` | Open-Unmix (Inria) | 4 | `openunmix torchaudio` |
| `mdx-vocalft`, `mdx-inst-hq3` | MDX-Net via audio-separator | 2 | `audio-separator[cpu]` |
| `bs-roformer` | BS-RoFormer via bs-roformer-infer | 6 | `bs-roformer-infer` |
| `melband-roformer` | Mel-Band RoFormer via melband-roformer-infer | 2 | `melband-roformer-infer` |

### Files changed

**Backend**
- `backend/separation.py` — full rewrite. `SUPPORTED_MODELS` dict now covers all 11 model keys. Six `_run_<engine>()` functions implement each backend. `_ENGINE_RUNNERS` dispatch table. `run_separation()` still the single public entry point — unchanged interface for `main.py`. `separation_engine` + `separation_model` written into manifest alongside legacy `demucs_model` key.
- `backend/main.py` — `/api/config` now returns `separation_models` dict (richer, includes `engine`, `pip_hint`, `data_cost_mb`) alongside legacy `demucs_models` for backward compat.
- `backend/requirements.txt` — optional engine installs documented as commented-out pip commands with notes on model download sizes.

**Frontend**
- `frontend/src/components/ImportSong.jsx` — model selector now uses `<optgroup>` to group by engine family. Reads `separation_models` from `/api/config` (falls back to `demucs_models` then hardcoded list). `DataCostWarning` component shows first-run download size in amber; flags Wi-Fi for anything ≥ 1 GB.
- `frontend/src/components/MetaCards.jsx` — prefers `separation_model` key in manifest, falls back to `demucs_model`.
- `frontend/src/components/SongSelector.jsx` — model pill abbreviates engine names cleanly for all engines, not just Demucs 4s/6s.
- `frontend/src/App.css` — `.import-song__data-warning` style.

**Colab notebook** (`colab/mwtn_notebook.ipynb`)
- Cell 1 (markdown): install table for all engines, per-engine data cost table, mobile data warning.
- Cell 2 (code): optional commented-out install lines for each non-default engine.
- Cell 3 (config): replaced `DEMUCS_MODEL` / `WHISPER_MODEL` with `SEPARATION_MODEL`, `SEPARATION_ENGINE`, `ENGINE_DISPATCH`, `MDX_MODEL_KEYS`. Full model-choice table in comments.
- Cell 5 (code): full engine dispatcher — `if/elif` blocks for demucs, spleeter, openunmix, mdxnet, bs_roformer, melband_roformer.
- Cell 10 (manifest): records `separation_model`, `separation_engine`, and legacy `demucs_model` key.

### Design decisions

- **audio-separator over raw MDX-Net** — MDX-Net has no pip-installable inference package; `audio-separator[cpu]` from karaokenerds is the established thin wrapper with ONNX Runtime, GPU support, and model auto-download. MIT-licensed.
- **bs-roformer-infer / melband-roformer-infer** — the architecture packages (lucidrains/BS-RoFormer) have no bundled checkpoints or CLI. The openmirlab inference packages provide sha256-verified checkpoint auto-download and a clean Python API. Both MIT.
- **Spleeter's TF constraint documented** — Spleeter requires Python 3.8–3.11 and TensorFlow; noted in pip_hint so users on Python 3.12+ know before they install.
- **`data_cost_mb` exposed in `/api/config`** — the frontend shows a Wi-Fi warning before the user triggers a local import that would download hundreds of MB on mobile data.

---

## Session: 2026-09-26 — Priority fixes, test suite, ZIP drag-drop, docs

### Priority tasks completed

**P1 — getStemRMS() / VU meters (was broken)**
- `AudioEngine.js`: AnalyserNode (fftSize=256, smoothing=0.8) inserted between
  each stem's GainNode and the master _mixGain. `getStemRMS(name)` reads
  `getFloatTimeDomainData()` each rAF frame — no allocation per call.
  `unloadAll()` patched to also disconnect analyserNodes (was a leak).
  `getStemWaveform(name, numPoints)` added — downsamples decoded AudioBuffer
  to N RMS values synchronously for the static waveform display.

**P2 — Waveform view**
- `WaveformView.jsx` (new): dual-layer canvas. Static RMS waveform from
  `getStemWaveform()`, teal tint over played region, white playhead, amber
  loop region overlay with A/B labels. Click/drag to seek via pointer
  capture. Mounted in App.jsx above TransportControls.
- `App.jsx`: `loopStart`, `loopEnd`, `activeStem` state lifted to App.
  Stem-picker row (coloured buttons) switches which stem's waveform is shown.
- `TransportControls.jsx`: `onLoopChange` prop added; all three loop
  mutations (markStart, markEnd, clearLoop) call it so WaveformView updates.

**P3 — Keyboard shortcuts**
- `hooks/useKeyboardShortcuts.js` (new): Space, ←/→ (±5s), Shift+←/→ (±30s),
  `[`/`]` (loop A/B), Escape (clear loop), 1–6 (solo by index), 0 (un-solo all).
  Input-focus guard prevents firing when user types in search/lyrics/etc.
  Cleans up the event listener on unmount.
- Wired into App.jsx with `useKeyboardShortcuts({...})`.

**P4 — Stem download progress bars**
- `AudioEngine.js`: `loadStem()` rewritten to use XMLHttpRequest instead of
  fetch — XHR has `onprogress` with `lengthComputable`, fetch does not.
  `onProgress(0..1)` callback parameter added (optional, defaults null).
- `App.jsx`: `stemProgress` state ({name: 0..1}), updated via callback,
  reset on song change. Progress bar grid rendered above WaveformView while
  any stem is < 100%. Disappears automatically once all stems are loaded.

**P5 — Delete confirmation**
- `App.jsx` `handleDeleteSong`: `window.confirm()` added with song title and
  explicit "cannot be undone" warning before any delete call.

**P6 — Loop region overlay on waveform**
- Implemented as part of WaveformView (P2). Amber fill, left/right edge lines,
  "A"/"B" text labels. Props: `loopStart`, `loopEnd` (both nullable).

**P7 — Pitch-preserving speed via SoundTouch tempo param**
- `AudioEngine.js` `setTempo(rate)`: checks for SoundTouch worklet's `tempo`
  (or `rate`) AudioParam first; if found, sets it directly without restarting
  sources. Falls back to `setPlaybackRate()` if worklet is unavailable.
- `App.jsx`: `handleRateChange` and the song-load rate reset now call
  `setTempo()` instead of `setPlaybackRate()`.
- `SpeedControl.jsx` caveat note ("Pitch shifts at speeds other than 1×")
  is now only shown when the worklet fallback is active (not when worklet
  tempo param is in use) — future task, currently always visible.

**P8 — Backend offline detection**
- `App.jsx` `refreshSongs()`: catches network-level fetch errors (message
  contains 'fetch', 'Failed to fetch', 'NetworkError', 'net::ERR') and sets
  `backendOnline: false` rather than populating `loadError`.
- Offline banner rendered with clear instructions for starting the server
  (Electron-aware: different message for Electron vs browser). Retry button
  calls `refreshSongs()` directly.

**ZIP drag-drop ingest (new feature)**
- `backend/ingest.py` rewritten. Two ZIP shapes supported:
  1. Colab-pipeline ZIP (has manifest.json) — extracted as-is.
  2. Raw-stems ZIP (loose WAVs, no manifest) — stems normalised by filename
     via STEM_NAME_ALIASES dict, manifest auto-generated.
  Path-traversal safety check on all ZIP entries. Idempotent (re-ingest
  of existing song_id returns existing manifest).
- `backend/main.py`: `POST /api/ingest/upload` (new) — multipart file
  upload + ingest in one call. Validates .zip extension, saves to tmp,
  ingests, deletes tmp.
- `frontend/src/api.js`: `ingestUpload(file, onProgress)` added — uses
  XHR for upload progress events.
- `frontend/src/components/ImportZip.jsx` (new): drag-and-drop or
  click-to-browse. Handles Colab ZIPs and raw-stems ZIPs. Upload progress
  bar. Success / error status. Collapsible naming conventions table listing
  all recognised aliases per canonical stem. Wired into App.jsx sidebar.

### Test suite

New test files (all new this session):
- `frontend/src/components/__tests__/AudioEngine.test.js` (10 tests)
- `frontend/src/components/__tests__/WaveformView.test.jsx` (8 tests)
- `frontend/src/components/__tests__/useKeyboardShortcuts.test.js` (11 tests)
- `frontend/src/components/__tests__/ImportZip.test.jsx` (7 tests)
- `frontend/src/components/__tests__/MetaCards.test.jsx` (7 tests + 4 StemPresence)
- `backend/tests/test_ingest.py` (17 tests)
- `backend/tests/test_separation_models.py` (16 tests)

Vitest config: `vite.config.js` updated with `test: { globals, environment: jsdom,
setupFiles }`. `src/setupTests.js` created with `@testing-library/jest-dom` import.

Total test inventory: 93 tests across 11 test files.

### Docs
- `docs/architecture.md` fully rewritten: repo layout, all processing paths,
  ZIP naming conventions table, all 11 separation engines, full API surface
  (17 endpoints), AudioEngine design notes, frontend state table, keyboard
  shortcut reference, data format specs, test inventory, operational notes
  with mobile data cost table, known limitations, and next steps.

### Bug fixes (spotted during audit)
- `unloadAll()` was not disconnecting AnalyserNodes added this session — patched.
- Rate-change and song-load rate-reset both called `setPlaybackRate()` directly
  in App.jsx, bypassing the pitch-preserving path — both patched to `setTempo()`.
- `SongSelector` model pill used `4s`/`6s` Demucs-only abbreviation — updated to
  handle all engine names via `replace()` chain.
- `MetaCards` only read `demucs_model` from manifest — updated to prefer the
  new `separation_model` key with fallback.

---

## Session: 2026-09-28 — Gap fix, model selector in UI, ingest.py bug

### Bug fixed — ingest.py line 71

`_is_safe_path()` used `name.replace("\\", "/")` — the backslash in a
regular Python string literal is an invalid escape sequence (`\"`  is not a
recognised escape, so Python 3.12+ raises `DeprecationWarning` and 3.13+
raises `SyntaxError` during compilation). The archive member normalisation
lines (138, 189) used `"\\\\"` which only replaces pairs of backslashes
(Windows long-path UNC style) and silently missed ordinary single-backslash
Windows ZIP entries.

Fix: extracted a `_normalise_zip_path()` helper that uses `chr(92)` (the
backslash character, unambiguously) rather than a string escape. All three
call sites updated. `ingest.py` fully rewritten for clarity — same logic,
clean escaping throughout. Verified with `ast.parse()`.

### Gap fixed — Colab/Electron folder name mismatch

Root cause: the notebook hardcoded `mwtn_outputs` (underscore) to Google
Drive, but `driveDetect.js` defaulted to `mwtn-outputs` (hyphen). These
never matched, so `ImportDrive` scanned the wrong path and found nothing.

Fix:
- Notebook Cell 3: new `DRIVE_OUTPUT_FOLDER = 'mwtn-outputs'` variable
  (now matches the Electron default). Cell 21 now uses that variable —
  no more hardcoded path. An explicit comment says it must match the
  Settings panel.
- `electron/driveDetect.js`: fixed typo `DEFAULT_MWNT_FOLDER` →
  `DEFAULT_MWTN_FOLDER`. Value confirmed as `'mwtn-outputs'`.

### Model selector in Electron Settings panel

Users can now change their default separation model from the Settings panel
(gear icon) without touching any code. The choice is:
- Shown in the UI with stems list, data cost, and a reminder to set the
  matching `SEPARATION_MODEL` in the Colab notebook Cell 3.
- Persisted to `mwtn-config.json` via the existing `driveDetect` config
  system (new `defaultModel` field added to `normalizeConfig`).
- Read by `ImportSong.jsx` on mount — the dropdown pre-selects the user's
  saved model.

IPC chain: `Settings.jsx` → `electronAPI.setDriveConfig(path, folder, model)`
→ `preload.js` contextBridge → `ipcMain.handle('drive:setConfig')` →
`setDriveConfig(userData, path, folder, model)` → `mwtn-config.json`.

### Colab quick-launch button

Settings panel now has an "Open notebook in browser" button that calls
`shell.openExternal()` via `electronAPI.openExternal()`. No OAuth, no API
integration — opens the notebook URL in the system's default browser. This
is the correct approach for v1: Colab's own auth handles everything, the
GPU is free, and there are no API preview risks or rate limits.

The button links directly to the GitHub-hosted notebook so users always get
the latest version. After the notebook finishes, they click "Scan Drive" in
the same Settings panel to import the new song.

### Files changed (this session only)

- `backend/ingest.py` — full rewrite (bug fix + `_normalise_zip_path`)
- `backend/tests/test_ingest.py` — 5 new `TestNormaliseZipPath` tests (22 total)
- `colab/mwtn_notebook.ipynb` — Cell 3: `DRIVE_OUTPUT_FOLDER` variable; Cell 21: variable used
- `electron/driveDetect.js` — typo fix, `defaultModel` in config
- `electron/main.js` — `drive:setConfig` IPC handler forwards `defaultModel`
- `electron/preload.js` — `setDriveConfig` contextBridge forwards `defaultModel`
- `frontend/src/components/Settings.jsx` — full rewrite: Colab button, model selector, folder mismatch warning
- `frontend/src/components/DriveConfigFields.jsx` — hint updated to reference notebook variable name
- `frontend/src/components/ImportSong.jsx` — reads saved model from Electron config on mount
- `frontend/src/App.css` — Settings section styles
## Notebook integration

- 2026-10-06: Added madmom installation and beat/meter-analysis cells to `colab/mwtn_notebook.ipynb`; the legacy librosa cell is retained as a non-executing reference.

## Tests

- 2026-10-06: Added deterministic unit coverage for duration-to-tick conversion helpers.
- 2026-10-06: Made duration lookup strict by default and preserved exact triplet matches over nearby dotted durations.
- 2026-10-06: Added synthetic unit coverage for meter detection and beat-grid query behavior.
- 2026-10-06: Added synthetic unit coverage for quantization, tuplets, rests, and measure validation.
- 2026-10-06: Corrected humanized beat snapping and triplet classification for synthetic quantization cases.
- 2026-10-06: Corrected triplet-group duration validation to span one complete beat.

## Harmonic context

- 2026-10-06: Added versioned harmonic key maps, enharmonic spelling, and legacy `key.json` migration.
- 2026-10-06: Added optional-autochord and offline-librosa chord detection with beat-aligned cache artifacts.
- 2026-10-06: Added non-breaking key-map, key-override, chord-detection, and chord-correction API routes; the existing cached `GET /chords` route is preserved.
- 2026-10-06: Added focused harmonic-context and API test coverage; direct smoke tests pass while this virtual environment lacks pytest.
- 2026-10-06: Added Colab harmonic-analysis cells for autochord installation, time-varying key maps, and beat-aligned chord detection.
- 2026-10-06: Added React HarmonicAnalysis components for synchronized key display, chord timeline, overrides, loading, and error states.
- 2026-10-06: Updated PowerShell startup scripts with required/optional dependency diagnostics, transcription-config validation, backend health reporting, mobile-data guidance, and Electron/browser fallback handling.
- 2026-10-06: Added pure unit coverage for harmonic pitch mapping, enharmonic spelling, scales, chromatic checks, key-map ranges, serialization, round-trips, and legacy cache migration.
- 2026-10-06: Added chord-detection unit tests and harmonic-pipeline integration tests covering parsing, merging, beat alignment, key-map caching, librosa fallback, and chord cache writes.

## Solfa

- 2026-10-06: Added a dependency-free movable-do solfège resolver and extended the canonical musical-event contract with optional solfège metadata.
- 2026-10-06: Added a cached, stem-level solfège API endpoint with legacy note/key artifact compatibility.
- 2026-10-06: Updated the active static solfège lane to consume stem-level results, render rests, and center the active event with a CSS transform.
- 2026-10-06: Added idempotent Colab solfège artifact generation to the pipeline and notebook before output packaging.
- 2026-10-06: Repaired activate.ps1 encoding and verified PowerShell parsing.
- 2026-10-06: Fixed run.ps1 port cleanup loop by renaming the `$pid` variable to avoid PowerShell's read-only `$PID` automatic variable.
- 2026-10-06: Hardened Colab notebook Cell 7 to locate the mwtn repository before importing backend beat-tracking code, with an actionable missing-source error.
- 2026-10-06: Fixed Colab harmonic-analysis cells to reuse dynamic repository discovery and avoid hardcoded /content/mwtn audio/cache paths.
- 2026-10-06: Repaired malformed Colab output-assembly Cell 10 source that had been split into one-character strings, causing an unterminated-string SyntaxError.
- 2026-10-06: Repaired widespread mojibake in colab/mwtn_notebook.ipynb by restoring UTF-8 text and validated the notebook JSON.
## 2026-10-06 — Frontend migration

### Structure
- Promoted the existing vanilla frontend from `frontend/static/` to `frontend/`.
- Added native module entry point, observable store, and UI module extension points.

### Backend
- Changed FastAPI static serving to mount `frontend/` directly.

### Verification
- Confirmed the new entry point and store exist and retain ES-module syntax.

## 2026-10-06 — Recovered harmonic panels

### Feature
- Replaced deleted React harmonic analysis panels with native DOM rendering.
- Added key-map/chord detection API wrappers and playback-synchronized chord highlighting.
- Added harmonic panel markup and scoped CSS.

### Verification
- `node --check` passed for the new harmonic module and modified API/app modules.

## 2026-10-06 — Frontend encoding cleanup

- Removed mojibake/non-ASCII corruption from `frontend/index.html` after the direct frontend copy.
- Rewrote the file as UTF-8 without a BOM and verified no `â`, `Â`, or `Ã` markers remain.

## 2026-10-06 — Browser runtime fixes

- Fixed the harmonic chord-label expression that mixed nullish coalescing and logical OR without parentheses.
- Replaced the non-standard vertical slider appearance with native vertical writing mode.
- Added a local `frontend/favicon.svg` and linked it from the app shell.
- Verified harmonic/app JavaScript syntax and favicon serving.

## 2026-10-06 — User-resizable analysis panels

- Added persistent drag handles for harmonic analysis, bass solfa, and lyrics panels.
- Added keyboard resizing with arrow keys and double-click reset behavior.
- Added responsive resize styling and preserved the harmonic handle across rerenders.

## 2026-10-06 — Harmonic analysis and responsive UI

### Backend
- Removed the hard prerequisite for an existing `beats.json`; chord detection now builds beat analysis on demand.

### Frontend
- Added error handling for the harmonic Analyze action.
- Added responsive breakpoints for sidebar, metadata panels, topbar, mixer, and mobile layouts.
- Restored colorful bass solfa syllables using stable per-syllable color mapping.

### Verification
- Frontend harmonic and solfa modules pass `node --check`.
- Python validation was unavailable because the environment could not launch `python.exe` or `py.exe`.
## 2026-10-06 — Solfa colour restoration

- Added shared solfa colour resolver and CSS variables.
- Updated the active vanilla SolfaPanel to respect `solfa_colours`, including active brightness and live refresh events.
- Loaded the persisted setting during app startup.
## 2026-10-06 — Plan 12 UI stubs

- Changed the extract panel's Colab action to an inline Plan 12 status message instead of throwing.
- Kept Local CPU import available.
- Routed mix/stem export buttons to the existing Studio export methods.
- Added explicit status messaging for unavailable MIDI, MusicXML, and click-track exports.
## 2026-10-06 — Frontend boot repair

- Removed duplicate initialization of the legacy and rewritten extract panels.
- Added the extract panel stylesheet to the actual served frontend entrypoint.
## 2026-10-06 — Frontend duplicate archive

- Moved the unused `frontend/static/` duplicate tree to `frontend/_archive/static-2026-10-06/`.
- The active frontend remains under `frontend/index.html`, `frontend/js/`, and `frontend/css/`.
- The archive is recoverable and contains 38 files.
## 2026-10-06 — Restore packaged frontend layout

- Restored `frontend/static/` from the archive after `run.ps1` reported it missing.
- Copied the current frontend HTML, JavaScript, and CSS into `frontend/static/`.
- Updated FastAPI static mounting to serve `frontend/static/`, matching the launcher and packaged project layout.
## 2026-10-06 — Fix extract panel syntax error

- Replaced the fragile nested one-line extract panel template with simpler pane builders.
- Corrected missing array brackets in note-duration and confidence-threshold option lists.
- Synchronized the corrected module into `frontend/static/js/ui/extractPanel.js`.
- Validated both served and source modules as ES modules.
## 2026-10-06 — Resizable panel startup guard

- Guarded `clamp` and `addHandle` against missing panel elements.
- Synchronized the fix to `frontend/static/js/resizablePanels.js`.
- This prevents optional/missing panels from aborting the entire application boot.
## 2026-10-06 — Force resizable module cache refresh

- Confirmed HTTP served `resizablePanels.js` contains the null guard.
- Added versioned `resizablePanels.v2.js` and changed the app import to bypass stale browser/Electron module cache.
- Synchronized the versioned module and app entrypoint into `frontend/static/`.
## 2026-10-06 — Resizable panel cache/runtime hardening

- Confirmed the served v2 module still contained the failing `dataset` access.
- Replaced panel dataset reads/writes with attribute access and added versioned `resizablePanels.v3.js`.
- Updated the served app entrypoint to import v3, bypassing Electron/browser cache reuse.
## 2026-10-06 — Fix resizable panel argument order

- Corrected all `applyHeight` calls to pass `(panel, height)` as defined.
- Synchronized the fix to the served v3 module and canonical frontend tree.
## 2026-10-06 — Solfa, collapse, and playback layout

- Applied shared syllable colours directly to bass solfa text, including active-note brightness.
- Reworked lyrics and solfa collapse controls to use `hidden` and panel state classes.
- Updated panel resizing to reserve transport and footer playback space.
- Synchronized all changes into `frontend/static/`, the served frontend tree.
## 2026-10-06 — Dynamic extraction model settings

- Replaced hardcoded extraction model choices with the backend configuration catalogue.
- Regenerate selectable stems from the selected model’s 2-, 4-, 5-, or 6-stem outputs.
- Persist selected stems locally and added an Extract & Analyse end-user guide.
- 2026-10-06 — Added `backend/jobs/notebook_generator.py` with `NotebookSettings`, strict parameters-cell lookup, JSON-safe string rendering, and immutable template generation for Colab exports.
- 2026-10-06 — Added notebook download and parameter-text API routes to `backend/main.py`; routes create queued notebook jobs, generate in worker threads, slug filenames, and return structured generation failures.
- 2026-10-06 — Added frontend Run Panel notebook flow, API client helpers, extract-panel wiring, polling tracker, clipboard fallback, and styling for Colab/local execution paths.
