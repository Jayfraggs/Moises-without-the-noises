# Frontend

Overview
- React + Vite SPA. `App.jsx` owns global state: current song, transport, stems, and metadata.

Responsibilities
- Components are presentational and receive state/callbacks from `App.jsx`.
- Use `api.js` for all HTTP calls; do not call `fetch()` directly in components.

Pitch control (real-time + export)
-------------------------------
- `PitchControl.jsx` provides the UI: semitone slider (-12..+12), preset
	buttons, transposed key preview, and an "Export at this pitch" action.
- The component is purely presentational and emits `onSemitoneChange(semitones)`
	and `onExportAtPitch(semitones)`. It does not construct audio nodes.
- `AudioEngine.js` owns the audio graph. A shared mixer GainNode (`_mixGain`)
	collects per-stem gains; when pitch shifting is enabled the mix is routed
	through a `SoundTouch` AudioWorklet node before connecting to destination.
- `AudioEngine.setPitch(semitones)` is the public API used by `App.jsx` to
	enable/disable or update the pitch processor. The pitch parameter is a
	multiplicative ratio `2 ** (semitones / 12)` applied to the SoundTouch node.
- For export, `api.exportStemAtPitch(songId, stemName, semitones)` calls the
	backend `GET /api/songs/{songId}/stems/{stemName}/export?semitones=...` which
	returns a one-shot WAV (server-side pitch-shift via `librosa.effects.pitch_shift`).

Build / dependency notes
------------------------
- We rely on `soundtouch-audio-worklet` for the client-side AudioWorklet
	processor. The package's worklet `.js` file is copied into the built
	`public/libs/soundtouch` directory during the Vite build (see `vite.config.js`).
- Install in the frontend directory:

```bash
cd frontend
npm install
npm run build
```

Runtime notes
-------------
- The SoundTouch processor is shared across stems (applied to the mixed
	output) to avoid per-stem CPU multiplication.
- Known limitation: When `playbackRate !== 1` and a non-zero pitch shift is
	active, their effects combine. Decoupled time-stretch + pitch-shift requires
	a more advanced processing graph or a server-side solution.
Setup wizard
------------
- `SetupWizard.jsx` / `SetupWizard.css` replace the old `OnboardingWizard.jsx` modal.
- It is a full-screen takeover rendered by `App.jsx` when `useOnboarding()` returns
  `showOnboarding: true`. It is non-dismissible until the user reaches the final step.
- `OnboardingWizard.jsx` is retained in the repo but is no longer imported anywhere.
- The wizard has its own dedicated stylesheet (`SetupWizard.css`) with a visual identity
  distinct from the main app (recording-booth dark field, amber power-LED top border,
  scanline background texture). It consumes the same CSS token variables as the main app
  (`--bg`, `--surface`, `--amber`, `--teal`, etc.) but applies them independently.
- Steps: Welcome → System scan (auto-advances, uses `navigator.deviceMemory`,
  `navigator.hardwareConcurrency`, `navigator.connection`) → Path selection (Colab vs
  Local, with system-scored recommendation) → Step-by-step guide for the chosen path.
- Props: `onComplete` (function) — called on the final step. No other props. The
  `useOnboarding` hook in `hooks/useOnboarding.js` persists completion state to
  `localStorage` under `mwtn_setup_complete`.

LyricsPanel prop contract
-------------------------
- `LyricsPanel` expects: `words` (array of `{ word, start, end }` or `null`),
  `getCurrentTime` (function → number), `isPlaying` (boolean).
- `App.jsx` passes: `words={lyrics?.words ?? null}` and
  `getCurrentTime={() => engine.getCurrentTime()}`.
- Do NOT pass the full `lyrics` API response object — only the `words` array.

Speed control — single source of truth
---------------------------------------
- `SpeedControl.jsx` is the only component that controls playback rate.
- `TransportControls.jsx` no longer contains a speed control (removed duplicate).
- App's `playbackRate` state and `handleRateChange` callback are the authoritative values.
- `SpeedControl` receives `currentRate` and `onRateChange` as props.

CountInControl value prop
--------------------------
- `CountInControl` requires a `value` prop (number) to highlight the active beat option.
- App passes `value={countInBeats}`. Without it every option renders as inactive.

Missing CSS — now in App.css
-----------------------------
- `btn`, `btn-primary`, `btn-secondary`, `btn-toggle` — generic button variants.
- `transport__metronome-control`, `transport__metronome-volume` — metronome row.
- `export-panel` and sub-classes — export modal overlay and body.
- `controls-row` — unified container grouping SpeedControl, CountInControl, PitchControl.
- `pitch-control__*`, `speed-control__*` — full rule sets for both controls.
