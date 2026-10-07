

### [PLAN-08] Smart Metronome + Click Track

**Scope:** BPM detection is already wired (Plan 03, `beats.json`). Plan 08 builds on that: a visual metronome display, a schedulable Web Audio click track generator, tempo tap-in, and click track export.

---

### [P08-BE-01] Click Track Audio Generator

**Target Files:** `backend/audio/click_track.py` *(new)*

**Context:** The frontend can generate a click track in-browser via Web Audio, but for export (burning the click into a downloadable WAV or adding it to the MIDI file) the backend needs to produce a click track as a WAV. `beats.json` already contains `{ bpm, beats: [{ time_s, beat_number, bar_number }] }`.

**Objective:**
Implement `generate_click_track(beats_json_path: Path, output_path: Path, sample_rate: int = 44100) -> Path` that writes a WAV file with an audible click at each beat timestamp.

**Technical Specifications:**
- Use `numpy` + `scipy.io.wavfile` (already in Colab/backend env).
- Click sound: short sine tone burst — 1000 Hz for downbeats (`beat_number == 1`), 800 Hz for other beats. Duration: 20 ms. Amplitude envelope: linear decay (avoids click artifact at tail).
- Output: mono 16-bit WAV at `sample_rate`.
- Total duration: from first beat to last beat + 2 seconds of silence.
- Return `output_path`.
- Full type hints.

**Execution Constraints:**
- Do not use `librosa` here — `scipy.io.wavfile` and `numpy` only.
- Stateless pure function — no global audio context.

**Output Request:**
Return only `backend/audio/click_track.py`.

---

### [P08-BE-02] Click Track Export API Route

**Target Files:** `backend/main.py` *(add route)*

**Context:** Consistent with existing stem export pattern. Returns a WAV file download.

**Objective:**
Add `GET /api/songs/{song_id}/click-track` that generates and returns the click track WAV.

**Technical Specifications:**
- Load `backend/data/{song_id}/beats.json`.
- Call `generate_click_track(...)`, write to `backend/data/{song_id}/click_track.wav`.
- Cache: skip regeneration if `click_track.wav` exists and `beats.json` mtime is older.
- Return `FileResponse`, `media_type="audio/wav"`, filename `{song_id}_click.wav`.
- HTTP 404 if `beats.json` missing.
- Wrap in `asyncio.to_thread`.

**Execution Constraints:**
- Maintain existing route structure.

**Output Request:**
Return only the new route block.

---

### [P08-FE-01] Metronome Engine (Web Audio)

**Target Files:** `frontend/js/metronome.js` *(new)*

**Context:** The browser-side click track uses the Web Audio API scheduler — not `setInterval` (which drifts). The approach is the standard "lookahead scheduler" pattern: a `setTimeout` loop schedules `OscillatorNode` bursts slightly ahead of time, keeping the click sample-accurate.

**Objective:**
Implement a `Metronome` class that plays a click track synchronized to the loaded song's beat timestamps.

**Technical Specifications:**
```js
export class Metronome {
  constructor(audioContext)
  load(beatsData)          // accepts parsed beats.json { bpm, beats: [{time_s, beat_number}] }
  start(offsetSeconds)     // begin scheduling from a given playback position
  stop()
  setVolume(0..1)
  setEnabled(bool)
  // internal:
  _schedule()              // lookahead scheduler, called via setTimeout
  _scheduleClick(time_s, isDownbeat)  // schedules one OscillatorNode burst
}
```

- Lookahead: 100 ms. Schedule interval: 25 ms (`setTimeout`).
- Click sound: `OscillatorNode` (sine), freq 1000 Hz downbeat / 800 Hz beat, duration 0.02 s, `GainNode` for volume and envelope (linear ramp to 0 over 20 ms).
- `start(offsetSeconds)`: map `offsetSeconds` to the correct index in `beats` array (binary search or linear scan — beats array is short).
- `stop()`: cancel all pending `setTimeout` calls and disconnect any scheduled-but-unfired nodes.
- Expose `onBeat(callback)` — fires on each scheduled beat (passes `{ time_s, beat_number, bar_number }`). Used by the UI to animate the visual metronome.

**Execution Constraints:**
- No external libs.
- Must tolerate `load()` being called before `start()` and `start()` being called before `load()` (guard both).
- Do not use `setInterval` — only `setTimeout` with self-rescheduling.

**Output Request:**
Return only `frontend/js/metronome.js`.

---

### [P08-FE-02] Metronome UI Module

**Target Files:** `frontend/js/ui/metronome.js` *(new)*, `frontend/css/metronome.css` *(new)*

