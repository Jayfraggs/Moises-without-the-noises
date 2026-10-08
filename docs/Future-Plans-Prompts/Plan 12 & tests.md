### [PLAN-12] GPU/Colab Job System

**Scope:** Right now the Colab pipeline is a linear notebook — cells run top to bottom, one song at a time, with no job tracking, no retry logic, no status reporting back to the app, and no queue. Plan 12 replaces that with a proper job system: a job queue persisted to Google Drive, a Colab-side job runner that picks up queued jobs and processes them, status polling from the app, and a job history UI. Also covers the backend job broker endpoints and the frontend job status module.

---

### [P12-BE-01] Job Model + Persistence Layer

**Target Files:** `backend/jobs/models.py` *(new)*, `backend/jobs/__init__.py` *(new)*, `backend/jobs/store.py` *(new)*

**Context:** Jobs are persisted as JSON files in `backend/data/_jobs/`. Each job represents one song processing request — a single source audio file going through the full pipeline (separation → transcription → beat → key → notes → solfa → alignment → confidence → MIDI/MusicXML). The backend is the source of truth for job state. Colab reads and writes to the same job files via Google Drive sync (or direct Drive API calls from Colab).

**Objective:**
Define the job datamodel and a filesystem-backed job store.

**Technical Specifications:**

**`backend/jobs/models.py`:**
```python
from dataclasses import dataclass, field
from typing import Optional, Literal
from datetime import datetime

JobStatus = Literal[
    'queued',        # submitted, not yet picked up
    'downloading',   # Colab fetching the source audio
    'separating',    # Demucs running
    'transcribing',  # Whisper running
    'analysing',     # beat/key/notes/solfa/alignment
    'packaging',     # zipping and uploading to Drive
    'done',          # zip available, song_id resolvable
    'failed',        # terminal failure
    'cancelled'      # user cancelled
]

@dataclass
class JobStep:
    name: str
    status: Literal['pending', 'running', 'done', 'failed', 'skipped']
    started_at: Optional[str] = None    # ISO 8601
    finished_at: Optional[str] = None
    error: Optional[str] = None
    progress_pct: Optional[float] = None  # 0.0 – 100.0

@dataclass
class Job:
    job_id: str                    # UUID4
    song_title: str
    source_url: Optional[str]      # YouTube URL or Drive file ID
    source_filename: Optional[str] # for local upload jobs
    status: JobStatus
    created_at: str                # ISO 8601
    updated_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    song_id: Optional[str] = None  # set when done — links to backend/data/{song_id}/
    drive_zip_url: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 2
    steps: list[JobStep] = field(default_factory=list)
    colab_session_id: Optional[str] = None  # identifies which Colab session claimed it
    estimated_duration_s: Optional[float] = None
    priority: int = 0              # higher = processed first
```

**`backend/jobs/store.py`:**
```python
# Filesystem-backed job store
# Jobs live at backend/data/_jobs/{job_id}.json

def create_job(song_title, source_url=None, source_filename=None, priority=0) -> Job
def get_job(job_id: str) -> Optional[Job]
def update_job(job: Job) -> None          # atomic write
def list_jobs(status: Optional[JobStatus] = None) -> list[Job]
def claim_next_job(colab_session_id: str) -> Optional[Job]
    # Atomically sets status='downloading', stamps colab_session_id
    # Returns None if no queued jobs
    # Uses file locking (fcntl on Linux, msvcrt on Windows) to prevent double-claim
def cancel_job(job_id: str) -> bool
def delete_job(job_id: str) -> bool       # removes JSON file
def get_job_dir() -> Path                 # backend/data/_jobs/
```

**File locking for `claim_next_job`:**
- Use `filelock` library (`pip install filelock`) — cross-platform, pure Python.
- Lock file: `backend/data/_jobs/.lock`.
- Add `filelock` to `requirements.txt`.
- Lock is held for the minimum time needed (read queue → pick job → write claim → release).

**Execution Constraints:**
- All writes atomic (`.tmp` + rename).
- `list_jobs` sorts by `priority` desc, then `created_at` asc.
- `claim_next_job` must be safe to call from multiple concurrent Colab sessions.
- Full type hints throughout.

**Output Request:**
Return `backend/jobs/models.py`, `backend/jobs/__init__.py`, and `backend/jobs/store.py`. Include the `filelock` addition to `requirements.txt`.

---

### [P12-BE-02] Job API Routes

**Target Files:** `backend/main.py` *(add routes)*

