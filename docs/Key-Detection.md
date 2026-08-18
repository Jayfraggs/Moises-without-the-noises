# Key Detection

Overview
- Musical key detection (Krumhansl–Schmuckler algorithm) run offline and exposed via `/api/songs/{song_id}/key`.

Responsibilities
- Backend computes and caches `key.json` on-demand.
- Frontend displays key info in `SongInfoBar.jsx`.