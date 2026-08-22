# API

Overview
- High-level API surface backed by `backend/main.py`. All endpoints are `/api/*`.

Endpoints (summary)
- `GET /api/songs` — list manifests
- `GET /api/songs/{song_id}/manifest` — manifest
- `GET /api/songs/{song_id}/stems/{stem_name}` — stem WAV
- `GET /api/songs/{song_id}/lyrics` — lyrics.json
- `GET /api/songs/{song_id}/beats` — beats.json
- `GET /api/songs/{song_id}/key` — key.json
- `POST /api/import` — upload and run separation

Notes
- CORS is open for local dev/Electron; production deployments should tighten origins.