**Objective:**
Add the full job management API surface.

**Technical Specifications:**

Routes:
```
POST   /api/jobs                        → create a new job
GET    /api/jobs                        → list all jobs (optional ?status= filter)
GET    /api/jobs/{job_id}               → get single job
PATCH  /api/jobs/{job_id}               → update job (Colab uses this to report progress)
DELETE /api/jobs/{job_id}               → cancel + delete
POST   /api/jobs/{job_id}/cancel        → cancel only (keeps history)
POST   /api/jobs/claim                  → Colab calls this to atomically claim next job
GET    /api/jobs/{job_id}/steps         → return just the steps array
PATCH  /api/jobs/{job_id}/steps/{name}  → update a specific step's status/progress
```

**`POST /api/jobs` request body:**
```json
{
  "song_title": "Fela Kuti — Zombie",
  "source_url": "https://www.youtube.com/watch?v=...",
  "priority": 0
}
```
- Generates `job_id` (UUID4), stamps `created_at`, sets `status='queued'`.
- Initialises `steps` list with all pipeline steps in order, all `status='pending'`.
- Returns full `Job` object.

**`PATCH /api/jobs/{job_id}` request body:**
```json
{
  "status": "separating",
  "started_at": "2026-10-06T14:00:00Z",
  "estimated_duration_s": 420
}
```
- Partial update — only fields present in body are changed.
- Stamps `updated_at` server-side.
- If `status` transitions to `'done'`: require `song_id` in body, validate `backend/data/{song_id}/manifest.json` exists.
- If `status` transitions to `'failed'`: require `error_message` in body.

**`POST /api/jobs/claim` request body:**
```json
{ "colab_session_id": "colab-abc123" }
```
- Calls `store.claim_next_job(colab_session_id)`.
- Returns claimed `Job` or `{ "job": null }` if queue empty.

**`PATCH /api/jobs/{job_id}/steps/{name}`:**
```json
{ "status": "running", "progress_pct": 45.0 }
```
- Updates the named step in `job.steps`. Step name must exist — 404 if not.

**General constraints for all routes:**
- All file I/O wrapped in `asyncio.to_thread`.
- Structured error JSON on all failures.
- No authentication for v1 — document this as a known gap.
- Maintain existing route structure in `main.py`.

**Output Request:**
Return only the new route blocks for `main.py`.

---

### [P12-BE-03] Stale Job Watchdog

**Target Files:** `backend/jobs/watchdog.py` *(new)*

**Context:** A Colab session can die mid-job (timeout, disconnect, crash). Without a watchdog, the job stays in `'separating'` forever. The watchdog runs as a background task in the FastAPI process and requeues stale jobs.

**Objective:**
Implement a background watchdog that detects and requeues stale jobs.

**Technical Specifications:**
```python
async def start_watchdog(check_interval_s: int = 120):
    """
    Runs forever as an asyncio task.
    Every check_interval_s seconds:
      - Load all jobs with status in ('downloading', 'separating', 'transcribing', 'analysing', 'packaging')
      - For each: if updated_at is older than STALE_THRESHOLD_S (default 600s) and retry_count < max_retries:
          - Increment retry_count
          - Reset status to 'queued'
          - Clear colab_session_id
          - Stamp updated_at
          - Log the requeue
      - If retry_count >= max_retries:
          - Set status to 'failed'
          - Set error_message to 'Job timed out after max retries'
          - Log the failure
    """
```

**Register in `backend/main.py`:**
```python
@app.on_event("startup")
async def startup():
    asyncio.create_task(start_watchdog())
```

**Execution Constraints:**
- Must not block the FastAPI event loop — use `asyncio.sleep` not `time.sleep`.
- All store writes inside `asyncio.to_thread`.
- Stale threshold and check interval configurable via env vars: `MWTN_STALE_THRESHOLD_S`, `MWTN_WATCHDOG_INTERVAL_S`.

**Output Request:**
Return only `backend/jobs/watchdog.py` and the startup hook addition to `main.py`.

---

### [P12-COLAB-01] Colab Job Runner

**Target Files:** `colab/job_runner.py` *(new)*, `colab/mwtn_notebook.ipynb` *(add cells)*

**Context:** This is the Colab-side counterpart to the backend job system. The job runner polls the backend API for queued jobs, claims one, runs the full pipeline for that job, reports step progress back via PATCH requests, and loops. It replaces the single-song linear notebook flow with a queue-aware worker loop.

