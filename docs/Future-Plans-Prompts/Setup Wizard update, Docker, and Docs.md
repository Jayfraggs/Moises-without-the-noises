Three tasks here: **Setup Wizard update**, **Docker**, and **Docs**. Generating all three as agent prompt chains.

---

### [SETUP-WIZARD-01] Onboarding Wizard — Full Update for Plans 1–12

**Target Files:** `frontend/js/ui/onboardingWizard.js` *(rewrite)*, `frontend/css/onboarding.css` *(rewrite)*

**Context:** The existing onboarding wizard is a single modal flagging mobile data costs. Plans 1–12 have added: a full Song-to-Score pipeline, a job queue system, a Colab job runner, an ngrok tunnel requirement, a confidence review layer, a score UI, MIDI/MusicXML export, click track generation, and a frontend migration from React to vanilla HTML/CSS/JS. The wizard needs to cover all of this — clearly, simply, without assuming prior ML knowledge.

**Objective:**
Rewrite the onboarding wizard as a multi-step modal that walks a first-time user through everything they need to know before using the app. Non-dismissible until the final step is acknowledged.

**Technical Specifications:**

**Step structure (8 steps total):**

```
Step 1 — Welcome
Step 2 — What MWTN does (feature overview)
Step 3 — Two processing paths (Colab vs local)
Step 4 — Mobile data warning (prominent — existing content, enhanced)
Step 5 — Setting up Colab (ngrok + job runner)
Step 6 — Your first song (end-to-end walkthrough)
Step 7 — Score features (Plans 06–11 summary)
Step 8 — You're ready
```

---

**Step 1 — Welcome:**
```html
<h2>Welcome to MWTN</h2>
<p>MWTN separates any song into individual stems — vocals, bass, guitar, piano, drums — 
and turns them into sheet music, MIDI files, solfège, and karaoke tracks.</p>
<p>This wizard takes about 3 minutes. Read it — it will save you hours.</p>
```

---

**Step 2 — What MWTN does:**
```html
<h2>What you can do</h2>
<ul class="wizard-feature-list">
  <li>🎵 Separate any song into 6 stems (Demucs AI)</li>
  <li>🎼 Generate sheet music — staff notation, piano roll, solfège</li>
  <li>🎹 Export MIDI and MusicXML files (open in MuseScore, GarageBand, etc.)</li>
  <li>🎤 Transcribe lyrics with word-level timing (Whisper AI)</li>
  <li>🥁 Smart metronome synced to the actual song tempo</li>
  <li>🎸 Chord detection and key identification</li>
  <li>📤 Export stems, custom mixes, and click tracks</li>
  <li>🔍 Review and correct AI-detected notes and lyrics</li>
</ul>
```

---

**Step 3 — Two processing paths:**
```html
<h2>How processing works</h2>
<div class="wizard-paths">
  <div class="wizard-path wizard-path--recommended">
    <h3>☁ Google Colab (Recommended)</h3>
    <p>Heavy AI processing (stem separation, transcription) runs on Google's free GPUs — 
    not your device. Takes 5–15 minutes per song. Requires a Google account.</p>
    <p class="wizard-path-cost">Your device cost: minimal — only JSON files and stems 
    download to your machine.</p>
  </div>
  <div class="wizard-path">
    <h3>💻 Local Import</h3>
    <p>Runs entirely on your machine — no internet needed after setup. 
    Significantly slower on CPU (30–90 min per song). Only recommended if you 
    have a dedicated GPU locally.</p>
    <p class="wizard-path-cost">Your device cost: model weights download once (~900 MB 
    for Demucs + ~140 MB for Whisper small). Do this on WiFi.</p>
  </div>
</div>
```

---

