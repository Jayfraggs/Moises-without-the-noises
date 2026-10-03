# mwtn — Setup Guide

**Moises without the Noises** — open-source offline-first stem practice app.

---

## What mwtn needs to run

| Component | Required | Notes |
|-----------|----------|-------|
| Python 3.10+ | ✅ Always | Backend API |
| ffmpeg | ✅ Always | Audio export, mixdown |
| librosa, soundfile | ✅ Always | BPM + key detection (installed via pip) |
| Google Colab (free) | ✅ Recommended | Runs Demucs + Whisper on GPU |
| torch + demucs | Optional | Only for the slow local-import path |
| Node.js + npm | Optional | Only for the Electron desktop wrapper |
| Docker | Optional | Self-contained deployment |

---

## Path A — Colab (recommended for most users)

Songs are processed on Google's free GPU (~2 min/song). Your machine only runs the API and UI.

### 1. Install prerequisites

**Windows:**
```powershell
# Install Python 3.10+ from https://python.org (tick "Add to PATH")
# Install ffmpeg from https://ffmpeg.org/download.html
# Add ffmpeg/bin to your PATH

# Then in the project folder:
.\activate.ps1
```

**macOS / Linux:**
```bash
# macOS
brew install python@3.11 ffmpeg

# Ubuntu/Debian
sudo apt install python3.11 python3.11-venv ffmpeg

# Then in the project folder:
./activate.sh
```

Both scripts:
- Create/repair a Python venv
- Install all backend deps (`fastapi`, `librosa`, `soundfile`, etc.)
- Optionally install Electron
- Verify ffmpeg is on PATH
- Print next steps

### 2. Start the app

```powershell
# Windows
.\run.ps1

# macOS / Linux
./run.sh
```

The script starts FastAPI on `http://127.0.0.1:8000`, polls until it's up, then opens the app in Electron or your browser.

### 3. Process a song with Colab

1. Open `colab/mwtn_notebook.ipynb` in [Google Colab](https://colab.research.google.com)
2. **Runtime → Change runtime type → T4 GPU** (free tier)
3. In Cell 3, set `DRIVE_FILE_PATH` to your song's path in Google Drive
4. **Run all cells** (~2 min on GPU)
5. The output ZIP lands in your Google Drive at `My Drive/mwtn-outputs/`
6. Download the ZIP and drag it onto the mwtn window — done

> **⚠ Mobile data:** First Colab run downloads ~3.5 GB of model weights (Demucs + Whisper). Do this on Wi-Fi. Subsequent runs in the same session cost nothing extra.

### 4. Importing the ZIP

Three ways:
- **Drag and drop** the ZIP onto the mwtn browser window
- **Import button** (top-right) → browse to the ZIP
- **Settings → Scan Drive** → point at your Drive folder, click Scan

---

## Path B — Local import (no Colab)

Everything runs on your machine. Expect **10–40 minutes per song on CPU**.

### Extra prerequisites

```bash
# Uncomment these lines in backend/requirements.txt:
#   --extra-index-url https://download.pytorch.org/whl/cpu
#   torch==2.3.1+cpu
#   demucs==4.0.1

# Then re-run setup:
.\activate.ps1   # Windows
./activate.sh    # macOS/Linux
```

> **⚠ Wi-Fi required:** First local separation downloads ~2.3 GB of Demucs model weights.

### Use it

Click **Import** in the mwtn window and drop an audio file (mp3, wav, flac, m4a, ogg). The backend runs Demucs locally as a background job — you can watch progress in the job panel.

---

## Path C — Docker

No Python install needed on your machine. Requires [Docker Desktop](https://docker.com).

```bash
# Build and run
docker compose up

# Or with a custom data directory
MWTN_DATA=/path/to/your/stems docker compose up

# Background
docker compose up -d

# Stop
docker compose down
```

The app is at `http://localhost:8000`.

To import a song, copy the Colab output ZIP into `./backend/data/` and extract it there:
```
backend/data/
  <song_id>/
    manifest.json
    vocals.wav
    drums.wav
    ...
```
The app picks it up automatically — no restart.

### Docker + local separation

The Docker image does **not** include torch/demucs by default (they add 4+ GB). To enable local import in Docker, create a `Dockerfile.local`:

```dockerfile
FROM mwtn:latest
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    torch==2.3.1+cpu demucs==4.0.1
```

Then `docker build -f Dockerfile.local -t mwtn-local .`

---

## In-app Setup Wizard

When you open mwtn for the first time (or navigate to `/setup`), a setup wizard walks you through:

1. **Choose path** — Colab (recommended) or local
2. **Configure** — Google Drive path and output folder name, or local model selection
3. **Verify** — live checks for backend, ffmpeg, librosa, demucs, and Drive folder
4. **First song** — step-by-step guide for your chosen path

The wizard saves your settings to `backend/mwtn_config.json`. They persist across restarts and pre-fill the Settings dialog.

---

## Directory structure after setup

```
mwtn/
├── backend/
│   ├── main.py             API (FastAPI)
│   ├── audio/              BPM, key, waveform, sections, click track
│   ├── data/               Song data (one folder per song_id)
│   │   └── <song_id>/
│   │       ├── manifest.json
│   │       ├── vocals.wav
│   │       ├── drums.wav
│   │       ├── beats.json
│   │       ├── key.json
│   │       └── peaks.json
│   └── mwtn_config.json    Saved wizard settings
├── frontend/
│   └── static/             Vanilla JS/HTML/CSS — no build step
│       ├── index.html
│       ├── setup.html      Setup wizard
│       ├── css/
│       └── js/
├── colab/
│   └── mwtn_notebook.ipynb Colab GPU pipeline
├── electron/               Desktop wrapper (optional)
├── activate.ps1            Windows setup
├── activate.sh             macOS/Linux setup
├── run.ps1                 Windows start
├── run.sh                  macOS/Linux start
├── Dockerfile
├── docker-compose.yml
└── run_tests.py            Unified test runner
```

---

## Troubleshooting

### Backend starts but UI shows no songs
- Check `backend/data/` — each song needs a `manifest.json` inside its folder
- Try: `GET http://127.0.0.1:8000/api/songs` in your browser

### "ffmpeg not found" on export
- Windows: download from [ffmpeg.org](https://ffmpeg.org/download.html), extract, add `bin/` folder to PATH, restart PowerShell
- macOS: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

### venv Activate.ps1 missing (Windows)
Run `.\activate.ps1` — it detects and rebuilds the broken venv automatically.

### Python version mismatch
mwtn requires Python 3.10+. Check with `python --version`. On Windows, if multiple Pythons are installed, you may need `py -3.11 -m venv venv` explicitly.

### Colab disconnects mid-run
Re-run from Cell 3. The notebook checks for existing output and skips completed steps.

### Import ZIP fails with "422 Unprocessable"
The ZIP must contain at least one stem WAV and a `manifest.json`. Run the full Colab notebook (not just the separation cell).
