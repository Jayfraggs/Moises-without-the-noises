# MWTN Feature Changelog

## [Feature Drop] Vocal Split · Section Detection · Beat Grid Editor

---

### Overview

Three new features added. All are **opt-in and gracefully degrading** — if
the required backend library is missing, the feature skips itself with a
clear console/log message rather than crashing. Existing behaviour is
unchanged for songs processed without the new features.

---

## 1. Vocal Lead / Backing Split

**What it does:** Takes the already-isolated `vocals.wav` from the first
Demucs pass and runs a second specialised AI pass to split it into:
- `lead_vocals.wav` — primary / foreground vocal
- `backing_vocals.wav` — harmonies / background vocal

**Model used:** `UVR-BVE-4B_SN-44100-1` (karaokenerds/python-audio-separator,
MIT licence). Falls back to `UVR_MDXNET_KARA_2` if the first model fails.
Both are ONNX-based — no GPU required, though GPU speeds them up significantly.

**Data cost:** ~200 MB ONNX model downloaded on first use, cached at
`~/.cache/audio-separator/`. On Colab, this re-downloads each session unless
you cache the directory to Google Drive.

**To enable on Colab:**
```bash
!pip install "audio-separator[cpu]"
```
Then set `RUN_VOCAL_SPLIT = True` at the top of `mwtn_pipeline.py`.