**Step 4 — Mobile data warning (PROMINENT):**
```html
<h2>⚠ Mobile Data — Read This</h2>
<div class="wizard-data-warning">
  <p>MWTN is designed to be mobile-data-aware. Here is exactly what costs data 
  and what does not.</p>
  <table class="wizard-data-table">
    <thead><tr><th>Action</th><th>Data cost</th><th>Safe on mobile?</th></tr></thead>
    <tbody>
      <tr><td>Running the app (local)</td><td>0 MB</td><td>✓ Yes</td></tr>
      <tr><td>Colab job runner (polling)</td><td>&lt;1 MB/hour</td><td>✓ Yes</td></tr>
      <tr><td>ngrok tunnel traffic</td><td>&lt;1 MB/hour</td><td>✓ Yes</td></tr>
      <tr><td>Downloading stems from Drive zip</td><td>50–200 MB/song</td><td>✗ WiFi only</td></tr>
      <tr><td>Local import (CPU path)</td><td>0 MB after setup</td><td>✓ Yes</td></tr>
      <tr class="wizard-data-row--danger">
        <td>First Colab setup (yt-dlp install)</td><td>~5 MB</td><td>⚠ Avoid</td>
      </tr>
      <tr class="wizard-data-row--danger">
        <td>Local model weights (if using local path)</td><td>~1 GB total</td><td>✗ WiFi only</td>
      </tr>
    </tbody>
  </table>
  <p class="wizard-data-rule">Rule of thumb: <strong>Queue jobs freely on mobile. 
  Download zips on WiFi.</strong></p>
</div>
<label class="wizard-checkbox">
  <input type="checkbox" id="wizard-data-ack" />
  I understand the data implications
</label>
```
"Next" button on this step is disabled until checkbox is ticked.

---

**Step 5 — Colab setup:**
```html
<h2>Setting up Google Colab</h2>
<ol class="wizard-steps-list">
  <li>Open <code>colab/mwtn_notebook.ipynb</code> in Google Colab 
      (File → Open notebook → Upload).</li>
  <li>Run the <strong>Setup cell</strong> — installs dependencies.</li>
  <li>Run the <strong>Tunnel cell</strong> — enter your ngrok auth token 
      (free at <strong>ngrok.com</strong>). Copy the URL it prints.</li>
  <li>Run the <strong>Job Runner cell</strong> — paste the URL into 
      <code>BACKEND_URL</code>. The runner will now process any song you queue 
      from this app.</li>
</ol>
<p class="wizard-note">The backend (this app) must already be running before you 
start the tunnel. Run <code>run.ps1</code> first.</p>
<p class="wizard-note">ngrok free tier is sufficient. One tunnel, one Colab session 
at a time.</p>
```

---

**Step 6 — First song walkthrough:**
```html
<h2>Processing your first song</h2>
<ol class="wizard-steps-list">
  <li>Click the <strong>Queue</strong> button (top right).</li>
  <li>Enter a song title and a YouTube URL (or leave URL blank to upload a local file).</li>
  <li>Click <strong>Add to Queue</strong>. The job appears with status "Queued".</li>
  <li>Colab picks it up automatically. Watch the step indicators progress.</li>
  <li>When status shows <strong>Done</strong>, click <strong>Load Song</strong>.</li>
  <li>If a ⚠ Review badge appears, open the Review panel to correct any 
      low-confidence detections before exporting.</li>
</ol>
<p class="wizard-note">First song takes 10–20 minutes in Colab. 
Subsequent songs are queued and processed automatically while the runner stays open.</p>
```

---

**Step 7 — Score features:**
```html
<h2>Score features</h2>
<p>Once a song is processed, the Score panel (bottom of the app) gives you:</p>
<div class="wizard-score-features">
  <div class="wizard-score-item">
    <span class="wizard-score-icon">🎼</span>
    <div>
      <strong>Staff Notation</strong>
      <p>Standard music notation for vocals, bass, guitar, and piano stems.</p>
    </div>
  </div>
  <div class="wizard-score-item">
    <span class="wizard-score-icon">🟦</span>
    <div>
      <strong>Piano Roll</strong>
      <p>MIDI-style horizontal note display. Good for seeing all pitches at once.</p>
    </div>
  </div>
  <div class="wizard-score-item">
    <span class="wizard-score-icon">🎵</span>
    <div>
      <strong>Solfège (Do-Re-Mi)</strong>
      <p>Movable-do syllables synced to each note. Useful for ear training.</p>
    </div>
  </div>
  <div class="wizard-score-item">
    <span class="wizard-score-icon">📄</span>
    <div>
      <strong>MIDI + MusicXML Export</strong>
      <p>Download and open in MuseScore, GarageBand, Sibelius, or any DAW.</p>
    </div>
  </div>
</div>
```