**Objective:**
Implement a `JobRunner` class that turns a Colab session into a persistent job worker.

**Technical Specifications:**

```python
class JobRunner:
    def __init__(self, backend_url: str, session_id: str, song_dir: Path, drive_output_dir: str):
        # backend_url: e.g. "https://your-ngrok-url.ngrok.io" or localhost
        # session_id: unique ID for this Colab session (generated at startup)
        # song_dir: where to write processed output before zipping
        # drive_output_dir: Google Drive folder path for zip upload

    def run(self, max_jobs: int = None):
        """
        Main loop. Runs until max_jobs processed (or forever if None).
        Poll interval: 10s when idle, immediate when a job was just finished.
        """

    def _claim_job(self) -> Optional[dict]
    def _run_job(self, job: dict)
    def _step_start(self, job_id, step_name)
    def _step_progress(self, job_id, step_name, pct)
    def _step_done(self, job_id, step_name)
    def _step_fail(self, job_id, step_name, error)
    def _job_done(self, job_id, song_id, drive_url)
    def _job_fail(self, job_id, error_message)
    def _patch_job(self, job_id, payload)   # PATCH /api/jobs/{job_id}
    def _patch_step(self, job_id, step, payload)  # PATCH /api/jobs/{job_id}/steps/{step}
```

**`_run_job` pipeline sequence (matches existing `mwtn_pipeline.py` steps):**
```
1. downloading   → fetch source audio (yt-dlp for YouTube URLs, Drive download for Drive IDs)
2. separating    → Demucs htdemucs_6s
3. transcribing  → Whisper (vocals stem only)
4. analysing     → beat detection → key detection → note extraction → chord detection
                   → solfa resolution → lyrics alignment → confidence aggregation
                   → MIDI export → MusicXML export → click track generation
5. packaging     → zip song folder → upload to Google Drive → return Drive share URL
```

Each step calls `_step_start` at entry, `_step_progress` periodically where measurable, `_step_done` on success, `_step_fail` on exception (and re-raises to abort the job with `_job_fail`).

**Progress reporting for Demucs:**
- Demucs prints progress to stderr. Capture stderr in a thread, parse percentage lines, call `_step_progress` on each.
- Pattern: `r'(\d+)%'` on stderr lines.

**Error handling:**
- Each step wrapped in `try/except Exception as e`.
- On step failure: `_step_fail`, then `_job_fail`, then `continue` to next job in the loop — do not crash the runner.
- Log all errors to a local `runner.log` file in `song_dir`.

**Polling behaviour:**
- When queue is empty: log "Queue empty, sleeping 10s..." and `time.sleep(10)`.
- When a job finishes successfully: immediately poll again (no sleep).
- When a job fails: sleep 30s before re-polling (avoid hammering on a broken job).

**Notebook cells to add:**

Cell A — Setup:
```python
# Cell: Job Runner Setup
import uuid, subprocess, sys
SESSION_ID = f"colab-{uuid.uuid4().hex[:8]}"
BACKEND_URL = ""  # ← user fills in their ngrok URL or local tunnel
SONG_DIR = Path("/content/mwtn_output")
DRIVE_OUTPUT_DIR = "MWTN_Output"  # Google Drive folder name
SONG_DIR.mkdir(exist_ok=True)
print(f"Session ID: {SESSION_ID}")
print(f"Backend URL: {BACKEND_URL or 'NOT SET — fill in before running the next cell'}")
```

Cell B — Run:
```python
# Cell: Start Job Runner
from colab.job_runner import JobRunner
runner = JobRunner(BACKEND_URL, SESSION_ID, SONG_DIR, DRIVE_OUTPUT_DIR)
runner.run()   # blocks — runs until session times out or max_jobs reached
```

**Execution Constraints:**
- `BACKEND_URL` must be set by the user — the runner raises `ValueError` immediately if empty.
- `yt-dlp` must be installed in the Colab setup cell (`pip install yt-dlp -q`). Add to Colab setup, not to backend `requirements.txt`.
- All HTTP calls to the backend use `requests` with a 30s timeout.
- Colab session ID must be stable for the lifetime of the runner — generated once in Cell A.
- The runner loop must be interruptible with `KeyboardInterrupt` — catch it gracefully, log "Runner stopped by user", and call `_job_fail` on the currently running job if any.

**Output Request:**
Return `colab/job_runner.py` and the two new notebook cell JSON blocks.

---

