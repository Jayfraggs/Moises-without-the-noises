Good. Plan 11 is the **Score UI** — the in-app musical score viewer. This is the most frontend-heavy plan in the set. Keeping strictly to vanilla HTML/CSS/JS per the migration.

---

### [PLAN-11] Score UI — In-App Musical Score Viewer

**Scope:** A canvas-based score renderer that displays the `MusicalEvent` stream as a readable musical score — staff notation, piano roll, and solfa lane — all three views switchable. Time-synced to playback. Supports the stems the user has extracted (vocals, bass, guitar, piano). No external notation library — rendered entirely with the Canvas 2D API and inline SVG. Covers the renderer engine, the UI module, CSS, `main.js` wiring, `index.html` mount, and run script notes.

---

### [P11-FE-01] Score Renderer Engine

**Target Files:** `frontend/js/score/renderer.js` *(new)*, `frontend/js/score/layout.js` *(new)*, `frontend/js/score/notation.js` *(new)*

**Context:** Three render modes share a common data pipeline. The input is always `list[MusicalEvent]` (with `pitch_midi`, `onset_s`, `duration_s`, `solfa`, `beat_number`, `bar_number`, `duration_type` from Plan 04). The renderer draws to an `HTMLCanvasElement`. The layout engine converts time/pitch to canvas coordinates. The notation module handles music symbol drawing (noteheads, stems, beams, rests, clef, time sig, key sig) using Canvas 2D path primitives — no SVG fonts, no VexFlow, no Lilypond.

---

#### `frontend/js/score/layout.js`

**Objective:** Pure coordinate math — converts `MusicalEvent` fields to pixel positions on the canvas.

**Technical Specifications:**

```js
export class ScoreLayout {
  constructor(options = {})
  // options: { canvasWidth, canvasHeight, staffTop, staffSpacing,
  //            pixelsPerSecond, pixelsPerBeat, mode }

  // Staff notation mode
  pitchToY(pitch_midi)         // maps MIDI pitch to Y pixel on staff (treble or bass clef)
  timeToX(onset_s)             // maps onset time (seconds) to X pixel
  durationToWidth(duration_s)  // maps duration to pixel width

  // Piano roll mode
  pitchToRollY(pitch_midi)     // maps MIDI 0–127 to Y in piano roll lane height
  timeToRollX(onset_s)         // same as timeToX, different scale possible

  // Solfa lane mode
  timeToSolfaX(onset_s)        // time → X
  solfaLaneY()                 // fixed Y positions per syllable label

  // Shared
  barLineX(bar_number)         // X position of bar line
  visibleTimeRange(scrollX)    // returns [start_s, end_s] for culling off-screen events
}
```

- Staff lines: 5 lines per staff, 10px spacing. Middle C (MIDI 60) = ledger line between treble and bass.
- Treble clef range rendered: MIDI 55 (G3) to MIDI 84 (C6). Bass clef: MIDI 36 (C2) to MIDI 57 (A3).
- Piano roll: full MIDI 21–108 (88 keys), each pitch = fixed row height of `Math.max(3, canvasHeight / 88)` px.
- `pixelsPerBeat` default: 80. `pixelsPerSecond` derived from BPM.

**Execution Constraints:**
- Pure math — no DOM access, no canvas context. Testable without a browser.
- All methods return numbers or `[number, number]` tuples. No side effects.

---

#### `frontend/js/score/notation.js`

**Objective:** Canvas 2D drawing primitives for standard music notation symbols.

**Technical Specifications:**

