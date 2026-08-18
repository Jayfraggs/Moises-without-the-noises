# Frontend

Overview
- React + Vite SPA. `App.jsx` owns global state: current song, transport, stems, and metadata.

Responsibilities
- Components are presentational and receive state/callbacks from `App.jsx`.
- Use `api.js` for all HTTP calls; do not call `fetch()` directly in components.