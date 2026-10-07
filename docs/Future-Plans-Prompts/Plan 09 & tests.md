Before generating Plan 09, I need to read the current project overview to know exactly what's already planned and what run scripts exist.Good. I have full context. Plan 09 in the uploaded set is **Lyrics-to-Notes Alignment** — synchronizing the Whisper word-level transcript against the note event stream. Also noting from the overview that run scripts are PowerShell (`activate.ps1`, `run.ps1`). I'll add a frontend-aware update to both.

---

### [PLAN-09] Lyrics-to-Notes Alignment

**Scope:** Takes the Whisper word-level transcript (`lyrics.json`) and the `MusicalEvent` stream from Plan 02 (vocals stem), aligns each word to its corresponding note(s), and produces a unified `aligned_lyrics.json`. Covers the backend aligner, API route, frontend display module (vanilla HTML/CSS/JS — no React), and Colab pipeline cell.

---

### [P09-BE-01] Lyrics-to-Notes Aligner

**Target Files:** `backend/alignment/lyrics_aligner.py` *(new)*, `backend/alignment/__init__.py` *(new)*

**Context:** Whisper produces `{ words: [{ word, start, end, probability }] }`. The vocals `MusicalEvent` list produces `[{ onset_s, duration_s, pitch_midi, pitch_hz, solfa, confidence }]`. The alignment task is a temporal join — for each word, find all notes whose onset falls within `[word.start - tolerance, word.end + tolerance]`. This is not ML — it's interval matching with a configurable tolerance.

**Objective:**
Implement `align_lyrics_to_notes(words: list[WordEvent], note_events: list[MusicalEvent], tolerance_s: float = 0.08) -> list[AlignedWord]`.

**Technical Specifications:**

Define these dataclasses in `backend/models/alignment.py` *(new)*:
```python
@dataclass
class WordEvent:
    word: str
    start: float        # seconds
    end: float          # seconds
    probability: float  # Whisper confidence 0..1

@dataclass
class AlignedWord:
    word: str
    start: float
    end: float
    probability: float
    notes: list[MusicalEvent]   # notes overlapping this word's window
    primary_note: Optional[MusicalEvent]  # highest-confidence note in window
    solfa: Optional[str]        # solfa of primary_note
    pitch_midi: Optional[int]   # pitch of primary_note
```

**Alignment logic:**
- For each `WordEvent`, collect all `MusicalEvent` objects where `note.onset_s >= word.start - tolerance` and `note.onset_s <= word.end + tolerance`.
- `primary_note`: from the collected set, pick the one with highest `confidence`. If tie, pick earliest onset.
- If no notes found in window: `notes=[]`, `primary_note=None`, `solfa=None`, `pitch_midi=None`.
- Return list of `AlignedWord` in word order.
- Full type hints. Pure function. No I/O.

**Parser helpers (also in `lyrics_aligner.py`):**
- `parse_whisper_output(lyrics_json: dict) -> list[WordEvent]` — handles both Whisper output formats: `{ words: [...] }` (word-level) and `{ segments: [{ words: [...] }] }` (segment-level). Flatten either into a flat word list.
- `load_aligned_lyrics(path: Path) -> list[AlignedWord]` — deserializes `aligned_lyrics.json` back to dataclasses.
- `dump_aligned_lyrics(aligned: list[AlignedWord], path: Path)` — serializes to JSON, atomic write (`.tmp` + rename).

**Execution Constraints:**
- Zero ML dependencies — stdlib + dataclasses only.
- Do not import librosa, torch, or whisper here.
- Tolerance must be a parameter, not a hardcoded constant — callers may tune it.

**Output Request:**
Return `backend/alignment/lyrics_aligner.py`, `backend/alignment/__init__.py`, and `backend/models/alignment.py`.

---

### [P09-BE-02] Alignment API Route

**Target Files:** `backend/main.py` *(add route)*

