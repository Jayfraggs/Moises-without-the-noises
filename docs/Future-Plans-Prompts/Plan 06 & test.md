
---

### [PLAN-06] Solfa Engine — Movable-Do Solfège

**Scope:** Takes the `MusicalEvent` stream produced by Plan 02 (Transcription Engine) and Plan 04 (Rhythm/Quantization), resolves key context from Plan 05 (Harmonic Analysis), and emits movable-do solfège syllables per note. Also covers the data contract additions and the frontend display stub.

---

### [P06-BE-01] Solfa Resolver — Core Mapping Engine

**Target Files:** `backend/solfa/solfa_resolver.py` *(new file)*

**Context:** `MusicalEvent` objects carry `pitch_midi` (int), `pitch_hz` (float), and a `key_context` reference (tonic + mode from Plan 05). Movable-do assigns syllables relative to the tonic, not absolute pitch. Nigerian/West African ear-training uses strictly movable-do (never fixed-do), so the resolver must be tonic-relative at all times.

**Objective:**
Implement a pure function `resolve_solfa(events: list[MusicalEvent], tonic_midi: int, mode: str) -> list[MusicalEvent]` that attaches a `solfa` field to each event.

**Technical Specifications:**
- Chromatic movable-do map (12 semitones relative to tonic, 0–11):
  ```
  MAJOR_SOLFA = ["Do","Ra","Re","Me","Mi","Fa","Se","Sol","Le","La","Te","Ti"]
  # index = (pitch_midi - tonic_midi) % 12
  ```
  Use the standard chromatic syllables (Ra, Me, Se, Le, Te for chromatically altered degrees). Diatonic major uses Do Re Mi Fa Sol La Ti.
- For `mode == "minor"`: shift the syllable reference so that the relative minor tonic maps to "La" (La-based minor, which matches West African ear-training convention). Accept a `minor_as_la: bool = True` parameter to make this togglable.
- Rests (`pitch_midi == None` or `pitch_midi == 0`) → `solfa = None`.
- Add `solfa: Optional[str]` to the `MusicalEvent` dataclass (Plan 01 contract).
- Emit a `SolfaResult` dataclass: `{ events: list[MusicalEvent], tonic_midi: int, tonic_name: str, mode: str }`.
- Full type hints. No external dependencies beyond stdlib.

**Execution Constraints:**
- Do not mutate the input `MusicalEvent` list in place — return new objects or a copy.
- Keep this module dependency-free from audio I/O. It is pure data transformation.
- Do not import librosa, numpy, or torch here.

**Output Request:**
Return only `backend/solfa/solfa_resolver.py` and the diff to `backend/models/musical_event.py` adding the `solfa` field.

---

### [P06-BE-02] Solfa API Endpoint

**Target Files:** `backend/main.py` *(add route)*, `backend/solfa/__init__.py` *(new)*

**Context:** Frontend needs to fetch solfa annotations per song per stem. The data is cheap to compute (pure math after key is known) so it is computed on-demand from existing `notes_<stem>.json` + `key.json` and cached as `solfa_<stem>.json`.

**Objective:**
Add `GET /api/songs/{song_id}/stems/{stem_name}/solfa` that returns the `SolfaResult` as JSON.

