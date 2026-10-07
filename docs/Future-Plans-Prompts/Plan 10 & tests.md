### [PLAN-10] Confidence Scoring + Human Review Layer

**Scope:** Every upstream plan (02–09) produces outputs with confidence values — Whisper word probabilities, pYIN note confidence, chord confidence, alignment match quality. Plan 10 aggregates these into a unified confidence model, flags low-confidence segments for human review, and provides a UI review interface where the user can correct, accept, or reject individual events. Also covers persistence of corrections back to the canonical `MusicalEvent` store.

---

### [P10-BE-01] Confidence Aggregator

**Target Files:** `backend/confidence/aggregator.py` *(new)*, `backend/confidence/__init__.py` *(new)*, `backend/models/confidence.py` *(new)*

**Context:** Each data type carries its own confidence signal in different shapes. This module normalises all of them to a common 0.0–1.0 scale and produces a per-event `ConfidenceScore` and a per-song `ConfidenceSummary`.

**Objective:**
Implement `aggregate_confidence(song_data: SongData) -> ConfidenceSummary` that reads all available JSON files for a song and produces a unified confidence report.

**Technical Specifications:**

**Dataclasses in `backend/models/confidence.py`:**
```python
@dataclass
class ConfidenceScore:
    source: str           # 'note', 'word', 'chord', 'alignment', 'key'
    item_id: str          # e.g. "vocals:note:042", "word:018"
    score: float          # 0.0 – 1.0 normalised
    raw_score: float      # original value before normalisation
    flagged: bool         # True if score < threshold for its source type
    flag_reason: str      # e.g. "below_note_threshold", "unaligned_word"

@dataclass  
class ConfidenceSummary:
    song_id: str
    overall_score: float          # weighted mean across all sources
    scores: list[ConfidenceScore]
    flagged_count: int
    flagged_by_source: dict[str, int]   # { 'note': 12, 'word': 4, ... }
    review_required: bool         # True if flagged_count / total > 0.15
```

**Normalisation rules (per source):**
```python
THRESHOLDS = {
    'note':      0.60,   # pYIN confidence
    'word':      0.70,   # Whisper word probability
    'chord':     0.55,   # chroma-based chord confidence
    'alignment': 0.50,   # overlap ratio from Plan 09
    'key':       0.65,   # Krumhansl-Schmuckler correlation
}
# score is already 0..1 for all sources — normalisation is just threshold comparison
```

**Data sources read (all optional — skip gracefully if file absent):**
- `notes_vocals.json` → note events, use `confidence` field.
- `lyrics.json` → Whisper words, use `probability` field.
- `chords.json` → chord events (Plan 05), use `confidence` field if present.
- `aligned_lyrics.json` → alignment quality = `len(word.notes) > 0` → 1.0, else 0.0.
- `key.json` → single key confidence value.

**`overall_score`:** weighted mean — notes weight 0.35, words 0.25, chords 0.20, alignment 0.15, key 0.05.

**`review_required`:** `flagged_count / max(total_items, 1) > 0.15`.

**Execution Constraints:**
- Pure function. No I/O inside `aggregate_confidence` — caller loads data and passes it.
- Provide a separate `load_song_data(song_dir: Path) -> SongData` loader function.
- Zero ML deps — stdlib + dataclasses only.
- All source reads wrapped in `try/except` — a missing or malformed file contributes zero items, not a crash.

**Output Request:**
Return `backend/confidence/aggregator.py`, `backend/confidence/__init__.py`, and `backend/models/confidence.py`.

---

### [P10-BE-02] Corrections Store

**Target Files:** `backend/confidence/corrections.py` *(new)*

**Context:** When the user accepts, rejects, or edits a flagged event in the review UI, those corrections must be persisted. The corrections live in `backend/data/{song_id}/corrections.json` — a flat list of correction records. Downstream consumers (MIDI exporter, MusicXML exporter, solfa resolver) check for corrections and apply them before producing output.

**Objective:**
Implement the corrections read/write layer and a `apply_corrections` function that merges corrections into a `MusicalEvent` list.

**Technical Specifications:**

**`backend/models/confidence.py` addition:**
```python
@dataclass
class Correction:
    item_id: str              # matches ConfidenceScore.item_id
    source: str               # 'note' | 'word' | 'chord' | 'alignment'
    action: str               # 'accept' | 'reject' | 'edit'
    edited_value: Optional[dict]   # for 'edit' — the patched fields
    corrected_at: str         # ISO 8601 timestamp
    corrected_by: str         # 'human' | 'auto' (for future auto-correction pass)
```

