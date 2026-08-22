# Notes

Overview
- Precomputed note timelines for supported stems (e.g., bass, vocals) used by `NoteDisplay.jsx`.

Responsibilities
- Note extraction runs in Colab or as part of the import pipeline; results are stored as `notes_<stem>.json`.
- Frontend reads notes from the manifest-driven files and syncs display with `requestAnimationFrame`.

Constraints
- Monophonic single-note strings only (e.g., "A2"). No real-time FFT-based detection.