**Context:** Visual metronome display: a pendulum/pulse indicator + BPM readout + tap-tempo button + enable/disable toggle. Lives in a `#metronome-mount` section added to `index.html`.

**Objective:**
Implement `initMetronome(container, state)` and `updateMetronome(state)` that render and animate the metronome UI module.

**Technical Specifications:**

HTML structure rendered by `initMetronome`:
```html
<div class="metronome-panel">
  <div class="metro-pulse" id="metro-pulse"></div>  <!-- flashes on beat -->
  <div class="metro-bpm">
    <span id="metro-bpm-value">120</span>
    <span class="metro-bpm-label">BPM</span>
  </div>
  <div class="metro-controls">
    <button id="metro-toggle">Enable Click</button>
    <button id="metro-tap">Tap Tempo</button>
  </div>
</div>
```

- **Pulse animation:** On `onBeat` callback from `Metronome`, add class `metro-pulse--active` to `#metro-pulse` for 80 ms, then remove. CSS handles the flash (no JS animation frames needed).
- **Tap Tempo:** Store last 4 tap timestamps in an array. On each tap, compute average interval → BPM. After 4 taps, call `store.set({ bpm: computedBpm })`. Reset if gap between taps > 3 seconds.
- **Toggle:** Enable/disable the `Metronome` engine. Button label toggles between "Enable Click" / "Disable Click".
- **BPM display:** Reads from `store.get().bpm`. Updates when store changes.

CSS:
- `metro-pulse`: 40×40 px circle, `var(--accent)` color, opacity 0.2 at rest.
- `metro-pulse--active`: opacity 1.0, scale 1.15. Transition: `opacity 0.08s ease, transform 0.08s ease`.
- Dark panel consistent with `--bg-surface`.

**Execution Constraints:**
- `initMetronome` must add `#metronome-mount` slot to `index.html` — remind the coding agent to add `<section id="metronome-mount"></section>` to the HTML shell.
- Tap tempo must not `alert()` or `console.error` on bad input — fail silently.
- No animation libs. CSS transitions only.

**Output Request:**
Return only `frontend/js/ui/metronome.js` and `frontend/css/metronome.css`.

---

### [P08-FE-03] Click Track Download Button

**Target Files:** `frontend/js/ui/exportPanel.js` *(modify)*

**Context:** The Export Panel (migrated from `ExportPanel.jsx` in MIGRATE-FE) handles audio stem and score exports. Plan 08 adds a "Download Click Track" button.

**Objective:**
Add a "Click Track" section to `exportPanel.js` with a download button that hits `GET /api/songs/{song_id}/click-track`.

**Technical Specifications:**
- Same blob-download pattern as MIDI/MusicXML in Plan 07.
- Loading + error states identical to existing export buttons.
- Disabled with tooltip "Beats not detected yet" if `manifest.has_beats === false`.
- Label: `Download Click Track (.wav)`.

**Execution Constraints:**
- Do not restructure the export panel — append the new section.
- No new API functions in `api.js` needed — inline the fetch or add `downloadClickTrack(songId)` to `api.js` following the existing blob-fetch pattern.

**Output Request:**
Return only the modified `exportPanel.js` section and the `api.js` addition.

---

### [P08-COLAB-01] Click Track Generation in Colab Pipeline

**Target Files:** `colab/mwtn_pipeline.py` *(add section)*, `colab/mwtn_notebook.ipynb` *(add cell)*

**Context:** After beats are computed and `beats.json` is written, generate the click track WAV in Colab (GPU session has numpy/scipy already) and bundle it into the zip.

**Objective:**
Add a pipeline cell that calls `generate_click_track` and writes `click_track.wav` into the song folder.

**Technical Specifications:**
- Import `generate_click_track` from `click_track.py` (inline or repo clone import).
- Guard in `try/except` — failure skips click track, does not abort the pipeline.
- Log output file size on success.
- Cell is idempotent.
- **Mobile data note:** Zero new pip installs — `numpy` and `scipy` are pre-installed in Colab.

**Output Request:**
Return the notebook cell JSON block and the `mwtn_pipeline.py` function.

---

**Bandwidth summary for Plan 08:**
- Zero new pip installs in Colab (numpy + scipy already present).
- Zero CDN references in frontend.
- Click track WAV download from the API: ~1–3 MB per song depending on length. Flag to user before triggering — add a file size estimate to the button tooltip.
- **Plan 08 is safe to build on mobile data.** The only data cost is downloading the generated WAV, which the user controls by clicking the button.
