# Agent Logs

## 2026-09-24
### Fix torch Version Pin for Python 3.14 (TASK-002)
- Replaced `torch==2.4.1` with `torch==2.9.1+cpu` in `backend/requirements.txt` to ensure compatibility with Python 3.14 on CPU.
- Removed the version pin for `demucs` (was `demucs==4.0.1`) to use the latest release compatible with torch >= 2.0.

### Fix soundtouch-audio-worklet Build Error (TASK-003)
- Initially added `"soundtouch-audio-worklet": "^0.3.2"` to dependencies in `frontend/package.json`.
- Encountered a 404 error during `npm install` because the package is not on the registry.
- Reverted the addition in `frontend/package.json` (removed Part A).
- Implemented the fallback (Part B): Added `build.rollupOptions.external` array containing `'soundtouch-audio-worklet'` to `frontend/vite.config.js` so that the build passes and the pitch-shifting will silently no-op at runtime.

### Fix activate.ps1 Backend Dependency Issues
- Added `setuptools` to `backend/requirements.txt` to fix a `ModuleNotFoundError: No module named 'pkg_resources'` error that occurs when `pip` attempts to build the `openai-whisper` wheel under Python 3.14 environments.

### Comment Out Local-Only ML Dependencies (TASK-004)
- Commented out `torch`, `demucs`, `openai-whisper`, `ffmpeg-python` and `--extra-index-url` in `backend/requirements.txt` since they are only required for local ML inference.
- Left `fastapi`, `uvicorn`, `python-multipart`, `librosa`, `soundfile`, and `numpy` uncommented as they are used at runtime regardless of the separation path.

### Rebuild OnboardingWizard with System-Spec Detection (TASK-005)
- Rewrote `frontend/src/components/OnboardingWizard.jsx` into a 4-step wizard.
- Step 2 now uses `navigator` APIs to detect RAM, CPU threads, platform, and network connection type.
- Step 3 scores the system for local Demucs usage and highlights the recommended setup path (Colab vs Docker).
- Step 4 implements paginated setup instructions for the chosen path (6 sub-steps for Colab, 4 for Docker).
- Maintained the existing `onComplete` prop interface and inline CSS strategy as requested.