**Functions in `corrections.py`:**
```python
def load_corrections(song_dir: Path) -> list[Correction]
def save_correction(song_dir: Path, correction: Correction) -> None  # atomic write
def apply_corrections(
    events: list[MusicalEvent],
    corrections: list[Correction]
) -> list[MusicalEvent]
```

**`apply_corrections` logic:**
- `reject`: remove the event from the list.
- `accept`: mark event `reviewed=True` (add field to `MusicalEvent` if not present), no other change.
- `edit`: merge `correction.edited_value` dict into the event's fields. Only allow editing: `pitch_midi`, `onset_s`, `duration_s`, `solfa`, `word` (for lyrics).

**Execution Constraints:**
- `save_correction` must be atomic (`.tmp` + rename) — corrections file may be written from concurrent review actions.
- `apply_corrections` returns a new list — does not mutate input.
- `item_id` format must be consistent with what `aggregator.py` generates — enforce this in the aggregator, not here.

**Output Request:**
Return only `backend/confidence/corrections.py` and the `Correction` dataclass addition to `backend/models/confidence.py`.

---

### [P10-BE-03] Confidence + Review API Routes

**Target Files:** `backend/main.py` *(add routes)*

**Objective:**
Add four routes:
- `GET /api/songs/{song_id}/confidence` — returns `ConfidenceSummary`.
- `GET /api/songs/{song_id}/confidence/flagged` — returns only flagged `ConfidenceScore` items.
- `POST /api/songs/{song_id}/corrections` — accepts and persists a `Correction`.
- `GET /api/songs/{song_id}/corrections` — returns all corrections for a song.

**Technical Specifications:**

`GET /api/songs/{song_id}/confidence`:
- Load song data, run `aggregate_confidence`, cache to `confidence.json`.
- Cache invalidation: regenerate if any source file (`notes_*.json`, `lyrics.json`, etc.) is newer than `confidence.json`.
- Return full `ConfidenceSummary` as JSON.

`GET /api/songs/{song_id}/confidence/flagged`:
- Load (or compute) `ConfidenceSummary`.
- Return only `{ flagged_count, review_required, items: [ConfidenceScore where flagged==True] }`.
- Sort by `score` ascending (worst first).

`POST /api/songs/{song_id}/corrections`:
- Request body: `{ item_id, source, action, edited_value? }`.
- Validate `action` ∈ `{'accept', 'reject', 'edit'}`.
- Validate `edited_value` present when `action == 'edit'`.
- Stamp `corrected_at` server-side (UTC ISO 8601), `corrected_by = 'human'`.
- Call `save_correction`.
- Invalidate `confidence.json` cache (delete it) so next GET recomputes.
- Return `{ "status": "saved", "item_id": "..." }`.

`GET /api/songs/{song_id}/corrections`:
- Load and return `corrections.json` as-is.
- Return `{ "corrections": [] }` if file absent.

**Execution Constraints:**
- All routes wrapped in `asyncio.to_thread` for file I/O.
- Structured error JSON on all failures — no raw 500 HTML.
- Maintain existing route structure.

**Output Request:**
Return only the four new route blocks for `main.py`.

---

### [P10-FE-01] Confidence API Client

**Target Files:** `frontend/js/api.js` *(add functions)*

**Objective:**
Add four functions to `api.js`:
- `fetchConfidence(songId)` → `GET /api/songs/{songId}/confidence`
- `fetchFlagged(songId)` → `GET /api/songs/{songId}/confidence/flagged`
- `postCorrection(songId, correction)` → `POST /api/songs/{songId}/corrections`
- `fetchCorrections(songId)` → `GET /api/songs/{songId}/corrections`

**Technical Specifications:**
- All JSON (not blob). Throw structured error on non-200.
- `postCorrection` sends `Content-Type: application/json`, body = `JSON.stringify(correction)`.
- Consistent with existing `api.js` pattern.

**Execution Constraints:**
- Do not alter existing exports.
- No new dependencies.

**Output Request:**
Return only the four new function blocks for `api.js`.

---

### [P10-FE-02] Review Panel UI Module

