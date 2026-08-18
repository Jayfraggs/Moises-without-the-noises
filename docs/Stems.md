# Stems

Overview
- Stem management (load, mute, solo, gain) and file layout expectations.

Responsibilities
- Backend: serve WAVs at `/api/songs/{song_id}/stems/{stem_name}`.
- Frontend: `AudioEngine.js` loads buffers and exposes controls to `StemControls.jsx`.

Data format
- Files named `<stem>.wav` inside `backend/data/<song_id>/` and listed in `manifest.json`.

Data cost
- Stems are large (tens of MB each). Avoid automatic downloads on mobile.