```js
export class NotationPainter {
  constructor(ctx, layout, theme)
  // theme: { staff, notehead, stem, beam, rest, text, clef, barLine }
  //        (all CSS var values resolved at init time)

  drawStaff(x, y, width)
  drawTrebleClef(x, y)          // approximated with bezier curves — no glyph font
  drawBassClef(x, y)
  drawTimeSignature(x, y, beats, beatType)
  drawKeySignature(x, y, fifths, clef)  // draws sharps or flats
  drawBarLine(x, y, height)
  drawNotehead(x, y, filled)    // filled = quarter/eighth; open = half; open+tail = whole
  drawStem(x, y, direction, length)
  drawBeam(notes)               // connects a group of flagged notes with a beam
  drawFlag(x, y, direction, count)      // single/double flag for 8th/16th
  drawRest(x, y, durationType)  // whole/half/quarter/eighth/16th rest symbols
  drawLedgerLine(x, y, width)
  drawAccidental(x, y, type)    // 'sharp' | 'flat' | 'natural'
  drawDot(x, y)                 // augmentation dot

  // Piano roll
  drawRollNote(x, y, width, height, color, label)
  drawRollGrid(visibleRange, bpm)

  // Solfa lane
  drawSolfaEvent(x, y, width, syllable, active, color)
  drawSolfaTimeline(events, currentTime)

  // Shared
  drawPlayhead(x)               // vertical red line at current time position
  drawTimeRuler(visibleRange, bpm)
}
```

**Treble clef approximation strategy:**
- Use 4–5 bezier curves that roughly trace the clef shape. It won't be engraver-quality but will be readable. Document this honestly in a code comment: `// Approximate treble clef — not a glyph font. Replace with SMuFL font if quality matters in v2.`
- Alternatively: embed the treble clef as a tiny inline SVG path string and draw it via `ctx.drawImage(svgBitmap, x, y)`. Specify this as the preferred approach — it's crisp at any scale and requires no font file.

**Execution Constraints:**
- All drawing uses `ctx.save()` / `ctx.restore()` around each symbol — never leave transforms or styles dirty.
- Theme colours resolved once in constructor via `getComputedStyle(document.documentElement)` — not on every draw call.
- No external font files. Staff notation uses system monospace only for text labels (octave numbers, dynamics).

---

#### `frontend/js/score/renderer.js`

**Objective:** Orchestrates layout + notation into a complete render pass. Manages the canvas, scroll position, and render loop.

**Technical Specifications:**

```js
export class ScoreRenderer {
  constructor(canvas, options)
  // options: { mode: 'staff'|'piano_roll'|'solfa', stems: [...], theme }

  load(stemEvents)   // stemEvents: { vocals: [MusicalEvent], bass: [...], ... }
  setMode(mode)      // switch render mode, re-render immediately
  setCurrentTime(t)  // called from rAF loop in main.js — updates playhead, auto-scrolls
  setActiveStem(stemName)  // highlights one stem's events, dims others
  scrollTo(time_s)   // programmatic scroll
  resize(width, height)    // called on window resize

  // internal
  _render()          // full redraw — called on mode change, resize, scroll
  _renderStaff()
  _renderPianoRoll()
  _renderSolfa()
  _autoScroll()      // keep playhead in view (left 20% of canvas width)
  _cull(events)      // filter to visible time range only
}
```

**Render loop integration:**
- `setCurrentTime(t)` does NOT trigger a full `_render()` — it only redraws the playhead and auto-scrolls if needed. Full redraw only on mode change, resize, or scroll.
- Playhead redraws use a separate overlay canvas (same dimensions, `position: absolute` on top, `pointer-events: none`) so the static score doesn't re-render at 60fps.

**Dual canvas architecture:**
```
<div class="score-container" style="position:relative">
  <canvas id="score-static"  />   ← score content, redraws on change only
  <canvas id="score-overlay" />   ← playhead only, redraws at 60fps
</div>
```

**Multi-stem rendering (staff mode):**
- Each stem gets its own staff system (grand staff for piano, single treble for vocals/guitar, single bass for bass).
- Stems stacked vertically, separated by `24px` between systems.
- Visible stems controlled by `setActiveStem` — inactive stems rendered at 30% opacity.

**Execution Constraints:**
- Never call `_render()` inside `setCurrentTime` — playhead is overlay-only.
- `_cull(events)` must be called before every render pass — never iterate the full event list if only 10% is visible.
- `resize()` must debounce — 150ms after last resize event fires before redrawing.
- All canvas operations inside `requestAnimationFrame` callback — never draw synchronously from event handlers.

**Output Request:**
Return `frontend/js/score/layout.js`, `frontend/js/score/notation.js`, and `frontend/js/score/renderer.js`.

---

### [P11-FE-02] Score UI Module