---

**Step 8 — Ready:**
```html
<h2>You're ready</h2>
<p>MWTN is now set up. A few reminders:</p>
<ul class="wizard-reminders">
  <li>Keep <code>run.ps1</code> running while you use the app.</li>
  <li>Keep the Colab notebook open while processing jobs.</li>
  <li>Download zips on WiFi — stems are large files.</li>
  <li>Use the Review panel to correct AI errors before exporting scores.</li>
  <li>The Score panel only shows data after note extraction completes in Colab.</li>
</ul>
<button id="wizard-finish-btn" class="wizard-finish-btn">Start using MWTN</button>
```

---

**Wizard state management:**
```js
// localStorage key: 'mwtn_wizard_complete'
// On app boot in main.js:
if (!localStorage.getItem('mwtn_wizard_complete')) {
  showWizard();
}
// wizard-finish-btn click:
localStorage.setItem('mwtn_wizard_complete', '1');
hideWizard();
```

**Navigation controls (all steps except Step 8):**
```html
<div class="wizard-nav">
  <button id="wizard-prev" disabled>← Back</button>
  <div class="wizard-dots">
    <!-- one dot per step, filled = current -->
  </div>
  <button id="wizard-next">Next →</button>
</div>
```

**CSS (`onboarding.css`) key rules:**
```css
.wizard-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.88);
  z-index: 2000;
  display: flex; align-items: center; justify-content: center;
}
.wizard-modal {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  width: min(640px, 95vw);
  max-height: 85vh;
  overflow-y: auto;
  padding: 32px;
  display: flex; flex-direction: column; gap: 20px;
}
.wizard-data-warning {
  background: rgba(239,68,68,0.1);
  border: 1px solid #ef4444;
  border-radius: var(--radius);
  padding: 16px;
}
.wizard-data-row--danger td { color: #f87171; }
.wizard-data-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.wizard-data-table th, .wizard-data-table td {
  text-align: left; padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}
.wizard-path--recommended {
  border: 1px solid var(--accent);
  background: rgba(124,58,237,0.08);
}
.wizard-finish-btn {
  background: var(--accent); color: white;
  padding: 12px 32px; border-radius: var(--radius);
  font-size: 1rem; cursor: pointer; border: none;
  width: 100%;
}
.wizard-dots { display: flex; gap: 6px; }
.wizard-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--border);
}
.wizard-dot.active { background: var(--accent); }
```

**Execution Constraints:**
- Non-dismissible — no close button, no ESC key, no click-outside-to-close until Step 8 is completed.
- Step 4 "Next" must be disabled until checkbox is ticked — enforce in JS, not CSS only.
- Wizard must re-show if `localStorage` is cleared — handled by the boot check.
- Zero CDN references.
- Trap keyboard focus inside modal while open (same pattern as Review Panel — Plan 10).
- `wizard-finish-btn` is the only exit point — clicking it sets localStorage and hides the overlay.

**Output Request:**
Return the complete `frontend/js/ui/onboardingWizard.js` and `frontend/css/onboarding.css`.

---

### [DOCKER-01] Dockerfile — Backend

**Target Files:** `Dockerfile` *(new, repo root)*

**Context:** The backend is a FastAPI Python app. It serves the vanilla HTML/CSS/JS frontend as static files from `frontend/`. No Node, no npm, no build step required. Docker target is local development and open-source contributors who don't want to set up a Python venv manually. Production hardening (auth, rate limiting) is explicitly out of scope for v1 — document this.

**Objective:**
Write a production-quality `Dockerfile` for the MWTN backend + frontend.

**Technical Specifications:**

