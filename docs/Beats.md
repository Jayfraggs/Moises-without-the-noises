# Beats

Overview
- Beat detection (BPM + timestamps) computed on-demand with `librosa` and cached as `beats.json`.

Responsibilities
- Backend exposes `/api/songs/{song_id}/beats` and caches computed results.
- Frontend uses beat timestamps for timeline markers and practice features.