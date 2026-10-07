### [PAPERMILL-01] Colab Automation via Papermill

**Context:** The "Colab CLI" as a concept doesn't map cleanly to automating a *hosted* Colab runtime — Google's Colab API doesn't expose a "run notebook" endpoint for free tier users. What does work: **Papermill**, which executes `.ipynb` notebooks as scripts, either locally or against a Jupyter kernel. For MWTN's architecture, the practical automation path is: Papermill runs the notebook *locally* (CPU path for lightweight pipeline steps) or triggers a pre-configured kernel on a remote Jupyter server (if the user self-hosts one). For Colab specifically, the closest automation is using the **Google Colab REST API** (v1, available to Workspace users) or, more practically, **keeping the job runner cell open and letting it poll** — which is already how Plan 12 works.

**What we're actually adding:** Papermill as a local execution path for the notebook, plus a backend route that triggers it, so the user can automate processing without manually opening the notebook browser.

---

### [PAPERMILL-BE-01] Papermill Backend Integration

**Target Files:** `backend/jobs/papermill_runner.py` *(new)*, `backend/main.py` *(add route)*

**Objective:**
Add a backend service that can trigger the Colab notebook locally via Papermill when a job is queued and the `proc_path` is `local`.

**Technical Specifications:**

```python
# backend/jobs/papermill_runner.py

import asyncio
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

NOTEBOOK_PATH = Path("colab/mwtn_notebook.ipynb")
OUTPUT_DIR = Path("colab/output")

async def run_notebook_papermill(
    job_id: str,
    song_title: str,
    source_path: Optional[str] = None,
    source_url: Optional[str] = None,
    parameters: dict = None,
) -> subprocess.CompletedProcess:
    """
    Executes mwtn_notebook.ipynb via papermill as a subprocess.
    Parameters are injected into the notebook's parameter cell.
    Non-blocking — called via asyncio.to_thread.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    output_path = OUTPUT_DIR / f"run_{job_id}_{timestamp}.ipynb"

    params = {
        "JOB_ID": job_id,
        "SONG_TITLE": song_title,
        "SOURCE_PATH": source_path or "",
        "SOURCE_URL": source_url or "",
        "BACKEND_URL": "http://localhost:8000",
        **(parameters or {}),
    }

    cmd = [
        sys.executable, "-m", "papermill",
        str(NOTEBOOK_PATH),
        str(output_path),
        *[arg for k, v in params.items() for arg in ["-p", k, str(v)]],
        "--log-output",
        "--no-progress-bar",
    ]

    result = await asyncio.to_thread(
        subprocess.run,
        cmd,
        capture_output=True,
        text=True,
        timeout=7200,  # 2 hour hard limit
    )
    return result, output_path
```

**New route `POST /api/jobs/{job_id}/run-local`:**
- Loads the job, validates `status == 'queued'`.
- Calls `run_notebook_papermill` as a background task (`asyncio.create_task` — non-blocking).
- Returns immediately: `{ "status": "started", "job_id": "...", "runner": "papermill" }`.
- On completion, the notebook updates the job via the existing PATCH routes — same flow as the Colab runner.
- HTTP 409 if job is not in `queued` status.
- HTTP 503 if `papermill` is not installed (check via `importlib.util.find_spec('papermill')`).

**Add to `requirements.txt`:**
```
papermill>=2.5.0
```

**Execution Constraints:**
- `run_notebook_papermill` must not block the FastAPI event loop — always `asyncio.to_thread` or `create_task`.
- Timeout: 2 hours hard limit via `subprocess.run(timeout=7200)`. On timeout: update job to `failed`, `error_message = "Local notebook run timed out after 2 hours"`.
- Output notebook saved to `colab/output/` — useful for debugging failed runs.
- Do not run if another Papermill process is already running for the same `job_id` — check `job.colab_session_id == 'papermill-local'` as a lock signal.

**Output Request:**
Return `backend/jobs/papermill_runner.py`, the new route block for `main.py`, and the `papermill` addition to `requirements.txt`.

---

### [PAPERMILL-COLAB-01] Notebook Parameterisation Cell

**Target Files:** `colab/mwtn_notebook.ipynb` *(add cell)*

**Context:** Papermill requires the notebook to have a cell tagged `parameters` — this is where injected values land. The cell must exist and declare all parameters with defaults so the notebook remains runnable manually in Colab without Papermill.

**Objective:**
Add a parameters cell at the top of the notebook (after setup, before processing).

**Technical Specifications:**