```dockerfile
# ---- Base ----
FROM python:3.11-slim AS base

WORKDIR /app

# System deps for librosa (soundfile needs libsndfile), numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# ---- Deps ----
FROM base AS deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- App ----
FROM deps AS app
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Create data directories
RUN mkdir -p backend/data/_jobs

# Expose FastAPI port
EXPOSE 8000

# Non-root user
RUN adduser --disabled-password --gecos '' mwtn
USER mwtn

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/songs')"

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Multi-stage rationale:** `base` → `deps` → `app` keeps the layer cache efficient — changing app code does not re-run pip install.

**Execution Constraints:**
- Do NOT include Demucs model weights in the image — they are Colab-only. Document this clearly in a comment.
- Do NOT include `electron/` — Docker target is web-only.
- Do NOT run as root in the final stage.
- `ffmpeg` is required by librosa for audio format conversion — must be in the image.
- `libsndfile1` is required by `soundfile` — must be in the image.

**Output Request:**
Return the complete `Dockerfile`.

---

### [DOCKER-02] docker-compose.yml

**Target Files:** `docker-compose.yml` *(new, repo root)*

**Context:** Compose orchestrates the single backend+frontend container, mounts the data volume (so processed songs survive container restarts), and maps the port.

**Objective:**
Write `docker-compose.yml` for local development use.

**Technical Specifications:**

```yaml
version: "3.9"

services:
  mwtn:
    build:
      context: .
      dockerfile: Dockerfile
      target: app
    ports:
      - "8000:8000"
    volumes:
      # Persist processed songs and job queue across restarts
      - mwtn_data:/app/backend/data
      # Mount frontend for live edits without rebuild
      # (remove in production to use baked-in static files)
      - ./frontend:/app/frontend:ro
    environment:
      - MWTN_STALE_THRESHOLD_S=600
      - MWTN_WATCHDOG_INTERVAL_S=120
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c",
             "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/songs')"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  mwtn_data:
    driver: local
```

**Comments to include in the file:**
```yaml
# MWTN — Moises Without The Noises
# Docker Compose for local development
#
# Usage:
#   docker compose up --build
#   Open http://localhost:8000
#
# Notes:
#   - Demucs and Whisper run in Google Colab, NOT in this container.
#   - This container serves the frontend and backend API only.
#   - Processed song data persists in the 'mwtn_data' Docker volume.
#   - For Colab integration: run the ngrok tunnel cell pointing to
#     http://localhost:8000 (or your machine's LAN IP if Colab needs it).
#
# Production:
#   Remove the frontend volume mount and tighten CORS in backend/main.py.
#   Add authentication before any public deployment.
```

**Execution Constraints:**
- Named volume for `backend/data` — not a bind mount — so data survives `docker compose down`.
- Frontend bind mount is read-only (`:ro`) — prevents accidental writes from inside the container.
- Env vars for watchdog thresholds — makes them configurable without rebuild.

**Output Request:**
Return the complete `docker-compose.yml`.

---

### [DOCKER-03] .dockerignore

**Target Files:** `.dockerignore` *(new, repo root)*

**Objective:**
Exclude everything that must not enter the Docker build context.

**Technical Specifications:**
```
# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/
*.egg-info/

# Node (legacy — no longer used but may exist in repo)
node_modules/
frontend/dist/
frontend/.vite/

# Electron (not needed in Docker)
electron/

# Colab (not needed in Docker)
colab/

# Data (mounted as volume — do not bake into image)
backend/data/

# Dev tooling
.git/
.github/
*.md
docs/
*.log
.env
.env.*

# OS
.DS_Store
Thumbs.db
```

**Output Request:**
Return the complete `.dockerignore`.

---

### [DOCKER-04] Docker Run Script Update

**Target Files:** `run.ps1` *(add Docker section)*

**Objective:**
Add an optional Docker launch path to `run.ps1` — if Docker is detected and `--docker` flag is passed, launch via `docker compose` instead of the local venv.

**Technical Specifications:**
```powershell
# At top of run.ps1, after param block:
param(
    [switch]$Docker
)

if ($Docker) {
    Write-Host "Starting MWTN via Docker Compose..." -ForegroundColor Cyan
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: Docker not found. Install Docker Desktop first." -ForegroundColor Red
        exit 1
    }
    docker compose up --build
    exit 0
}
# ... rest of existing script continues unchanged
```

**Execution Constraints:**
- `--docker` flag is opt-in — default behaviour unchanged.
- PowerShell 5.1+ compatible.
- Diff/addition only.

**Output Request:**
Return only the addition block.

---

### [DOCS-01] Full Documentation Suite

**Target Files:** `docs/` *(directory — multiple new files)*

**Objective:**
Write comprehensive documentation covering every architectural change and new feature introduced in Plans 1–12, the frontend migration, Docker, and the onboarding wizard. All docs in Markdown. No external links except where unavoidable (ngrok, Google Colab). Offline-readable.

---

#### `docs/README.md` — Documentation Index

```markdown
# MWTN Documentation

