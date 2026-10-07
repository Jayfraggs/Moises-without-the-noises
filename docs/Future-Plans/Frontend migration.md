
---

### [MIGRATE-FE] React → Vanilla HTML/CSS/JS Migration

**Target Files:**
- `frontend/src/` *(entire directory — audit and replace)*
- `frontend/index.html` *(restructure as the app shell)*
- `frontend/src/AudioEngine.js` *(keep — it's plain JS already)*
- `frontend/src/api.js` *(keep — already plain JS)*
- Delete: all `.jsx` files, `vite.config.js`, `package.json`, `node_modules/`

**Context:**
All UI has been authored as React/JSX. The backend serves `frontend/dist` as static files. With no build step, the backend should serve `frontend/` directly (or a designated `static/` folder). The Web Audio engine and API bridge are already framework-agnostic — only the UI layer needs replacement.

**Objective:**
Replace the entire React component tree with a single `index.html` shell + scoped CSS files + vanilla JS modules. No build step. No bundler. No npm. The backend mounts the folder directly via FastAPI `StaticFiles`.

**Technical Specifications:**

**File structure after migration:**
```
frontend/
├── index.html              ← app shell, all layout markup
├── css/
│   ├── reset.css
│   ├── main.css            ← layout, dark DAW theme, CSS variables
│   ├── transport.css
│   ├── stems.css
│   ├── solfa.css
│   ├── export.css
│   └── song-selector.css
└── js/
    ├── AudioEngine.js      ← unchanged
    ├── api.js              ← unchanged
    ├── main.js             ← app bootstrap, wires everything together
    ├── ui/
    │   ├── transport.js    ← replaces TransportControls.jsx
    │   ├── stems.js        ← replaces StemControls.jsx
    │   ├── solfa.js        ← replaces SolfaDisplay.jsx
    │   ├── noteDisplay.js  ← replaces NoteDisplay.jsx
    │   ├── songSelector.js ← replaces SongSelector.jsx
    │   ├── importSong.js   ← replaces ImportSong.jsx
    │   └── exportPanel.js  ← replaces ExportPanel.jsx
    └── state/
        └── store.js        ← lightweight observable store (no Redux, no lib)
```

**Design system (CSS variables on `:root`):**
```css
:root {
  --bg-primary: #0f0f0f;
  --bg-surface: #1a1a1a;
  --bg-elevated: #242424;
  --accent: #7c3aed;        /* purple — DAW feel */
  --accent-hover: #6d28d9;
  --text-primary: #f5f5f5;
  --text-muted: #6b7280;
  --stem-vocals: #f472b6;
  --stem-drums: #fb923c;
  --stem-bass: #34d399;
  --stem-guitar: #60a5fa;
  --stem-piano: #fbbf24;
  --stem-other: #a78bfa;
  --border: #2e2e2e;
  --radius: 6px;
  --font-mono: 'Courier New', Courier, monospace;
  --font-ui: system-ui, -apple-system, sans-serif;
}
```

**Component → JS module mapping:**

Each `ui/*.js` module exports an `init(container, state)` function and an `update(state)` function. No framework, no virtual DOM. Direct DOM manipulation via `document.createElement`, `innerHTML` (for static structure), and `addEventListener`.

`store.js` — minimal observable:
```js
// subscribers get called with the full state on every set()
export const store = {
  _state: {},
  _subs: [],
  get: () => store._state,
  set: (patch) => { store._state = {...store._state, ...patch}; store._subs.forEach(fn => fn(store._state)); },
  subscribe: (fn) => store._subs.push(fn),
};
```

**`main.js` responsibilities:**
- On `DOMContentLoaded`: init all UI modules into their `#mount` slots in `index.html`.
- Subscribe each UI module's `update` to the store.
- Call `api.fetchSongs()` → populate store → song selector renders.

**`index.html` layout structure:**
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MWTN</title>
  <link rel="stylesheet" href="css/reset.css">
  <link rel="stylesheet" href="css/main.css">
  <!-- per-component CSS loaded here -->
</head>
<body>
  <div id="app">
    <header id="song-selector-mount"></header>
    <main>
      <section id="transport-mount"></section>
      <section id="stems-mount"></section>
      <section id="solfa-mount"></section>
      <section id="note-display-mount"></section>
    </main>
    <aside id="export-panel-mount"></aside>
  </div>
  <script type="module" src="js/main.js"></script>
</body>
</html>
```

**FastAPI static mount — update `backend/main.py`:**
```python
# Replace the current frontend/dist mount with:
from pathlib import Path
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
```

**Execution Constraints:**
- Zero npm, zero bundler, zero CDN references — fully offline after clone.
- `AudioEngine.js` and `api.js` must work as ES modules (`type="module"`) — they already use `export`; verify no CommonJS patterns crept in.
- No `import` from node_modules paths anywhere in HTML/JS.
- All JS files use native ES module syntax (`import`/`export`) — the browser handles it natively via `<script type="module">`.
- Dark DAW aesthetic. Flat. No shadows heavier than `0 1px 3px rgba(0,0,0,0.6)`. No gradients except subtle stem color accents.
- Maintain all existing function signatures in `api.js` and `AudioEngine.js` — only the UI consumption layer changes.

**Execution Constraints — what to DELETE:**
- `frontend/src/*.jsx`
- `frontend/vite.config.js`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/node_modules/` (if present)
- `frontend/dist/` (no longer needed — backend serves `frontend/` directly)

**Output Request:**
Return the complete file set: `index.html`, all `css/*.css` files, all `js/ui/*.js` files, `js/state/store.js`, `js/main.js`, and the updated static mount line for `backend/main.py`. Return each as a clearly labelled code block.
