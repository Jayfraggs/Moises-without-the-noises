# Playback

Overview
- Describes playback behaviour, transport controls, and sync expectations.

Responsibilities
- Start/stop/seek controls via `TransportControls.jsx`.
- Maintain `isPlaying`, `currentTime`, `duration` in `App.jsx`.

Frontend components
- `TransportControls.jsx`, `SongInfoBar.jsx`, `NoteDisplay.jsx`.

Offline / Data cost
- Stem loading should be progressive and not blocked by metadata fetches.