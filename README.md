# Moises without the Noises

An open-source stem separation and musician practice tool powered by Meta's [Demucs](https://github.com/facebookresearch/demucs) and a suite of open-source audio analysis libraries.

Separate vocals, drums, bass, guitar, and piano from any song. Loop sections, detect chords, read lyrics, slow down without pitch shift. Built for musicians who want the power of Moises without the subscription.

---

## What's implemented

| Feature | Status | Powered by |
|---|---|---|
| 4-stem separation (vocals/drums/bass/other) | ✅ Local + Colab | Demucs `htdemucs` |
| 6-stem separation (+ guitar, piano) | ✅ Colab only | Demucs `htdemucs_6s` |
| Mute / Solo / Volume per stem | ✅ | Web Audio API |
| A-B Loop | ✅ | Web Audio API |
| Speed control (pitch shifts — known tradeoff) | ✅ | `playbackRate` |
| Note detection (bass, vocals) | ✅ | `librosa.pyin` |
| BPM detection | ✅ | `librosa.beat_track` |
| Key detection | ✅ | Krumhansl-Schmuckler |
| Lyric transcription | ✅ Colab only | OpenAI Whisper |
| Stem export (download WAV) | ✅ | FastAPI |
| Pitch-preserving speed change | 🔜 v2 | `soundtouchjs` |
| Chord detection | 🔜 v2 | `chord-extractor` |
| AI Voice Studio | ⚠️ Scoped out | Legal complexity |

---

## Architecture

```
mwtn/
├── colab/
│   └── mwtn_notebook.ipynb   # GPU processing: Demucs + Whisper + analysis
├── backend/                  # FastAPI — serves stems, notes, lyrics, BPM, key
│   ├── main.py
│   ├── separation.py         # Local Demucs wrapper (slow path)
│   ├── note_extraction.py    # librosa.pyin pitch tracker
│   ├── audio/
│   │   ├── bpm.py            # Beat & tempo detection
│   │   ├── key_detection.py  # Musical key estimation
│   │   └── pitch.py          # Server-side pitch shift / time stretch (export)
│   ├── data/                 # Song data lands here (gitignored)
│   └── requirements.txt
├── frontend/                 # React + Vite
│   └── src/
│       ├── AudioEngine.js    # Sample-accurate multi-stem playback engine
│       ├── App.jsx
│       ├── api.js
│       └── components/
├── electron/                 # Thin Electron shell (desktop wrapper)
└── docs/
```

**The Colab notebook is the primary processing path.** It runs Demucs and Whisper on a free GPU in ~1 minute per song, producing a zip you extract into `backend/data/`. The local import path (in-app button) also works but is slow on CPU-only machines (15–40 min per song).

---

## Getting started

### Prerequisites
- Python 3.10+
- Node.js 18+
- A Google account (for Colab)
- `ffmpeg` installed and on PATH

### 1. Process a song (Colab — recommended)

> **Mobile data:** The first Colab run downloads ~3.5 GB of model weights (Demucs + Whisper). Do this on Wi-Fi. Subsequent runs in the same session are free. Enable Drive caching in Cell 2 to persist weights across sessions.

1. Open `colab/mwtn_notebook.ipynb` in [Google Colab](https://colab.research.google.com)
2. Runtime → Change runtime type → **GPU (T4)**
3. Run all cells, upload your song when prompted
4. Download the output zip
5. Extract it so `<song_id>/manifest.json` is directly inside `backend/data/`

### 2. Run the backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Backend runs at `http://localhost:8000`.

### 3. Run the frontend (dev)

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`. Vite proxies `/api` to the backend automatically.

### 4. (Optional) Desktop app

```bash
cd electron
npm install
npm start
```

Opens an Electron window pointing at the running backend.

---

## Adding a song (local — slow path)

If you don't want to use Colab, click **"+ Import a song"** in the app. This runs Demucs locally via the backend. On a CPU-only machine, expect 15–40 minutes per song. You'll see a progress log while it runs.

> **Note:** Local import uses `htdemucs` (4 stems). The 6-stem model (`htdemucs_6s`) is too slow locally. Use the Colab notebook for guitar and piano stems.

---

## Data directory structure

After processing, each song lives in `backend/data/<song_id>/`:

```
backend/data/my_song/
├── manifest.json       # What the app reads first; describes available data
├── vocals.wav
├── drums.wav
├── bass.wav
├── other.wav
├── guitar.wav          # Only from Colab + htdemucs_6s
├── piano.wav           # Only from Colab + htdemucs_6s
├── notes_vocals.json   # [{start, end, note, midi}, ...]
├── notes_bass.json
├── lyrics.json         # Whisper output — only from Colab
├── beats.json          # {bpm, beats: [...], downbeats: [...]}
└── key.json            # {key, root, mode, confidence}
```

---

## API reference

| Endpoint | Description |
|---|---|
| `GET /api/songs` | List all songs |
| `GET /api/songs/{id}/manifest` | Song metadata |
| `GET /api/songs/{id}/stems/{stem}` | Stem WAV |
| `GET /api/songs/{id}/notes/{stem}` | Note timeline |
| `GET /api/songs/{id}/lyrics` | Whisper transcription |
| `GET /api/songs/{id}/beats` | BPM + beat timestamps |
| `GET /api/songs/{id}/key` | Detected musical key |
| `GET /api/songs/{id}/stems/{stem}/export?semitones=2&speed=0.8` | Pitch-shifted export |
| `POST /api/import` | Local import (slow) |
| `GET /api/import/{job_id}/status` | Import job status |

---

## Known limitations

**Speed control shifts pitch.** The playback engine uses Web Audio's `playbackRate`, which is sample-accurate and keeps stems in sync, but slows/speeds pitch proportionally. True pitch-preserving speed change requires a phase vocoder per stem. The `AudioEngine.js` structure is ready for this swap when we build it.

**Note detection is monophonic.** `librosa.pyin` assumes one note at a time. Works well on isolated bass and vocals. Guitar and piano are polyphonic and don't get note detection.

**6-stem separation is Colab-only.** `htdemucs_6s` takes ~3-10x realtime on CPU. On a 16 GB RAM / no-GPU machine, that's 15–40 min for a 4-min song. Colab's T4 GPU does it in ~60 seconds.

**Lyrics require Colab.** Whisper on CPU is too slow to include in the local import path for v1.

---

## Contributing

This project is open-source. Issues and PRs welcome.

When opening an issue, include:
- Whether you're using Colab or local import
- The Demucs model (`htdemucs` vs `htdemucs_6s`)
- Your OS and Python version

---

## License

MIT. Demucs is MIT. Whisper is MIT. librosa is ISC.
