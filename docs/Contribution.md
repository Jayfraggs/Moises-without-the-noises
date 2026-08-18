# Contribution Guide

Overview
- How to contribute, coding conventions, and important non-negotiable rules (see `AGENTS.md`).

Quick rules
- No CDN assets; no runtime external network calls from frontend.
- Use `api.js` for HTTP; keep audio node creation in `AudioEngine.js`.
- If changing `manifest.json` schema, update `backend/main.py` and `colab/mwtn_notebook.ipynb` together.

Data cost note
- Mention any task that downloads model weights or song stems and annotate the approximate data size.