**Target Files:** `frontend/js/ui/reviewPanel.js` *(new)*, `frontend/css/review-panel.css` *(new)*

**Context:** Vanilla HTML/CSS/JS. This is the human review interface — a modal overlay that lists flagged items grouped by source type, lets the user accept/reject/edit each one, and posts corrections back to the API. It is triggered by a "Review" button that appears in the app header when `confidence.review_required === true`.

**Objective:**
Implement `initReviewPanel(container, state)` and the review modal logic.

**Technical Specifications:**

**Trigger button (injected into app header by `main.js`):**
```html
<button id="review-trigger" class="review-trigger-btn hidden">
  ⚠ Review Needed (<span id="review-count">0</span>)
</button>
```
Show/hide based on `store.get().confidence?.review_required`. Badge shows `flagged_count`.

**Modal DOM structure:**
```html
<div class="review-modal-overlay" id="review-overlay" hidden>
  <div class="review-modal">
    <header class="review-modal-header">
      <h2>Review Flagged Items</h2>
      <div class="review-progress">
        <span id="review-done">0</span> / <span id="review-total">0</span> reviewed
      </div>
      <button id="review-close">✕</button>
    </header>
    <div class="review-tabs">
      <!-- one tab per source type that has flagged items -->
    </div>
    <div class="review-list" id="review-list">
      <!-- flagged item cards injected here -->
    </div>
    <footer class="review-modal-footer">
      <button id="review-accept-all">Accept All Visible</button>
      <button id="review-done-btn">Done</button>
    </footer>
  </div>
</div>
```

**Item card (per flagged `ConfidenceScore`):**
```html
<div class="review-card" data-item-id="vocals:note:042" data-source="note">
  <div class="review-card-meta">
    <span class="review-source-badge">note</span>
    <span class="review-score">Score: 0.41</span>
    <span class="review-flag-reason">below_note_threshold</span>
  </div>
  <div class="review-card-content">
    <!-- For notes: show pitch (MIDI + name), onset time, duration, solfa -->
    <!-- For words: show word text, timestamp, Whisper probability -->
    <!-- For chords: show chord name, time range, confidence -->
  </div>
  <div class="review-card-actions">
    <button class="review-accept" data-item-id="...">✓ Accept</button>
    <button class="review-reject" data-item-id="...">✕ Reject</button>
    <button class="review-edit" data-item-id="...">✎ Edit</button>
  </div>
</div>
```

**Edit inline form (shown on "Edit" click, replaces card content):**
- For `note`: inputs for `pitch_midi` (number, 0–127), `onset_s` (number, step 0.01), `duration_s` (number, step 0.01), `solfa` (text).
- For `word`: input for `word` (text).
- For `chord`: input for chord name (text).
- Submit → `postCorrection(songId, { item_id, source, action: 'edit', edited_value: { ...formValues } })` → on success, mark card as reviewed, update progress counter.

**Accept/Reject:**
- Immediate POST to `/api/songs/{songId}/corrections`.
- On success: card gets class `review-card--done`, buttons disabled, progress counter increments.
- On error: inline error text below the card — no `alert()`.

**Accept All Visible:**
- Iterates all currently visible (active tab) un-reviewed cards.
- POSTs corrections sequentially (not parallel — avoid race on `corrections.json`).
- Shows a progress indicator while running.

**CSS (`review-panel.css`):**
- Modal overlay: `position: fixed; inset: 0; background: rgba(0,0,0,0.75); z-index: 1000`.
- Modal box: `max-width: 680px; max-height: 80vh; overflow-y: auto; background: var(--bg-surface); border-radius: var(--radius); border: 1px solid var(--border)`.
- Source badges: colour-coded — note = `var(--stem-vocals)`, word = `var(--accent)`, chord = `var(--stem-guitar)`, alignment = `var(--stem-bass)`, key = `var(--stem-piano)`.
- Reviewed cards: `opacity: 0.5`, `pointer-events: none` once accepted/rejected.
- Tabs: flat button row, active tab has `border-bottom: 2px solid var(--accent)`.

**Execution Constraints:**
- No `alert()` or `confirm()` anywhere.
- Modal must trap focus (keyboard navigation inside modal only while open) — add `tabindex="-1"` to overlay, focus it on open, restore previous focus on close.
- "Done" button closes modal and triggers a store refresh: `fetchConfidence(songId)` → `store.set({ confidence: result })`.
- Sequential POSTs in "Accept All" — do not use `Promise.all`.
- Fully offline — no CDN, no external fonts.