**Technical Specifications:**
- Load `backend/data/{song_id}/notes_{stem_name}.json` → parse into `list[MusicalEvent]`.
- Load `backend/data/{song_id}/key.json` → extract `tonic_midi` and `mode`.
- Call `resolve_solfa(events, tonic_midi, mode)`.
- Cache result to `backend/data/{song_id}/solfa_{stem_name}.json` (skip recomputation if file exists and notes/key files haven't changed — use mtime comparison).
- Response schema:
  ```json
  {
    "song_id": "...",
    "stem": "vocals",
    "tonic": "C",
    "tonic_midi": 60,
    "mode": "major",
    "events": [
      { "onset_s": 0.5, "duration_s": 0.25, "pitch_midi": 64, "pitch_hz": 329.6, "solfa": "Mi", "confidence": 0.91 }
    ]
  }
  ```
- HTTP 404 if `notes_{stem_name}.json` or `key.json` missing (not an error — those may not have run yet).
- HTTP 200 with empty `events: []` if stem has no notes (e.g., drums).

**Execution Constraints:**
- Add to existing router pattern in `main.py` — do not restructure the file.
- Cache write must be atomic (write to `.tmp`, rename).

**Output Request:**
Return only the new route block for `main.py` and the full `backend/solfa/__init__.py`.

---

### [P06-FE-01] Solfa API Client

**Target Files:** `frontend/src/api.js` *(add function)*

**Context:** `api.js` already has `fetchNotes`, `fetchBeats`, `fetchKey`. Solfa follows the same pattern.

**Objective:**
Add `fetchSolfa(songId, stemName)` to `api.js`.

**Technical Specifications:**
- `GET /api/songs/{songId}/stems/{stemName}/solfa`
- Returns the full `SolfaResult` JSON or throws on non-200.
- Consistent with existing error handling pattern in `api.js`.

**Execution Constraints:**
- Do not alter any existing exports.
- No new dependencies.

**Output Request:**
Return only the new function block to splice into `api.js`.

---

### [P06-FE-02] SolfaDisplay Component

**Target Files:** `frontend/src/components/SolfaDisplay.jsx` *(new)*, `frontend/src/components/SolfaDisplay.css` *(new)*

**Context:** The score UI (Plan 11) will be the full rendering surface, but Plan 06 needs a functional display stub that works now — inline with the note display, time-synced to playback position.

**Objective:**
Create `SolfaDisplay` — a horizontally scrolling lane that shows solfa syllables time-locked to the audio transport position.

**Technical Specifications:**
- Props: `solfaResult: SolfaResult | null`, `currentTime: number` (seconds, from AudioEngine), `stemColor: string`.
- Layout: horizontal timeline. Each syllable occupies horizontal space proportional to its `duration_s`. Active syllable (the one whose window contains `currentTime`) is highlighted with `stemColor`, larger font.
- Inactive syllables: muted gray, smaller.
- Rests: render as a dotted line gap, not a blank — visually distinct.
- Horizontal scroll follows `currentTime` — keep active syllable centered in the lane.
- Font: system monospace (matches dark DAW aesthetic — no CDN fonts).
- No animation libraries. CSS `transform: translateX` driven by a `useEffect` on `currentTime`.
- Renders `null` gracefully when `solfaResult` is null or `events` is empty.

**Execution Constraints:**
- Strictly offline — zero external CDN references in CSS or JSX.
- Do not import from `AudioEngine.js` directly — receive `currentTime` as a prop.
- Use `useRef` for the scroll container, not `useState` for position (avoids re-render thrash at high update rates).

**Output Request:**
Return only `SolfaDisplay.jsx` and `SolfaDisplay.css`.

---

### [P06-COLAB-01] Wire Solfa into Colab Notebook

**Target Files:** `colab/mwtn_pipeline.py` *(add section)*, `colab/mwtn_notebook.ipynb` *(add cell)*

**Context:** The Colab pipeline already runs Demucs → Whisper → beat/key analysis and bundles results into a zip. Plan 06 needs a lightweight cell that runs the solfa resolver post-key-detection and writes `solfa_<stem>.json` into the song folder before zipping.

**Objective:**
Add a Colab pipeline step (after key detection, before zip) that calls the Python `resolve_solfa` logic for each stem that has a `notes_<stem>.json` and writes `solfa_<stem>.json`.

**Technical Specifications:**
- Import `solfa_resolver.py` (copy it into Colab or inline the logic — Colab can't `pip install` a local package cleanly, so inline or `exec`/`importlib` it from the repo clone).
- For each stem in `["vocals", "bass", "guitar", "piano"]` (skip drums/other — no pitched notes):
  - Check `notes_{stem}.json` exists.
  - Load `key.json` for tonic/mode.
  - Run `resolve_solfa` and write `solfa_{stem}.json`.
- Log skipped stems (missing notes file) cleanly.
- **Mobile data note:** This step adds zero network usage — it's pure computation on already-downloaded data.

**Execution Constraints:**
- The cell must be idempotent — re-running overwrites existing `solfa_*.json` files safely.
- Do not add new pip installs to the Colab cell.

**Output Request:**
Return the new notebook cell as a raw JSON cell block and the corresponding `mwtn_pipeline.py` function.

---