**Target Files:** `frontend/js/ui/scorePanel.js` *(new)*, `frontend/css/score-panel.css` *(new)*

**Context:** The Score Panel is a full-width section below the stem lanes. It contains the mode switcher, stem selector, zoom control, and the dual-canvas score display. It initialises the `ScoreRenderer` and wires it to the store and rAF loop.

**Objective:**
Implement `initScorePanel(container, state)` and `updateScorePanel(state)`.

**Technical Specifications:**

**DOM structure rendered by `initScorePanel`:**
```html
<div class="score-panel">
  <div class="score-toolbar">
    <div class="score-mode-toggle">
      <button class="score-mode-btn active" data-mode="staff">Staff</button>
      <button class="score-mode-btn" data-mode="piano_roll">Piano Roll</button>
      <button class="score-mode-btn" data-mode="solfa">Solfa</button>
    </div>
    <div class="score-stem-selector">
      <!-- one button per available stem: vocals, bass, guitar, piano -->
      <button class="score-stem-btn active" data-stem="vocals">Vocals</button>
      <button class="score-stem-btn" data-stem="bass">Bass</button>
      <!-- etc -->
    </div>
    <div class="score-zoom">
      <button id="score-zoom-out">−</button>
      <span id="score-zoom-label">1×</span>
      <button id="score-zoom-in">+</button>
    </div>
    <button id="score-follow-toggle" class="active">Follow</button>
  </div>
  <div class="score-canvas-wrapper">
    <canvas id="score-static"></canvas>
    <canvas id="score-overlay"></canvas>
  </div>
</div>
```

**Behaviour:**
- **Mode toggle:** calls `renderer.setMode(mode)`. Active button gets `.active` class.
- **Stem selector:** calls `renderer.setActiveStem(stem)`. Available stems derived from `store.get().manifest.stems`.
- **Zoom:** increments `pixelsPerBeat` by 20 per click (range 40–200). Calls `renderer.resize()` equivalent — re-layout and re-render.
- **Follow toggle:** when active, `renderer._autoScroll()` is enabled. When inactive, user can drag-scroll freely.
- **Drag scroll:** `mousedown` + `mousemove` on `.score-canvas-wrapper` shifts the scroll position horizontally. Touch equivalent (`touchstart` + `touchmove`).

**`updateScorePanel(state)` triggers:**
- `state.notes` changed → call `renderer.load(state.notes)`.
- `state.activeSong` changed → reset scroll, re-render.
- `state.currentTime` changed → `renderer.setCurrentTime(state.currentTime)` (called from the rAF loop in `main.js`, not from store subscription — same rule as aligned lyrics).

**CSS (`score-panel.css`):**
```css
.score-panel {
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
  border-top: 1px solid var(--border);
  height: 340px;   /* fixed height — does not grow with stems */
}
.score-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.score-canvas-wrapper {
  position: relative;
  flex: 1;
  overflow: hidden;  /* canvas scrolling is internal */
}
#score-static, #score-overlay {
  position: absolute;
  top: 0; left: 0;
  width: 100%; height: 100%;
}
#score-overlay { pointer-events: none; }
.score-mode-btn, .score-stem-btn {
  background: var(--bg-elevated);
  color: var(--text-muted);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 4px 10px;
  font-family: var(--font-ui);
  font-size: 0.8rem;
  cursor: pointer;
}
.score-mode-btn.active, .score-stem-btn.active {
  background: var(--accent);
  color: var(--text-primary);
  border-color: var(--accent);
}
```

**Execution Constraints:**
- Canvas dimensions must be set in JS (`canvas.width = wrapper.offsetWidth * devicePixelRatio`) — not CSS. CSS sets display size; JS sets resolution. Always account for `devicePixelRatio` to avoid blurry canvas on HiDPI screens.
- `initScorePanel` must be idempotent — calling it twice must not create two renderers.
- Drag scroll must not interfere with transport play/pause click events.
- Score panel must degrade gracefully when `state.notes` is null — show a placeholder message inside the canvas: "No score data — run note extraction first."

**Output Request:**
Return only `frontend/js/ui/scorePanel.js` and `frontend/css/score-panel.css`.