**Output Request:**
Return only `frontend/js/ui/reviewPanel.js` and `frontend/css/review-panel.css`.

---

### [P10-FE-03] Wire Review Panel into main.js and index.html

**Target Files:** `frontend/js/main.js` *(modify)*, `frontend/index.html` *(modify)*

**Objective:**
Add the review trigger button to the app header, wire confidence fetch on song load, and mount the review panel modal.

**Technical Specifications:**

**`index.html` additions:**
```html
<!-- In <header> / song-selector-mount area: -->
<button id="review-trigger" class="review-trigger-btn hidden">
  ⚠ Review Needed (<span id="review-count">0</span>)
</button>

<!-- Before closing </body>: -->
<div id="review-panel-mount"></div>
```

**`main.js` additions (in song-load handler):**
```js
import { initReviewPanel } from './ui/reviewPanel.js';
import { fetchConfidence } from './api.js';

// After song loads:
const confidence = await fetchConfidence(songId).catch(() => null);
store.set({ confidence });

// Init review panel (once, on app boot):
initReviewPanel(document.getElementById('review-panel-mount'), store.get());
```

**Store subscription for review trigger:**
```js
store.subscribe((state) => {
  const btn = document.getElementById('review-trigger');
  const count = document.getElementById('review-count');
  if (state.confidence?.review_required) {
    btn.classList.remove('hidden');
    count.textContent = state.confidence.flagged_count;
  } else {
    btn.classList.add('hidden');
  }
});
```

**Execution Constraints:**
- `initReviewPanel` called once on boot, not on every song change — panel fetches its own data when opened.
- `fetchConfidence` failure is silent — not all songs have enough data yet.

**Output Request:**
Return only the diff blocks for `main.js` and `index.html`.

---

### [P10-COLAB-01] Confidence Report in Colab Pipeline

**Target Files:** `colab/mwtn_pipeline.py` *(add section)*, `colab/mwtn_notebook.ipynb` *(add cell)*

**Context:** After alignment (Plan 09), after solfa (Plan 06) — all data is available. Run the aggregator and write `confidence.json` into the song folder so the app can surface the review prompt immediately when the user loads the zip.

**Objective:**
Add a Colab cell that runs `aggregate_confidence` and writes `confidence.json`.

**Technical Specifications:**
- Inline or import `aggregator.py` from repo clone.
- Print a confidence summary table: source → item count → flagged count → mean score.
- Print `review_required: True/False` prominently.
- If `review_required` is True: print a yellow warning block — "⚠ This song has low-confidence regions. Open the app and use the Review panel before exporting."
- Cell is idempotent.
- **Mobile data note:** Zero network cost. Pure computation.

**Execution Constraints:**
- No new pip installs.
- `try/except` around the whole cell — failure writes no `confidence.json` and logs a warning, does not abort the pipeline.

**Output Request:**
Return the notebook cell JSON block and the `mwtn_pipeline.py` function.

---

### [P10-RUN-01] Run Script Updates

**Target Files:** `activate.ps1`, `run.ps1`

**Objective:**
Minor additions only — Plan 10 adds no new pip packages and no new processes. Updates are informational.

**Technical Specifications:**

**`activate.ps1` addition:**
- Add a check that `backend/confidence/` directory exists after pip install. If absent, print a yellow warning: `"Confidence module not found — ensure Plan 10 has been applied."` This is a soft guard, not a hard stop.

**`run.ps1` addition:**
- After the health check passes, also hit `GET /api/songs` and if any songs are returned, print: `"Tip: Open a song and check the Review panel if confidence flags appear."` One line, green. Only prints if songs exist — skip if the library is empty.

**Execution Constraints:**
- No structural changes to either script — append only.
- PowerShell 5.1+ compatible.

**Output Request:**
Return only the specific additions (diff blocks, not the full scripts — those were already rewritten in Plan 09).

---

**Bandwidth summary for Plan 10:**
- Zero new pip installs anywhere.
- Zero CDN references in the frontend.
- `confidence.json` and `corrections.json` are small text files — single-digit KB each.
- The review panel fetches `confidence/flagged` on open — that's one local API call, no external network.
- **Plan 10 is fully safe to build and run on mobile data.**