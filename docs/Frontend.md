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