---

### [P11-FE-03] Notes API Client Addition

**Target Files:** `frontend/js/api.js` *(add function)*

**Context:** `api.js` needs a function to fetch all note events for all stems in one call (or per-stem calls — backend decides). The Score Renderer needs notes for multiple stems simultaneously.

**Objective:**
Add `fetchAllNotes(songId, stems)` to `api.js`.

**Technical Specifications:**
- `stems`: `string[]` — e.g. `['vocals', 'bass', 'guitar', 'piano']`.
- Fires `fetchNotes(songId, stem)` for each stem in parallel (`Promise.all`).
- Returns `{ vocals: [...], bass: [...], guitar: [...], piano: [...] }` — keys only for stems that returned data (skip 404s silently).
- Individual stem 404 is not an error — some stems may not have notes yet.

**Execution Constraints:**
- Do not alter existing `fetchNotes`.
- Parallel fetch — `Promise.all`, not sequential.

**Output Request:**
Return only the new function block.

---

### [P11-FE-04] Wire Score Panel into main.js and index.html

**Target Files:** `frontend/js/main.js` *(modify)*, `frontend/index.html` *(modify)*

**Objective:**
Add the score panel mount point, import `scorePanel`, wire to the rAF loop, and fetch notes on song load.

**Technical Specifications:**

**`index.html` addition:**
```html
<!-- After #aligned-lyrics-mount, before closing </main> -->
<section id="score-panel-mount"></section>
```

**`main.js` additions:**

```js
import { initScorePanel, updateScorePanel } from './ui/scorePanel.js';
import { fetchAllNotes } from './api.js';

// On song load:
const PITCHED_STEMS = ['vocals', 'bass', 'guitar', 'piano'];
const notes = await fetchAllNotes(songId, PITCHED_STEMS);
store.set({ notes });
initScorePanel(document.getElementById('score-panel-mount'), store.get());

// In rAF loop (extend existing loop):
function syncLoop() {
  const currentTime = audioEngine.getCurrentTime();
  updateAlignedLyrics({ currentTime });
  updateScorePanel({ currentTime });   // ← add this line
  requestAnimationFrame(syncLoop);
}
```

**Window resize handler:**
```js
window.addEventListener('resize', debounce(() => {
  // scorePanel handles its own resize internally via ResizeObserver
}, 150));
```

Use `ResizeObserver` on the `.score-canvas-wrapper` inside `scorePanel.js` rather than `window.resize` — more precise and doesn't fire for unrelated layout changes.

**Execution Constraints:**
- `updateScorePanel` in the rAF loop only passes `currentTime` — not the full state. Full state updates come from store subscriptions inside `scorePanel.js`.
- Notes fetch failure is silent — score panel shows placeholder.

**Output Request:**
Return only the diff blocks for `main.js` and `index.html`.

---

### [P11-FE-05] Staff Notation Symbol SVG Paths

**Target Files:** `frontend/js/score/symbols.js` *(new)*

**Context:** Rather than approximating clef shapes with bezier guesswork, this module stores pre-defined SVG path strings for the essential notation symbols (treble clef, bass clef, sharp, flat, natural, whole/half note rest block shapes). The `NotationPainter` imports these and renders them via `Path2D` — crisp at any canvas resolution, zero font dependency, offline.

**Objective:**
Define and export SVG path data for all notation symbols used by `NotationPainter`.

**Technical Specifications:**

```js
// All paths are normalised to a 1×1 unit square.
// NotationPainter scales via ctx.scale() before drawing.
export const SYMBOLS = {
  TREBLE_CLEF:    "M ...",   // SVG path string
  BASS_CLEF:      "M ...",
  SHARP:          "M ...",
  FLAT:           "M ...",
  NATURAL:        "M ...",
  WHOLE_REST:     "M ...",   // rectangle hanging from 4th staff line
  HALF_REST:      "M ...",   // rectangle sitting on 3rd staff line
  COMMON_TIME:    "M ...",   // C symbol
  CUT_TIME:       "M ...",   // cut C
};

// Pre-compiled Path2D objects (faster than re-parsing strings on every draw)
export const PATHS = Object.fromEntries(
  Object.entries(SYMBOLS).map(([k, v]) => [k, new Path2D(v)])
);
```