### [P12-COLAB-02] ngrok / Tunnel Setup Cell

**Target Files:** `colab/mwtn_notebook.ipynb` *(add cell)*

**Context:** The Colab job runner needs to reach the FastAPI backend running on the user's local machine. This requires a tunnel. `ngrok` is the most reliable option; `pyngrok` wraps it for Python. This cell automates the tunnel setup and prints the URL to paste into Cell A.

**Objective:**
Add a Colab cell that establishes a tunnel to the local FastAPI backend and prints the public URL.

**Technical Specifications:**
```python
# Cell: Backend Tunnel Setup
# Run this BEFORE the Job Runner Setup cell.
# Your FastAPI backend must already be running locally (run.ps1).

!pip install pyngrok -q

from pyngrok import ngrok
import getpass

# User provides their ngrok auth token (free tier works)
NGROK_TOKEN = getpass.getpass("Paste your ngrok auth token: ")
ngrok.set_auth_token(NGROK_TOKEN)

tunnel = ngrok.connect(8000)
BACKEND_URL = tunnel.public_url
print(f"\n✓ Tunnel active: {BACKEND_URL}")
print(f"  Paste this into BACKEND_URL in the next cell.")
print(f"  Keep this cell alive — closing it kills the tunnel.")
```

**Mobile data note — include this as a comment in the cell:**
```python
# BANDWIDTH NOTE: ngrok itself uses minimal data (tunnel headers only).
# All audio processing happens in Colab — the only traffic through the
# tunnel is job JSON (tiny). Source audio download in Colab is the main
# cost — see _run_job step 1.
```

**Execution Constraints:**
- `pyngrok` install: ~200 KB. One-time per Colab session.
- ngrok free tier: 1 concurrent tunnel, 40 connections/min. Sufficient for solo use.
- Cell must print a clear warning if `BACKEND_URL` is still empty after setup.

**Output Request:**
Return the notebook cell JSON block.

---

### [P12-FE-01] Job Status API Client

**Target Files:** `frontend/js/api.js` *(add functions)*

**Objective:**
Add job management functions to `api.js`.

**Technical Specifications:**
```js
fetchJobs(status = null)              // GET /api/jobs?status=...
fetchJob(jobId)                       // GET /api/jobs/{jobId}
createJob(payload)                    // POST /api/jobs — returns created Job
cancelJob(jobId)                      // POST /api/jobs/{jobId}/cancel
deleteJob(jobId)                      // DELETE /api/jobs/{jobId}
pollJob(jobId, onUpdate, intervalMs)  // polls GET /api/jobs/{jobId} every intervalMs,
                                      // calls onUpdate(job) on each response,
                                      // returns a stop() function
```

**`pollJob` specification:**
```js
export function pollJob(jobId, onUpdate, intervalMs = 3000) {
  let active = true;
  let timeoutId;
  async function poll() {
    if (!active) return;
    const job = await fetchJob(jobId).catch(() => null);
    if (job) onUpdate(job);
    if (job && ['done', 'failed', 'cancelled'].includes(job.status)) {
      active = false;
      return;
    }
    timeoutId = setTimeout(poll, intervalMs);
  }
  poll();
  return { stop: () => { active = false; clearTimeout(timeoutId); } };
}
```

**Execution Constraints:**
- `pollJob` must auto-stop on terminal statuses — no infinite polling after `done`/`failed`/`cancelled`.
- Do not use `setInterval` — use `setTimeout` with self-scheduling (same reason as metronome).
- Do not alter existing exports.

**Output Request:**
Return only the new function blocks for `api.js`.

---

### [P12-FE-02] Job Queue UI Module

**Target Files:** `frontend/js/ui/jobQueue.js` *(new)*, `frontend/css/job-queue.css` *(new)*

**Context:** Vanilla HTML/CSS/JS. A sidebar panel (or collapsible drawer) showing the job queue — active job with live step progress, queued jobs, and job history. The user can submit new jobs (YouTube URL or local file), cancel running jobs, and see when a processed song is ready to load.

**Objective:**
Implement `initJobQueue(container, state)` and `updateJobQueue(state)`.

**Technical Specifications:**

**DOM structure:**
```html
<div class="job-queue-panel">
  <div class="job-queue-header">
    <h3>Processing Queue</h3>
    <span class="job-queue-badge" id="job-queue-count">0</span>
  </div>

  <div class="job-submit">
    <input type="text" id="job-url-input" placeholder="YouTube URL or leave blank for file upload" />
    <input type="text" id="job-title-input" placeholder="Song title" />
    <button id="job-submit-btn">Add to Queue</button>
  </div>

  <div class="job-list" id="job-list">
    <!-- job cards injected here -->
  </div>
</div>
```