```python
# Parameters cell — tag this cell with the 'parameters' tag in Colab
# (View → Cell toolbar → Tags → add 'parameters')
# Papermill will inject values here when running non-interactively.

JOB_ID       = ""           # Set by Papermill or manually
SONG_TITLE   = "My Song"    # Display name
SOURCE_PATH  = ""           # Local file path (mutually exclusive with SOURCE_URL)
SOURCE_URL   = ""           # YouTube URL (mutually exclusive with SOURCE_PATH)
BACKEND_URL  = ""           # e.g. http://your-ngrok-url.ngrok.io
                            # Leave empty for manual Colab runs (job updates skipped)
```

**Guard in pipeline cells:**
```python
# At the top of each pipeline cell that reports to the backend:
def report_step(step_name, status, progress=None, error=None):
    if not BACKEND_URL or not JOB_ID:
        print(f"[{step_name}] {status} (no backend reporting — manual mode)")
        return
    # ... existing PATCH logic
```

**Execution Constraints:**
- Cell must be the first code cell after the setup/install cell.
- All parameters must have sensible defaults — notebook must run end-to-end without Papermill if defaults are used.
- The `parameters` tag must be documented in a comment inside the cell — Colab's cell tag UI is not obvious to new users.

**Output Request:**
Return the notebook cell JSON block.

---

### [PAPERMILL-SETUP-01] Activate Script + Run Script + Docs Updates

**Target Files:** `activate.ps1` *(modify)*, `run.ps1` *(modify)*, `docs/colab-guide.md` *(modify)*

**`activate.ps1` addition:**
```powershell
# Check papermill
python -c "import papermill" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing papermill..." -ForegroundColor DarkCyan
    pip install papermill
} else {
    Write-Host "  papermill OK" -ForegroundColor Green
}

# Create colab/output directory for notebook run artifacts
$colabOutput = Join-Path $PSScriptRoot "colab\output"
if (-not (Test-Path $colabOutput)) {
    New-Item -ItemType Directory -Path $colabOutput | Out-Null
    Write-Host "Created colab/output/ directory." -ForegroundColor Green
}
```

**`run.ps1` addition (in startup banner):**
```powershell
Write-Host "Papermill: POST /api/jobs/{id}/run-local to execute notebook locally." -ForegroundColor Cyan
Write-Host "           Output notebooks saved to colab/output/" -ForegroundColor DarkCyan
```

**`docs/colab-guide.md` new section — Papermill Automation:**
```markdown
## Automating the Notebook with Papermill

Papermill lets you run the MWTN notebook as a script — no browser required.
This is the recommended approach for local CPU processing (no Colab GPU).

### When to use Papermill vs Colab

| Scenario | Use |
|---|---|
| Fast GPU processing | Colab (manual or job runner) |
| Local processing, no browser | Papermill |
| CI/CD or scripted testing | Papermill |
| First-time setup or debugging | Colab (manual — easier to see output) |

### How it works

1. A job is queued via the app or `POST /api/jobs`.
2. The extract panel (Advanced tab) or `POST /api/jobs/{id}/run-local` 
   triggers Papermill.
3. Papermill executes `colab/mwtn_notebook.ipynb` locally, 
   injecting the job parameters into the parameters cell.
4. The notebook reports progress back to the backend via the same 
   PATCH routes the Colab runner uses.
5. Output notebook saved to `colab/output/run_{job_id}_{timestamp}.ipynb` 
   for debugging.

### Prerequisites

Papermill is installed automatically by `activate.ps1`.
Manual install: `pip install papermill`

### Parameters cell

The notebook's parameters cell (tagged `parameters`) accepts:

| Parameter | Default | Description |
|---|---|---|
| `JOB_ID` | `""` | Job ID from the queue |
| `SONG_TITLE` | `"My Song"` | Display name |
| `SOURCE_PATH` | `""` | Local audio file path |
| `SOURCE_URL` | `""` | YouTube URL |
| `BACKEND_URL` | `""` | Your backend URL (localhost or ngrok) |

### Limitations

- No GPU — Demucs and Whisper run on CPU. Expect 30–90 min per song.
- Papermill runs the notebook sequentially — one song at a time.
- For GPU speed, use the Colab job runner (Plan 12) instead.
- YouTube download (`yt-dlp`) must be installed locally if using `SOURCE_URL`.
```

**Output Request:**
Return the addition blocks for `activate.ps1`, `run.ps1`, and the new section for `docs/colab-guide.md`.

---

**Summary of decisions made:**

| Question | Decision | Confidence |
|---|---|---|
| MuseScore integration | File-based only (MusicXML download + manual open). No plugin API in v1. | High |
| Colab CLI | Doesn't exist as a "run hosted notebook" tool. Papermill is the correct substitute for local automation. Colab GPU path stays manual/job-runner. | High |
| Bass solfa colours | Restored via CSS variables + `getSolfaColour()` util, toggle in extract panel settings, applies to all solfa surfaces. | High |
| Extract panel | Full 5-tab rewrite covering all Plans 01–12 features, settings persisted to localStorage. | High |