| Document | What it covers |
|---|---|
| [architecture.md](architecture.md) | Full system architecture (updated for Plans 1–12) |
| [data-contracts.md](data-contracts.md) | All data models and file formats |
| [api-reference.md](api-reference.md) | Complete REST API surface |
| [pipeline.md](pipeline.md) | End-to-end processing pipeline |
| [frontend.md](frontend.md) | Frontend architecture (vanilla HTML/CSS/JS) |
| [score-ui.md](score-ui.md) | Score viewer — staff, piano roll, solfège |
| [job-system.md](job-system.md) | Colab job queue and runner |
| [colab-guide.md](colab-guide.md) | Step-by-step Colab setup guide |
| [export.md](export.md) | MIDI, MusicXML, click track, stem export |
| [confidence-review.md](confidence-review.md) | Confidence scoring and human review |
| [docker.md](docker.md) | Docker setup and deployment |
| [contributing.md](contributing.md) | Contributor guide |
| [mobile-data.md](mobile-data.md) | Mobile data cost reference |
```

---

#### `docs/architecture.md` — Updated System Architecture

**Sections to include:**

1. **Repository layout** — updated tree reflecting all new directories:
   ```
   mwtn/
   ├── backend/
   │   ├── main.py
   │   ├── separation.py
   │   ├── note_extraction.py
   │   ├── audio/
   │   │   ├── bpm.py
   │   │   ├── pitch.py
   │   │   ├── key_detection.py
   │   │   ├── click_track.py          ← Plan 08
   │   │   └── waveform_scan.py
   │   ├── alignment/                  ← Plan 09
   │   │   └── lyrics_aligner.py
   │   ├── confidence/                 ← Plan 10
   │   │   ├── aggregator.py
   │   │   └── corrections.py
   │   ├── export/                     ← Plan 07
   │   │   ├── midi_exporter.py
   │   │   └── musicxml_exporter.py
   │   ├── jobs/                       ← Plan 12
   │   │   ├── models.py
   │   │   ├── store.py
   │   │   └── watchdog.py
   │   ├── models/
   │   │   ├── musical_event.py        ← Plan 01
   │   │   ├── alignment.py            ← Plan 09
   │   │   └── confidence.py           ← Plan 10
   │   └── solfa/                      ← Plan 06
   │       └── solfa_resolver.py
   ├── frontend/
   │   ├── index.html
   │   ├── css/
   │   └── js/
   │       ├── AudioEngine.js
   │       ├── api.js
   │       ├── main.js
   │       ├── metronome.js            ← Plan 08
   │       ├── score/                  ← Plan 11
   │       │   ├── renderer.js
   │       │   ├── layout.js
   │       │   ├── notation.js
   │       │   └── symbols.js
   │       ├── state/
   │       │   └── store.js
   │       └── ui/
   │           ├── transport.js
   │           ├── stems.js
   │           ├── solfa.js
   │           ├── noteDisplay.js
   │           ├── songSelector.js
   │           ├── importSong.js
   │           ├── exportPanel.js
   │           ├── alignedLyrics.js    ← Plan 09
   │           ├── reviewPanel.js      ← Plan 10
   │           ├── scorePanel.js       ← Plan 11
   │           ├── jobQueue.js         ← Plan 12
   │           ├── metronome.js        ← Plan 08
   │           └── onboardingWizard.js
   ├── colab/
   │   ├── mwtn_notebook.ipynb
   │   ├── mwtn_pipeline.py
   │   └── job_runner.py              ← Plan 12
   ├── electron/
   ├── docs/
   ├── Dockerfile                     ← Docker
   ├── docker-compose.yml
   └── .dockerignore
   ```

2. **Architectural decisions** — one section per key decision:
   - Canonical `MusicalEvent` model as single source of truth (Plan 01)
   - Manifest-first song discovery (unchanged from original)
   - Frontend migration from React/Vite to vanilla HTML/CSS/JS — rationale, tradeoffs, what was kept (`AudioEngine.js`, `api.js`)
   - Dual-canvas score rendering (Plan 11) — why overlay canvas for playhead
   - Job queue as filesystem JSON (Plan 12) — why not a database for v1
   - Colab-as-worker architecture — why heavy ML lives outside the API process
   - Confidence layer (Plan 10) — why it's a separate pass rather than inline thresholds

3. **Data flow diagram** — text-based ASCII diagram:
   ```
   [Source Audio]
        │
        ▼
   [Colab Job Runner] ──── PATCH ───▶ [FastAPI /api/jobs]
        │
        ├──▶ Demucs htdemucs_6s ──▶ stems/*.wav
        ├──▶ Whisper ──────────────▶ lyrics.json
        ├──▶ librosa beat ──────────▶ beats.json
        ├──▶ Key detection ─────────▶ key.json
        ├──▶ pYIN note extraction ──▶ notes_*.json
        ├──▶ Chord detection ────────▶ chords.json
        ├──▶ Solfa resolver ─────────▶ solfa_*.json
        ├──▶ Lyrics aligner ─────────▶ aligned_lyrics.json
        ├──▶ Confidence aggregator ──▶ confidence.json
        ├──▶ MIDI exporter ──────────▶ {song_id}.mid
        ├──▶ MusicXML exporter ──────▶ {song_id}.xml
        └──▶ Click track gen ────────▶ click_track.wav
                                           │
                              [Zip → Google Drive]
                                           │
                              [User downloads on WiFi]
                                           │
                              [FastAPI serves to frontend]
                                           │
                              [Score UI / Transport / Export]
   ```

---

#### `docs/data-contracts.md` — Data Models Reference

**Sections:**
- `MusicalEvent` dataclass — all fields, types, which plan added each field
- `AlignedWord` dataclass
- `ConfidenceScore` and `ConfidenceSummary`
- `Correction` dataclass
- `Job` and `JobStep` dataclasses
- File format reference: `manifest.json`, `beats.json`, `key.json`, `lyrics.json`, `notes_*.json`, `solfa_*.json`, `aligned_lyrics.json`, `confidence.json`, `corrections.json`, `{song_id}.mid`, `{song_id}.xml`, `click_track.wav`
- `_jobs/{job_id}.json` format

For each file: example JSON snippet, field descriptions, which plan produces it, which plans consume it.

---

#### `docs/api-reference.md` — Complete REST API

**Format per endpoint:**
```
### GET /api/songs/{song_id}/stems/{stem_name}/solfa
Added: Plan 06

Returns solfège syllables for each note in the stem.

**Parameters**
- song_id (path): Song identifier
- stem_name (path): One of vocals, bass, guitar, piano

**Response 200**
{ "song_id": "...", "stem": "vocals", "tonic": "C", ... }

**Response 404**
Notes or key file not yet generated.

**Caching**
Cached to solfa_{stem_name}.json. Regenerates if source files change.
```

Cover every route added across Plans 01–12 plus the original routes.

---

#### `docs/pipeline.md` — Processing Pipeline

**Sections:**
1. Overview — linear sequence from audio file to score
2. Colab path — step by step with time estimates and data costs per step
3. Local CPU path — same but with caveats
4. Step dependencies — which steps require which previous outputs (dependency graph in ASCII)
5. Idempotency — which steps are safe to re-run and which overwrite outputs
6. Error recovery — what happens when a step fails, how to resume

---

#### `docs/frontend.md` — Frontend Architecture

**Sections:**
1. Migration rationale — why React was dropped, what was preserved
2. Module system — how ES modules work without a bundler
3. `store.js` — the observable store pattern, how UI modules subscribe
4. `AudioEngine.js` — Web Audio graph, node routing, `getCurrentTime()`
5. `api.js` — all functions, error handling conventions
6. `main.js` — boot sequence, rAF loop, song-load handler
7. UI modules — one paragraph per module, what it renders, what store keys it reads
8. CSS architecture — design system variables, file organisation, naming conventions
9. Adding a new UI module — step-by-step guide for contributors

---

#### `docs/score-ui.md` — Score Viewer

**Sections:**
1. Three render modes — staff, piano roll, solfa — with screenshots described in text
2. `ScoreRenderer` architecture — dual canvas, layout engine, notation painter
3. `symbols.js` — how SMuFL paths were extracted, what's included
4. Zoom, scroll, and follow behaviour
5. Multi-stem display — how stacking works, opacity model
6. Performance notes — why overlay canvas, why culling matters, `devicePixelRatio` handling
7. Known limitations — approximate clef shape, no tuplets in v1, monophonic only

---

#### `docs/job-system.md` — Job Queue and Colab Runner

**Sections:**
1. Architecture overview — backend broker + Colab worker
2. Job lifecycle — state machine diagram (ASCII) covering all `JobStatus` values:
   ```
   queued → downloading → separating → transcribing → analysing → packaging → done
      ↑                                                                          
      └── (requeued by watchdog if stale) ────────────────────────────── failed
   ```
3. `JobStore` — filesystem layout, file locking, atomic writes
4. Watchdog — stale detection, retry logic, configuration via env vars
5. Colab job runner — `JobRunner` class, polling behaviour, error handling, `KeyboardInterrupt` handling
6. ngrok tunnel — why it's needed, free tier limits, setup steps
7. Multi-session support — can multiple Colab sessions process jobs in parallel? (Yes — `claim_next_job` is atomic.)
8. Security note — no auth in v1, do not expose backend publicly

---

#### `docs/colab-guide.md` — Step-by-Step Colab Guide

Written for a first-time Colab user. No assumed ML knowledge.

**Sections:**
1. Prerequisites — Google account, ngrok free account, MWTN backend running locally
2. Opening the notebook — upload vs Google Drive link
3. Runtime selection — GPU (T4 recommended), why it matters
4. Running each cell in order — what each cell does, what to expect
5. Getting your ngrok auth token — where to find it, how to paste it
6. Setting BACKEND_URL — common mistakes (trailing slash, http vs https)
7. What the job runner output looks like — example log output
8. Session timeouts — Colab free tier limits (~12 hrs), what happens to running jobs (watchdog requeues), how to restart
9. Troubleshooting — common errors and fixes:
   - "BACKEND_URL not set"
   - "Connection refused" (backend not running)
   - "ngrok tunnel expired"
   - "Job stuck in separating" (watchdog will requeue after 10 min)
   - "Out of GPU memory" (switch to smaller Whisper model)

---

#### `docs/export.md` — Export Reference

**Sections:**
1. Stem audio export — formats, quality, server-side mixing
2. MIDI export — how `MusicalEvent` maps to MIDI, multi-track layout, channel assignments, known limitations (velocity default, no expression)
3. MusicXML export — structure, how to open in MuseScore, known limitations (approximate rhythms, no dynamics)
4. Click track — how it's generated, downbeat vs beat tone frequencies, WAV spec
5. Custom mix — what it is, how fader levels are applied server-side
6. Export + corrections — how human review corrections (Plan 10) affect exported MIDI/MusicXML

---

#### `docs/confidence-review.md` — Confidence and Human Review

**Sections:**
1. Why AI transcription needs review — brief, honest explanation of pYIN and Whisper accuracy limits
2. Confidence scores — per-source thresholds, normalisation, weighted overall score
3. `review_required` trigger — 15% flagged threshold, rationale
4. The Review panel — how to use it, accept/reject/edit, "Accept All" workflow
5. Corrections file — where it lives, what it contains, how to reset it (delete `corrections.json`)
6. How corrections propagate — which exporters apply corrections, which don't yet
7. Known gap — corrections are not version-controlled in v1

---

#### `docs/docker.md` — Docker Setup

**Sections:**
1. What Docker gives you — reproducible environment, no venv setup
2. What Docker does NOT do — no Demucs/Whisper in container, no Electron, no GPU
3. Prerequisites — Docker Desktop install
4. Quick start — `docker compose up --build`, open `http://localhost:8000`
5. Volume persistence — where song data lives, how to back it up
6. Frontend development with Docker — the read-only bind mount, live edits
7. Environment variables — `MWTN_STALE_THRESHOLD_S`, `MWTN_WATCHDOG_INTERVAL_S`
8. Colab integration with Docker — ngrok pointing to `localhost:8000` works identically
9. Production notes — tighten CORS, add auth, remove frontend bind mount

---

#### `docs/mobile-data.md` — Mobile Data Cost Reference

A single authoritative table covering every action in the app with its data cost and a mobile-safe verdict. Compiled from the bandwidth notes across Plans 01–12. This becomes the canonical reference — all future plans should update this table.

| Action | One-time or recurring | Approx. cost | Mobile safe? | Notes |
|---|---|---|---|---|
| Run MWTN backend | Recurring | 0 MB | ✓ | Local only |
| Run frontend in browser | Recurring | 0 MB | ✓ | Served locally |
| Queue a job | Per job | < 1 KB | ✓ | JSON API call |
| Job status polling | Per session | < 1 MB/hr | ✓ | Tiny JSON |
| ngrok tunnel traffic | Per session | < 1 MB/hr | ✓ | Headers only |
| pyngrok Colab install | One-time/session | ~200 KB | ✓ | |
| filelock pip install | One-time | ~15 KB | ✓ | |
| mido pip install | One-time | ~50 KB | ✓ | |
| yt-dlp Colab install | One-time/session | ~5 MB | ⚠ Avoid | Do on WiFi |
| Source audio download (Colab) | Per song | 5–15 MB | ✓ | Happens in Colab, not local |
| Processed zip download from Drive | Per song | 50–200 MB | ✗ WiFi only | Stems are large |
| Bravura glyph extraction (dev) | One-time | ~2 MB | ⚠ Avoid | Dev step only |
| Local model weights (if CPU path) | One-time | ~1 GB | ✗ WiFi only | Demucs + Whisper |
| MIDI/MusicXML download | Per export | < 100 KB | ✓ | Text formats |
| Click track WAV download | Per song | 1–3 MB | ✓ | Generated locally |
| Score panel rendering | Recurring | 0 MB | ✓ | Canvas — no network |

---

#### `docs/contributing.md` — Contributor Guide

**Sections:**
1. Project philosophy — open source, offline-first, mobile-aware, zero CDN
2. Architecture principles — canonical model, manifest-first, no runtime ML in API process
3. Setting up for development — `activate.ps1`, then `run.ps1` (and Docker alternative)
4. Frontend conventions — no framework, ES modules, store pattern, CSS variables only
5. Backend conventions — async routes, `asyncio.to_thread` for I/O, atomic writes, structured error JSON
6. Adding a new analysis step — checklist: add to `MusicalEvent` model, add backend route, add Colab pipeline cell, add `api.js` function, add UI module, update `docs/data-contracts.md` and `docs/api-reference.md`
7. Agent prompt format — reference to `agents.md`, how to write tasks for AI coding agents
8. Bandwidth discipline — every PR touching network behaviour must update `docs/mobile-data.md`
9. Known gaps and v2 roadmap — pitch-preserved time stretch, polyphonic AMT, LRC export, full Electron packaging, corrections version control

---

**Execution Constraints for all docs:**
- All Markdown. No HTML in docs.
- No external links except: ngrok.com (setup only), Google Colab (setup only), MuseScore (export only), SMuFL/Bravura (symbols only).
- Code blocks for all file paths, JSON examples, and command snippets.
- Every doc must be accurate to the state of the codebase after Plans 1–12 and the Docker/wizard additions — no forward references to unimplemented features.
- `docs/mobile-data.md` is the authoritative data cost reference — no other doc should define costs independently.
- ASCII diagrams preferred over Mermaid (offline readable in any text editor).

**Output Request:**
Return each documentation file as a separately labelled Markdown code block. Produce all files in full — no placeholders, no "add content here" stubs.

---

**Final bandwidth note for this entire task:**

- Setup wizard: zero network cost — pure DOM/localStorage.
- Docker: `docker compose up --build` pulls `python:3.11-slim` (~150 MB) and installs pip packages (~500 MB total image). **Do this on WiFi — one time only.** Subsequent `docker compose up` uses the cached image.
- Documentation: zero network cost — local Markdown files.
- **The Docker build is the only WiFi-only action in this task.**