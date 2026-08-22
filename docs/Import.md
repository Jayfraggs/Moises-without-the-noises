# Import

Overview
- Local import uploads a file to `POST /api/import` and runs Demucs separation as a background job.

Responsibilities
- Backend: `main.py` accepts upload and kicks off separation in a background thread (writes to `backend/data/<song_id>/`).
- Frontend: `ImportSong.jsx` provides UI and polls job status.

Operational notes
- Local CPU imports can take 15–40 minutes; prefer Colab for speed.