**Context:** Alignment is cheap (pure interval math) so it runs on-demand and caches. Requires both `lyrics.json` (Whisper output) and `notes_vocals.json` to be present. If solfa has been run (Plan 06), notes will already carry `solfa` fields — alignment picks them up automatically.

**Objective:**
Add `GET /api/songs/{song_id}/aligned-lyrics` that returns the aligned lyrics JSON.

**Technical Specifications:**
- Load `backend/data/{song_id}/lyrics.json` → `parse_whisper_output`.
- Load `backend/data/{song_id}/notes_vocals.json` → `list[MusicalEvent]`.
- Call `align_lyrics_to_notes(words, notes, tolerance_s=0.08)`.
- Cache to `backend/data/{song_id}/aligned_lyrics.json` — skip if exists and both source files are older (mtime).
- Response schema:
```json
{
  "song_id": "...",
  "word_count": 142,
  "aligned_count": 118,
  "unaligned_count": 24,
  "words": [
    {
      "word": "hold",
      "start": 4.12,
      "end": 4.48,
      "probability": 0.94,
      "solfa": "Sol",
      "pitch_midi": 67,
      "notes": [
        { "onset_s": 4.14, "duration_s": 0.31, "pitch_midi": 67, "solfa": "Sol", "confidence": 0.88 }
      ]
    }
  ]
}
```
- HTTP 404 if `lyrics.json` missing.
- HTTP 404 if `notes_vocals.json` missing — response body: `{ "error": "note_extraction_required", "detail": "Run note extraction on the vocals stem first." }`.
- HTTP 200 with `words: []` not a 404 if alignment produces zero results (degenerate case).
- Wrap in `asyncio.to_thread`.

**Execution Constraints:**
- Maintain existing route structure in `main.py`.
- Atomic cache write.

**Output Request:**
Return only the new route block for `main.py`.

---

### [P09-FE-01] Aligned Lyrics API Client

**Target Files:** `frontend/js/api.js` *(add function)*

**Context:** Follows existing blob/JSON fetch pattern in `api.js`.

**Objective:**
Add `fetchAlignedLyrics(songId)` to `api.js`.

**Technical Specifications:**
- `GET /api/songs/{songId}/aligned-lyrics`
- Returns parsed JSON or throws structured error on non-200.
- Consistent with existing error handling pattern.

**Execution Constraints:**
- Do not alter existing exports.

**Output Request:**
Return only the new function block.

---

### [P09-FE-02] AlignedLyrics Display Module

**Target Files:** `frontend/js/ui/alignedLyrics.js` *(new)*, `frontend/css/aligned-lyrics.css` *(new)*

**Context:** This is the karaoke-style synchronized lyric display, extended to show solfa and pitch information per word. It replaces the basic karaoke display from the existing karaoke editor. Vanilla JS — no React.

**Objective:**
Implement `initAlignedLyrics(container, state)` and `updateAlignedLyrics(state)` as a time-synced lyric display lane.

**Technical Specifications:**

**DOM structure rendered by `initAlignedLyrics`:**
```html
<div class="aligned-lyrics-panel">
  <div class="lyrics-mode-toggle">
    <button class="lyrics-mode-btn active" data-mode="karaoke">Karaoke</button>
    <button class="lyrics-mode-btn" data-mode="solfa">Solfa</button>
    <button class="lyrics-mode-btn" data-mode="both">Both</button>
  </div>
  <div class="lyrics-scroll-container" id="lyrics-scroll">
    <!-- word spans injected here -->
  </div>
</div>
```

**Word rendering (`_renderWords(alignedLyrics, mode)`):**
Each word becomes a `<span class="lyric-word" data-start="4.12" data-end="4.48">`:
- Mode `karaoke`: span text = `word.word`.
- Mode `solfa`: span text = `word.solfa ?? '—'`.
- Mode `both`: span text = `word.word`, `<sub class="lyric-solfa">Sol</sub>` below it.
- Words with `notes.length === 0`: add class `lyric-word--unaligned` (muted, italic).