**Path sourcing strategy (specify this clearly for the coding agent):**
- Source paths from the **SMuFL** (Standard Music Font Layout) reference glyph outlines — these are freely available and not copyrighted as path data. Use the Bravura font's published glyph outlines, which are OFL licensed.
- Specifically: extract path data from `BravuraText.svg` (the SVG font file in the Bravura release). The coding agent must fetch this from `https://github.com/steinbergmedia/bravura/releases` and extract the relevant glyph paths.
- Normalise each path to a 0–1 unit square by dividing all coordinates by the font's `units-per-em` value.
- **Bandwidth note for Jimi:** The coding agent does this extraction once as a build step. The resulting `symbols.js` is a static file committed to the repo — no runtime download, no CDN.

**Execution Constraints:**
- `PATHS` are created once at module load — not per draw call.
- The file is pure data + one `Object.fromEntries` call — no logic, no imports.
- Path strings must be valid SVG path syntax (`M`, `L`, `C`, `Z` commands only — no `A` arcs, which Canvas `Path2D` handles inconsistently across browsers).

**Output Request:**
Return `frontend/js/score/symbols.js` with the complete path data included (the coding agent must look up and include the actual path strings — not placeholders).

---

### [P11-BE-01] Notes Batch Endpoint

**Target Files:** `backend/main.py` *(add route)*

**Context:** The frontend's `fetchAllNotes` fires parallel per-stem requests. As an optimisation, also provide a single batch endpoint that returns all stems' notes in one response — useful when the user first opens a song and needs all score data immediately.

**Objective:**
Add `GET /api/songs/{song_id}/notes` (no stem qualifier) that returns all available note files in one JSON payload.

**Technical Specifications:**
- Scan `backend/data/{song_id}/` for all `notes_*.json` files.
- Load each, return as:
```json
{
  "song_id": "...",
  "stems": {
    "vocals": [ ...MusicalEvent... ],
    "bass":   [ ...MusicalEvent... ],
    "guitar": [ ...MusicalEvent... ]
  }
}
```
- Stems with no `notes_*.json` are omitted — not returned as empty arrays.
- HTTP 404 if no note files exist at all.
- Wrap in `asyncio.to_thread`.

**Execution Constraints:**
- No recomputation — read cached JSON files only.
- Maintain existing route structure.

**Output Request:**
Return only the new route block.

---

### [P11-RUN-01] Run Script Updates

**Target Files:** `run.ps1` *(modify)*

**Objective:**
Add a note about the Score Panel's canvas requirements. No structural changes.

**Technical Specifications:**

Add to the startup banner (after the health check passes):
```
Write-Host "Score UI: Staff / Piano Roll / Solfa views available after note extraction." -ForegroundColor Cyan
Write-Host "Tip: Run note extraction in Colab first for the best score experience." -ForegroundColor DarkCyan
```

Add a check: if `frontend/js/score/symbols.js` does not exist, print:
```
Write-Host "WARNING: Score symbols file missing (frontend/js/score/symbols.js). Score notation may render incorrectly." -ForegroundColor Yellow
```

**Execution Constraints:**
- Diff/addition only — not the full script.
- PowerShell 5.1+ compatible.

**Output Request:**
Return only the addition blocks.

---

**Bandwidth summary for Plan 11:**

- **Zero new pip installs** on backend.
- **Zero CDN references** in frontend — all notation drawn with Canvas 2D + pre-computed `Path2D` from `symbols.js`.
- **One-time agent cost:** The coding agent fetches Bravura SVG font from GitHub to extract glyph paths. This happens once during development, not at runtime. The result is committed as a static JS file. ~2 MB download, once, on WiFi — **delegate this specific step to when you're on an unmetered connection.**
- The batch notes endpoint (`/api/songs/{song_id}/notes`) returns JSON — a few hundred KB for a typical song. This is a local API call.
- The dual-canvas score display has zero network cost at runtime.
- **Plan 11 frontend work is safe on mobile data. The Bravura path extraction step is not — flag it and do it on WiFi.**