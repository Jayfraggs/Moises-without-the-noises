# Lyrics

Overview
- Word-level timestamps produced by Whisper and stored as `lyrics.json` per song.

Responsibilities
- Backend serves `/api/songs/{song_id}/lyrics` if available.
- Frontend `LyricsPanel.jsx` highlights individual words during playback.

Offline notes
- Missing `lyrics.json` is not an error — UI shows a non-crashing fallback.