# Vanilla frontend migration -DONE

The frontend is now served directly from `frontend/` by FastAPI. The existing
framework-free studio modules were promoted from `frontend/static/` so playback,
waveforms, imports, analysis, and exports remain available without npm or a
bundler. `frontend/js/main.js` is the native ES-module entry point and
`frontend/js/state/store.js` provides the observable state primitive for new UI
modules.

The migration is offline-safe: assets are local, API calls remain same-origin,
and the backend continues to own processing and file serving.

## Harmonic analysis panels

The recovered harmonic feature is implemented in `frontend/js/harmonic.js` and
rendered into `#harmonicPanel`. It includes detected key display, confidence,
key override controls, chord detection, chord timeline rendering, and active
chord highlighting during playback. Styling lives in `frontend/css/harmonic.css`.

Analysis panels can be resized with their top drag handles. Heights persist per
browser and double-clicking a handle restores the default size.