**Time sync (`_syncToTime(currentTime)`):**
- Called on every `currentTime` update from the transport (high frequency — use `requestAnimationFrame` loop, not store subscription, to avoid over-rendering).
- Find the active word: `word.start <= currentTime <= word.end`.
- Remove `lyric-word--active` from all spans, add to the current one.
- Auto-scroll: if active word is outside the visible area of `#lyrics-scroll`, `scrollIntoView({ behavior: 'smooth', block: 'center' })`.

**State shape consumed from store:**
```js
{
  alignedLyrics: null | { words: [...] },
  currentTime: 0,
  lyricsMode: 'karaoke'   // 'karaoke' | 'solfa' | 'both'
}
```

**CSS (`aligned-lyrics.css`):**
```css
.lyric-word { 
  display: inline-block; 
  margin: 0 4px; 
  padding: 2px 4px; 
  border-radius: var(--radius); 
  font-family: var(--font-ui); 
  color: var(--text-muted); 
  transition: color 0.1s, background 0.1s; 
  cursor: default;
}
.lyric-word--active { 
  color: var(--text-primary); 
  background: var(--accent); 
}
.lyric-word--unaligned { 
  color: var(--text-muted); 
  font-style: italic; 
  opacity: 0.5; 
}
.lyric-solfa { 
  display: block; 
  font-size: 0.65em; 
  color: var(--stem-vocals); 
  font-family: var(--font-mono); 
}
```

**Execution Constraints:**
- Use `requestAnimationFrame` for sync loop — not store subscription (too slow at audio rates).
- Cancel the `rAF` loop on `destroy()` — expose `destroy()` from the module to prevent memory leaks when song changes.
- `scrollIntoView` must be throttled — do not call on every frame, only when the active word changes.
- Do not import AudioEngine directly — receive `currentTime` via a callback registered in `main.js`.

**Output Request:**
Return only `frontend/js/ui/alignedLyrics.js` and `frontend/css/aligned-lyrics.css`.

---

### [P09-FE-03] Wire AlignedLyrics into main.js and index.html

**Target Files:** `frontend/js/main.js` *(modify)*, `frontend/index.html` *(modify)*

**Context:** `main.js` bootstraps all UI modules. `index.html` needs the mount point. AlignedLyrics needs to be wired to the AudioEngine's `currentTime` via a `requestAnimationFrame` loop in `main.js`.

**Objective:**
Add the `alignedLyrics` module to the app bootstrap, wire the `rAF` time sync loop, and fetch aligned lyrics when a song is selected.

**Technical Specifications:**

**`index.html` addition:**
```html
<section id="aligned-lyrics-mount"></section>
```
Place between `#solfa-mount` and `#note-display-mount`.

**`main.js` additions:**
```js
import { initAlignedLyrics, updateAlignedLyrics } from './ui/alignedLyrics.js';
import { fetchAlignedLyrics } from './api.js';

// In song-load handler (when user selects a song):
const aligned = await fetchAlignedLyrics(songId).catch(() => null);
store.set({ alignedLyrics: aligned });

// rAF loop (single loop for all time-synced modules):
function syncLoop() {
  const currentTime = audioEngine.getCurrentTime(); // must expose this on AudioEngine
  updateAlignedLyrics({ currentTime });
  // also call metronome sync, solfa sync here
  requestAnimationFrame(syncLoop);
}
requestAnimationFrame(syncLoop);
```

**AudioEngine addition required:**
- Expose `getCurrentTime() -> float` on `AudioEngine.js` — returns `audioContext.currentTime - startOffset` when playing, or last paused position when paused.

**Execution Constraints:**
- Single `rAF` loop for all time-synced UI — do not create one per module.
- `fetchAlignedLyrics` failure must be silent (`.catch(() => null)`) — not all songs will have both lyrics and notes.