**Job card:**
```html
<div class="job-card" data-job-id="..." data-status="separating">
  <div class="job-card-title">Fela Kuti — Zombie</div>
  <div class="job-card-status">
    <span class="job-status-badge job-status--separating">Separating</span>
    <span class="job-eta" id="eta-...">~6 min remaining</span>
  </div>
  <div class="job-steps">
    <!-- step indicators -->
    <div class="job-step job-step--done" title="Downloading">↓</div>
    <div class="job-step job-step--running" title="Separating (45%)">≋</div>
    <div class="job-step job-step--pending" title="Transcribing">T</div>
    <div class="job-step job-step--pending" title="Analysing">A</div>
    <div class="job-step job-step--pending" title="Packaging">📦</div>
  </div>
  <div class="job-card-actions">
    <button class="job-cancel-btn" data-job-id="...">Cancel</button>
  </div>
</div>
```

**Step indicators:**
- 5 fixed steps: `downloading`, `separating`, `transcribing`, `analysing`, `packaging`.
- States: `pending` (gray dot), `running` (pulsing accent), `done` (green), `failed` (red), `skipped` (dim).
- Running step shows `progress_pct` as a text label if available.

**ETA calculation:**
- Use `job.estimated_duration_s` from the backend if set.
- If not set, use heuristic: separating ≈ 4 min, transcribing ≈ 2 min, analysing ≈ 1 min, packaging ≈ 30s.
- Display as "~N min remaining" based on current step and elapsed time.

**Done state:**
- Card gets class `job-card--done`.
- Show a "Load Song" button that calls `store.set({ pendingSongId: job.song_id })` — `main.js` watches this and triggers song load.
- If `drive_zip_url` is present, also show "Open in Drive" link (plain `<a>` tag, `target="_blank"`).

**Polling:**
- On `initJobQueue`: fetch all jobs once.
- For each job with a non-terminal status: start `pollJob(jobId, onUpdate, 3000)`.
- Store the `stop()` functions and call them when the job reaches a terminal status.
- When a new job is created via the submit form: immediately start polling it.

**Submit form behaviour:**
- "Add to Queue" → validate `song_title` is non-empty → call `createJob({ song_title, source_url, priority: 0 })` → add card to list → start polling.
- On `createJob` error: inline error message below the submit form.
- No `alert()`.

**CSS (`job-queue.css`):**
```css
.job-queue-panel {
  width: 280px;
  background: var(--bg-surface);
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  height: 100vh;
  position: fixed;
  right: 0; top: 0;
  z-index: 100;
  transform: translateX(100%);
  transition: transform 0.25s ease;
}
.job-queue-panel.open {
  transform: translateX(0);
}
/* Status badge colours */
.job-status--queued      { background: var(--text-muted); }
.job-status--downloading { background: var(--stem-bass); }
.job-status--separating  { background: var(--accent); }
.job-status--transcribing{ background: var(--stem-vocals); }
.job-status--analysing   { background: var(--stem-guitar); }
.job-status--packaging   { background: var(--stem-piano); }
.job-status--done        { background: #22c55e; }
.job-status--failed      { background: #ef4444; }
.job-status--cancelled   { background: var(--text-muted); }

/* Running step pulse */
.job-step--running {
  animation: step-pulse 1s ease-in-out infinite;
}
@keyframes step-pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.4; }
}
```

**Trigger button (in app header):**
```html
<button id="job-queue-toggle">Queue <span id="job-active-count">0</span></button>
```
Toggles `.open` class on `.job-queue-panel`. Badge shows count of non-terminal jobs.

**Execution Constraints:**
- Panel is a fixed sidebar — does not push layout. Main content does not reflow when it opens.
- All poll `stop()` calls must be made when the panel is destroyed or the app unmounts — no zombie polls.
- "Load Song" triggers store update — does not directly call `api.fetchSongs()`. `main.js` watches `pendingSongId`.
- No `alert()` or `confirm()` anywhere.
- Zero external dependencies.

**Output Request:**
Return only `frontend/js/ui/jobQueue.js` and `frontend/css/job-queue.css`.

---

### [P12-FE-03] Wire Job Queue into main.js and index.html