**To use after local import (POST /api/import):**
Click the "Split Lead / Backing Vocals" button that appears in the mixer
below the Vocals lane (only visible when `vocals.wav` exists and split
hasn't run yet).

---

### Files Changed

#### `backend/audio/vocal_split.py` *(NEW)*
- `run_vocal_split(song_dir, report)` — main entry point
- Tries `UVR-BVE-4B_SN-44100-1` first, falls back to `UVR_MDXNET_KARA_2`
- Normalises audio-separator's output filenames (they vary by model) to the
  canonical `lead_vocals.wav` / `backing_vocals.wav`
- Returns `{}` on any soft failure so caller can degrade gracefully
- Writes stems into `song_dir/` directly

#### `backend/main.py`
- Added `from audio.vocal_split import run_vocal_split`
- Added `POST /api/songs/{song_id}/vocal-split` endpoint
  - Returns `{ new_stems: [...], log: [...] }`
  - Updates `manifest.json` with `has_vocal_split: true` and appends new
    stems to the `stems` list
  - Returns `422` if audio-separator is not installed (with install hint)
- Added vocal split step inside `_run_import` (local import pipeline),
  guarded so it only runs if `vocals.wav` is present

#### `frontend/static/js/api.js`
- Added `API.triggerVocalSplit(songId)` — calls `POST .../vocal-split`

#### `frontend/static/js/app.js`
- Added `document.getElementById('vocalSplitBtn')` click handler
  - Disables button, shows "Splitting…", calls `API.triggerVocalSplit()`
  - On success: reloads song so new stems appear in the mixer
  - On failure: shows error in `#vocalSplitStatus` span
- Added `_updateVocalSplitUI()` — called inside the `loadSong` wrapper
  - Shows/hides `#vocalSplitRow` based on whether `vocals.wav` exists
    and split hasn't already run
  - Shows/hides `.lead_vocals` and `.backing_vocals` static lane stubs
    based on manifest `stems` list

#### `frontend/static/index.html`
- Added `lead_vocals` stem lane (`<span class="lead_vocals hidden" ...>`)
  after the `vocals` lane — hidden by default, revealed by `_updateVocalSplitUI()`
- Added `backing_vocals` stem lane — same pattern
- Added `#vocalSplitRow` trigger row containing `#vocalSplitBtn` and
  `#vocalSplitStatus`, positioned between the stem list and the rest of
  the mixer. Hidden when split isn't available or is already done.

#### `colab/mwtn_pipeline.py`
- Added `RUN_VOCAL_SPLIT = False` feature flag at top of file (set `True`
  to enable after installing audio-separator)
- Added `run_vocal_split(stems_source_dir)` function — same logic as the
  backend module but standalone (no import from backend/)
- Updated `build_output()` signature to accept `vocal_split_stems: dict | None`
- Updated `main()` to run vocal split when flag is on, pass result to
  `build_output()`
- Updated `manifest` written to zip to include `has_vocal_split` flag and
  the new stems in the `stems` list

---

## 2. Song Structure Section Detection

**What it does:** Automatically detects song structure (intro, verse, chorus,
bridge, outro, etc.) using an open-source ML model and writes the result to
`sections.json`, which the existing Sections panel in the UI then loads and
renders.

**Primary model:** `allin1` (Taejun Kim, ISMIR 2023, MIT licence). This model
was trained on the Harmonix dataset and returns both segment boundaries and
semantic labels. Install: `pip install allin1`.

**Fallback:** If `allin1` is not installed, a librosa novelty-based heuristic
runs instead. It detects boundaries using a recurrence-matrix / Laplacian
approach and labels all segments `"part"` (no semantic labels). No extra
install needed — librosa is already in requirements.

**Data cost (allin1):** ~120 MB checkpoint downloaded on first use, cached at
`~/.cache/allin1/`. On Colab this re-downloads each session unless you set
`HF_HOME` to a Google Drive path before importing allin1:
```python
import os
os.environ["HF_HOME"] = "/content/drive/MyDrive/hf_cache"
import allin1
```

**To enable on Colab:**
```bash
!pip install allin1
```
Then set `RUN_SECTION_DETECT = True` at the top of `mwtn_pipeline.py`.

**To use on an existing song (backend endpoint):**
Click "Auto-detect" in the Sections panel header. The result is persisted
to `sections.json` immediately; no page reload needed.

---

### Files Changed

#### `backend/audio/section_detection.py` *(NEW)*
- `detect_sections(song_dir, report)` — public entry point
  - Picks best available audio source from existing stems
  - Tries `_detect_with_allin1()` first
  - Falls back to `_detect_with_librosa()` if allin1 unavailable
  - Normalises raw segment list through `audio.sections.normalize_sections()`
    (same pipeline as manual section saves)
  - Writes `sections.json` atomically (write to `.tmp`, rename) and returns
    the normalised list
- `_detect_with_allin1(audio_path, duration)` — wraps `allin1.analyze()`,
  maps allin1 segment labels to mwtn section kinds
- `_detect_with_librosa(audio_path, duration)` — MFCC + delta features →
  recurrence matrix → Laplacian novelty → peak-pick boundaries
- `_map_label(label)` — label normalisation dict (pre-chorus → verse, etc.)

#### `backend/main.py`
- Added `from audio.section_detection import detect_sections`
- Added `POST /api/songs/{song_id}/sections/detect` endpoint
  - Returns `{ sections: [...], log: [...] }`
  - Returns `422` with install hint if detection produces nothing
  - Calls `_patch_manifest()` to set `has_sections: true` on success
- **Bug fix:** The existing `PATCH /api/songs/{song_id}/sections` was calling
  `normalize_sections(validated)` with only one argument; `normalize_sections`
  requires a `duration` argument as well. Fixed to derive duration from the
  max `end` value in the submitted sections before calling normalise.
- Added section detection step inside `_run_import` (runs after key detection,
  before final manifest write), non-fatal on exception

#### `frontend/static/js/api.js`
- Added `API.detectSections(songId)` — calls `POST .../sections/detect`

#### `frontend/static/js/sections.js`
- Added `this._detectBtn` — reference to `#sectionsDetectBtn`
- `init()` — added click listener → `_autoDetect()`, unhides `#sectionsDetectBtn`
- Added `_autoDetect()` method:
  - Disables button, shows "Detecting…"
  - Calls `API.detectSections(songId)`
  - On success: replaces `this._sections` and `State.sections` with result,
    calls `_render()` to draw them immediately, flashes "Detected" badge
  - On failure: shows alert with error text
  - Always restores button to enabled state
- `_flashSaveIndicator(msg)` — updated signature to accept optional `msg`
  argument (default `'Saved'`) so the detect path can flash `'Detected'`

#### `frontend/static/index.html`
- Added `#sectionsDetectBtn` button in the sections header actions bar,
  after the existing Add button. Hidden by default; `sections.js` unhides
  it in `init()`.

#### `colab/mwtn_pipeline.py`
- Added `RUN_SECTION_DETECT = False` feature flag at top of file
- Added `detect_sections_allin1(stems_source_dir)` function — standalone
  allin1 wrapper with the same label mapping as the backend module
- Added `normalize_sections_simple(raw, duration)` — a self-contained
  normaliser that mirrors `backend/audio/sections.py` without requiring
  that module to be importable from the Colab environment
- Updated `build_output()` to accept `sections_result: list | None`, write
  `sections.json`, and set `has_sections` in the manifest
- Updated `main()` to run section detection when flag is on

---

## 3. Beat Grid Editor (Canvas Drag)

**What it does:** Upgrades the existing beat grid from DOM-tick rendering to
a fully canvas-based drag editor. Previous implementation created one DOM
element per beat tick, which became sluggish at 200+ beats. The new
implementation draws all ticks on a single `<canvas>` and uses pointer
coordinate hit-testing to drive all interaction.

**Edit mode interactions:**
- **Left-click empty space** → add a beat at that position
- **Left-drag an existing tick** → move it (pointer capture, smooth)
- **Right-click a tick** → delete it
- Changes auto-save to `PATCH /beats` with an 800 ms debounce; the Save
  button forces an immediate save

**Display mode (edit off):** Canvas is overlay-only with `pointer-events:none`,
so clicks pass through to the playhead scrub beneath it. Beat ticks and bar
numbers render the same as before.

---

### Files Changed

#### `frontend/static/js/beat-grid.js` *(REWRITTEN)*
The class retains its original public API (`new BeatGrid(...)`, `.init()`,
`.loadSong(songId)`, `.clear()`, `.toggleEditMode()`, `.tick(pos)`) so
`app.js` requires no changes beyond what was already there.

Internal changes:
- **Canvas management:** `_buildCanvas()` creates a single `<canvas>` appended
  to `#ruler-time`, observed by a `ResizeObserver` that triggers re-render on
  ruler width changes (e.g. panel resize, window resize)
- **Rendering:** `_render()` redraws the whole canvas on every state change.
  Beat ticks are coloured by type (bar = gold, beat = dim white, dragging =
  blue). Bar numbers are drawn as text above bar ticks. Edit mode adds a
  small grab-handle circle on each tick.
- **Hit-testing:** `_hitTest(clientX)` scans `this._tickRects` (populated
  during each render) and returns the index of the nearest beat within
  `_TICK_HIT` (8 px) half-width.
- **Pointer events:**
  - `_onPointerDown` — start drag (existing tick) or add beat (empty space)
  - `_onPointerMove` — move dragged beat; update cursor guide
  - `_onPointerUp` — commit drag, re-sort beats array, trigger debounced save
  - `_onContextMenu` — delete beat at right-click position
- **Save / Reset:**
  - `_debouncedSave()` — 800 ms debounce → `_save()`
  - `_save(userTriggered)` — `PATCH /beats`, updates `State.beats`, calls
    `studio._drawRulerBeats?.()` to sync the existing ruler ticks
  - `_reset()` — confirm dialog → `DELETE+GET /beats` → re-render
- **Toolbar state:** `_updateToolbar()` shows/hides `#beatGridToolbar` and
  enables/disables `#beatSaveBtn` based on `_beats.length` and `_dirty`

#### `frontend/static/index.html`
- Added `#beatGridToolbar` div (hidden by default) above the ruler, containing:
  - `#beatGridInfo` — live beat count chip (e.g. "128 beats")
  - `#beatEditToggleBtn` — toggles edit mode; gets `.active` class when on
  - `#beatResetBtn` — resets to auto-detected grid (with confirm dialog)
  - `#beatSaveBtn` — force-saves current edits; `disabled` when not dirty
  - `#beatSaveBadge` — transient "Saved" / "✓" / "Reset" confirmation chip

---

## New File

#### `frontend/static/css/features.css` *(NEW)*
Styles for all three features. Linked in `index.html` after `daw.css`.

Sections:
- `.beat-grid-toolbar` and children — toolbar layout, button variants,
  edit-active colour, save badge fade-in/out
- `.vocal-split-trigger` / `.vocal-split-btn` / `.vocal-split-status` —
  the trigger row in the mixer stem list
- `#sectionsDetectBtn` — overrides on the existing `.sections-add-btn-label`
  base class to give the detect button a distinct purple accent

---

## Updated File

#### `backend/requirements.txt`
- Restructured with comments explaining which packages are required vs optional
- Added opt-in notes for `audio-separator[cpu]` (vocal split) and `allin1`
  (section detection) with data-cost callouts
- No new packages are **installed by default** — all new dependencies are
  explicitly opt-in to avoid bloating the base install

---

## Data / Manifest Schema Additions

`manifest.json` gains two new optional boolean flags:

| Key | Type | Set when |
|---|---|---|
| `has_vocal_split` | `bool` | `lead_vocals.wav` + `backing_vocals.wav` exist |
| `has_sections` | `bool` | `sections.json` was written by auto-detection |

Both default to absent/falsy when the feature hasn't run, so existing
processed songs remain fully compatible.

`stems` list in manifest may now include `"lead_vocals"` and/or
`"backing_vocals"` after a vocal split.

---

## Mobile Data Advisory

| Action | Data cost | When to do it |
|---|---|---|
| First vocal split on Colab | ~200 MB (model download) | Wi-Fi only |
| First section detect on Colab | ~120 MB (model download) | Wi-Fi only |
| Subsequent runs (models cached) | ~0 MB extra | Any |
| Models cached to Drive | Re-downloads each Colab session unless `HF_HOME` or `~/.cache` is on Drive | |
| `audio-separator` package install | ~50 MB | Wi-Fi only |
| `allin1` package install | ~80 MB | Wi-Fi only |

All three features work on already-downloaded stems — no re-upload of audio needed.

---

## Upgrade Path for Existing Songs

Existing songs (already in `backend/data/`) work unchanged. To add the new
features to an existing song:

**Vocal split** — click "Split Lead / Backing Vocals" in the mixer (requires
`audio-separator` installed on the backend server or Colab).

**Section detection** — click "Auto-detect" in the Sections header (requires
`allin1` for labelled sections, or falls back to librosa heuristic with no
extra install).

**Beat grid editor** — available automatically for any song that already has
beat data (`has_beats: true` in manifest). Click "Edit beats" in the toolbar
above the ruler.
