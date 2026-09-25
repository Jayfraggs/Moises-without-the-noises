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