**Target Files:** `frontend/js/main.js` *(modify)*, `frontend/index.html` *(modify)*

**Objective:**
Add the queue toggle button, the queue panel mount, and the `pendingSongId` store watcher.

**Technical Specifications:**

**`index.html` additions:**
```html
<!-- In <header>: -->
<button id="job-queue-toggle">
  Queue <span id="job-active-count">0</span>
</button>

<!-- Before </body>: -->
<div id="job-queue-mount"></div>
```

**`main.js` additions:**
```js
import { initJobQueue } from './ui/jobQueue.js';

// On app boot:
initJobQueue(document.getElementById('job-queue-mount'), store.get());

// Toggle button:
document.getElementById('job-queue-toggle')
  .addEventListener('click', () => {
    document.querySelector('.job-queue-panel').classList.toggle('open');
  });

// Watch for song ready from completed job:
store.subscribe((state) => {
  if (state.pendingSongId && state.pendingSongId !== state.activeSongId) {
    loadSong(state.pendingSongId);   // existing song-load function
    store.set({ pendingSongId: null });
  }

  // Update queue badge in header
  const activeCount = (state.jobs || [])
    .filter(j => !['done','failed','cancelled'].includes(j.status)).length;
  document.getElementById('job-active-count').textContent = activeCount;
});
```

**Execution Constraints:**
- `initJobQueue` called once on boot.
- `loadSong` must already be defined in `main.js` from earlier plans — do not redefine it.
- Store key `jobs` is maintained by `jobQueue.js` via `store.set({ jobs: [...] })` — `main.js` only reads it for the badge.

**Output Request:**
Return only the diff blocks for `main.js` and `index.html`.

---

### [P12-RUN-01] Run Script Updates

**Target Files:** `activate.ps1` *(modify)*, `run.ps1` *(modify)*

**Objective:**
Add `filelock` to the pip install check, update the startup banner for the job system, and add a note about ngrok.

**Technical Specifications:**

**`activate.ps1` addition:**
```powershell
# After pip install -r requirements.txt:
Write-Host "Checking filelock (job queue dependency)..." -ForegroundColor DarkCyan
python -c "import filelock" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: filelock not installed. Run: pip install filelock" -ForegroundColor Yellow
} else {
    Write-Host "  filelock OK" -ForegroundColor Green
}

# Check _jobs directory exists
$jobsDir = Join-Path $PSScriptRoot "backend\data\_jobs"
if (-not (Test-Path $jobsDir)) {
    New-Item -ItemType Directory -Path $jobsDir | Out-Null
    Write-Host "Created backend/data/_jobs/ directory." -ForegroundColor Green
}
```

**`run.ps1` addition (in startup banner after health check):**
```powershell
Write-Host "" 
Write-Host "Job Queue: POST to /api/jobs to queue a song for Colab processing." -ForegroundColor Cyan
Write-Host "Colab:     Open colab/mwtn_notebook.ipynb, run the tunnel cell," -ForegroundColor Cyan
Write-Host "           then run the job runner cell to start processing." -ForegroundColor Cyan
Write-Host "ngrok:     Free account at https://ngrok.com — auth token required in Colab." -ForegroundColor DarkCyan
Write-Host ""
```

**Execution Constraints:**
- Diff/addition blocks only.
- PowerShell 5.1+ compatible.
- `$PSScriptRoot` for all path resolution.

**Output Request:**
Return only the addition blocks for both scripts.

---

**Bandwidth summary for Plan 12:**

Item by item:

- `filelock` pip install: ~15 KB. One-time.
- `pyngrok` pip install in Colab: ~200 KB. One-time per Colab session.
- `yt-dlp` pip install in Colab: ~5 MB. One-time per Colab session. **Do this on WiFi.**
- Job JSON payloads through the ngrok tunnel: single-digit KB per poll. Negligible.
- Source audio download inside Colab (step 1 of `_run_job`): this is the real cost — a 5-minute YouTube video is ~5–8 MB as audio. **This download happens inside Colab, not on your device.** Zero local mobile data cost for source audio.
- The Drive zip download (after job completes): same as current — tens of MB. Already flagged in earlier plans. **Do on WiFi.**
- Frontend job queue UI: local API calls only. Zero external network.

**Concrete actions to defer to WiFi:**
1. First-time `yt-dlp` install in a fresh Colab session (~5 MB).
2. Downloading the processed zip from Drive after a job completes.
3. Everything else in Plan 12 is safe on mobile data.