**Output Request:**
Return only the diff blocks for `main.js`, `index.html`, and the `getCurrentTime()` addition to `AudioEngine.js`.

---

### [P09-COLAB-01] Alignment Step in Colab Pipeline

**Target Files:** `colab/mwtn_pipeline.py` *(add section)*, `colab/mwtn_notebook.ipynb` *(add cell)*

**Context:** After solfa (Plan 06) and before zip: run alignment and write `aligned_lyrics.json` into the song folder. Alignment is instant on any hardware — pure Python interval math.

**Objective:**
Add a Colab cell that calls `align_lyrics_to_notes` and writes `aligned_lyrics.json`.

**Technical Specifications:**
- Guard: skip if `lyrics.json` or `notes_vocals.json` missing — log which is absent.
- On success: log word count, aligned count, unaligned count, and file size.
- Cell is idempotent — overwrites existing `aligned_lyrics.json`.
- **Mobile data note:** Zero network cost. Pure computation.

**Execution Constraints:**
- No new pip installs.
- Failure must not abort the pipeline — `try/except` with logged warning.

**Output Request:**
Return the notebook cell JSON block and the `mwtn_pipeline.py` function.

---

### [P09-RUN-01] Run Script Updates

**Target Files:** `activate.ps1`, `run.ps1`

**Context:** The frontend is now vanilla HTML/CSS/JS served directly by FastAPI `StaticFiles`. There is no longer a Vite dev server, no `npm install`, no `npm run dev`. Both scripts must reflect this. `run.ps1` currently likely starts both a Vite frontend process and the FastAPI backend as separate processes — that second process is now unnecessary.

**Objective:**
Update both PowerShell scripts to remove all Node/Vite/npm references and reflect the new single-process serving model.

**Technical Specifications:**

**`activate.ps1` changes:**
- Remove: any `npm install`, `npm ci`, `node_modules` check, Vite-related setup.
- Remove: Demucs model download step (already flagged in PS-01 from the overview — confirm it's gone).
- Keep: Python venv creation/activation, `pip install -r requirements.txt`.
- Add: check that `frontend/index.html` exists — warn if missing (means the migration hasn't been applied yet).
- Add: print a clear note that the frontend is served by FastAPI — no separate frontend server needed.
- Output format: colored `Write-Host` blocks. Green = OK, Yellow = warning, Red = error.

**`run.ps1` changes:**
- Remove: any `Start-Process` or `npm run dev` or Vite process launch.
- Remove: any frontend port reference (e.g., `http://localhost:5173`).
- Keep: FastAPI backend launch (`uvicorn backend.main:app --reload`).
- Add: startup health check — after launching uvicorn, poll `http://localhost:8000/api/songs` with a short retry loop (5 attempts, 1s apart). Print status.
- Add: print the correct URL — `http://localhost:8000` (not 5173).
- Add: Electron launch step (if `electron/` exists and `electron` is in PATH) — `Start-Process electron .` after health check passes. Wrap in `try/catch` so Electron absence doesn't abort the script.
- Keep: clear error if backend venv missing (PS-02 requirement — confirm it's present).

**Execution Constraints:**
- Scripts must remain runnable on Windows PowerShell 5.1+ (no `pwsh`-only syntax).
- Do not hardcode absolute paths — use `$PSScriptRoot` for relative resolution.
- Health check loop must not hang indefinitely — max 5 retries with a timeout message if backend doesn't start.

**Output Request:**
Return the complete updated `activate.ps1` and `run.ps1`.

---

**Bandwidth summary for Plan 09:**
- Zero new pip installs anywhere.
- Zero CDN refs in frontend.
- `aligned_lyrics.json` is text/JSON — a few KB per song. Negligible in the zip.
- The aligned lyrics display is pure DOM — no assets fetched at render time.
- **Plan 09 is fully safe to build and run on mobile data.**