### [EXTRACT-PANEL-01] Extract Panel — Full Menu and Settings Rewrite- DONE

**Target Files:** `frontend/js/ui/extractPanel.js` *(rewrite)*, `frontend/css/extract-panel.css` *(rewrite)*

**Context:** The existing extract panel covers basic stem separation options. Plans 01–12 added: note extraction (per stem, with pYIN config), chord detection, solfa resolution, lyric alignment, confidence aggregation, MIDI export, MusicXML export, click track generation, and the job queue. The panel needs a complete settings surface that exposes all of these without overwhelming new users.

**Objective:**
Rewrite the extract panel as a tabbed settings modal with five tabs: **Separation**, **Transcription**, **Score**, **Export**, and **Advanced**.

---

**DOM structure:**
```html
<div class="extract-panel-overlay" id="extract-overlay" hidden>
  <div class="extract-panel">

    <header class="extract-header">
      <h2>Extract &amp; Analyse</h2>
      <button id="extract-close" aria-label="Close">✕</button>
    </header>

    <nav class="extract-tabs" role="tablist">
      <button class="extract-tab active" data-tab="separation"   role="tab">Separation</button>
      <button class="extract-tab"         data-tab="transcription" role="tab">Transcription</button>
      <button class="extract-tab"         data-tab="score"         role="tab">Score</button>
      <button class="extract-tab"         data-tab="export"        role="tab">Export</button>
      <button class="extract-tab"         data-tab="advanced"      role="tab">Advanced</button>
    </nav>

    <div class="extract-body">
      <!-- tab panes injected here -->
    </div>

    <footer class="extract-footer">
      <span class="extract-status" id="extract-status"></span>
      <button id="extract-run-btn" class="extract-run-btn">Run Selected</button>
    </footer>

  </div>
</div>
```

---

**Tab 1 — Separation:**
```html
<div class="extract-pane" data-pane="separation">

  <div class="extract-section">
    <h3>Stem Model</h3>
    <div class="extract-radio-group">
      <label class="extract-radio">
        <input type="radio" name="demucs_model" value="htdemucs_6s" checked />
        <span>htdemucs_6s <span class="extract-badge extract-badge--recommended">Recommended</span></span>
        <small>6 stems: vocals, bass, guitar, piano, drums, other. Best quality.</small>
      </label>
      <label class="extract-radio">
        <input type="radio" name="demucs_model" value="htdemucs" />
        <span>htdemucs</span>
        <small>4 stems: vocals, bass, drums, other. Faster.</small>
      </label>
      <label class="extract-radio">
        <input type="radio" name="demucs_model" value="mdx_extra" />
        <span>mdx_extra</span>
        <small>4 stems. Alternative architecture — sometimes better on electronic music.</small>
      </label>
    </div>
  </div>

  <div class="extract-section">
    <h3>Stems to Separate</h3>
    <div class="extract-check-group" id="stem-select">
      <label><input type="checkbox" value="vocals"  checked /> Vocals</label>
      <label><input type="checkbox" value="bass"    checked /> Bass</label>
      <label><input type="checkbox" value="guitar"  checked /> Guitar</label>
      <label><input type="checkbox" value="piano"   checked /> Piano</label>
      <label><input type="checkbox" value="drums"   checked /> Drums</label>
      <label><input type="checkbox" value="other"   checked /> Other</label>
    </div>
    <p class="extract-hint">Deselecting stems still runs the full model — 
    it just skips writing those WAV files.</p>
  </div>

  <div class="extract-section">
    <h3>Processing Path</h3>
    <div class="extract-radio-group">
      <label class="extract-radio">
        <input type="radio" name="proc_path" value="colab" checked />
        <span>Google Colab (GPU) <span class="extract-badge extract-badge--recommended">Recommended</span></span>
        <small>Queues job via the job system. Requires Colab runner to be active.</small>
      </label>
      <label class="extract-radio">
        <input type="radio" name="proc_path" value="local" />
        <span>Local CPU</span>
        <small>Slow (30–90 min). No Colab needed. Runs directly on this machine.</small>
      </label>
    </div>
  </div>

</div>
```

---

**Tab 2 — Transcription:**
```html
<div class="extract-pane" data-pane="transcription" hidden>

  <div class="extract-section">
    <h3>Lyric Transcription (Whisper)</h3>
    <label class="extract-toggle-row">
      <input type="checkbox" id="enable-whisper" checked />
      <span>Enable lyric transcription</span>
    </label>
    <div class="extract-sub-settings" id="whisper-settings">
      <label class="extract-select-row">
        <span>Whisper model</span>
        <select name="whisper_model">
          <option value="tiny">tiny — fastest, lowest accuracy (~75 MB)</option>
          <option value="base">base (~140 MB)</option>
          <option value="small" selected>small — recommended (~460 MB)</option>
          <option value="medium">medium — best accuracy (~1.5 GB) ⚠ WiFi only</option>
        </select>
      </label>
      <label class="extract-select-row">
        <span>Language</span>
        <select name="whisper_language">
          <option value="auto">Auto-detect</option>
          <option value="en">English</option>
          <option value="es">Spanish</option>
          <option value="pt">Portuguese</option>
          <option value="fr">French</option>
          <option value="it">Italian</option>
          <option value="yo">Yoruba</option>
          <option value="ha">Hausa</option>
          <option value="ig">Igbo</option>
          <option value="sw">Swahili</option>
        </select>
      </label>
      <label class="extract-toggle-row">
        <input type="checkbox" id="enable-alignment" checked />
        <span>Align lyrics to notes after transcription (requires note extraction)</span>
      </label>
    </div>
  </div>

  <div class="extract-section">
    <h3>Note Extraction (pYIN)</h3>
    <label class="extract-toggle-row">
      <input type="checkbox" id="enable-notes" checked />
      <span>Extract notes from pitched stems</span>
    </label>
    <div class="extract-sub-settings" id="notes-settings">
      <p class="extract-hint">Pitched stems: vocals, bass, guitar, piano. 
      Drums and other are skipped automatically.</p>
      <label class="extract-select-row">
        <span>Confidence threshold</span>
        <select name="note_confidence">
          <option value="0.5">Lenient (0.5) — more notes, more errors</option>
          <option value="0.6" selected>Standard (0.6) — recommended</option>
          <option value="0.75">Strict (0.75) — fewer notes, higher quality</option>
        </select>
      </label>
      <label class="extract-select-row">
        <span>Min note duration</span>
        <select name="note_min_dur">
          <option value="0.05">50 ms — capture fast runs</option>
          <option value="0.1" selected>100 ms — recommended</option>
          <option value="0.2">200 ms — filter ornaments</option>
        </select>
      </label>
    </div>
  </div>

  <div class="extract-section">
    <h3>Chord Detection</h3>
    <label class="extract-toggle-row">
      <input type="checkbox" id="enable-chords" checked />
      <span>Detect chords from harmonic content</span>
    </label>
  </div>

</div>
```

---

**Tab 3 — Score:**
```html
<div class="extract-pane" data-pane="score" hidden>

  <div class="extract-section">
    <h3>Solfège</h3>
    <label class="extract-toggle-row">
      <input type="checkbox" id="enable-solfa" checked />
      <span>Generate solfège annotations</span>
    </label>
    <div class="extract-sub-settings" id="solfa-settings">
      <label class="extract-select-row">
        <span>System</span>
        <select name="solfa_system">
          <option value="movable_do" selected>Movable Do (recommended — ear training)</option>
          <option value="fixed_do">Fixed Do</option>
        </select>
      </label>
      <label class="extract-select-row">
        <span>Minor key convention</span>
        <select name="solfa_minor">
          <option value="la_based" selected>La-based minor (Do Re Mi… La Ti Do)</option>
          <option value="do_based">Do-based minor (Do Re Me Fa Sol Le Te Do)</option>
        </select>
      </label>
      <label class="extract-toggle-row">
        <input type="checkbox" id="solfa-colours" checked />
        <span>Show syllable colours in display</span>
      </label>
    </div>
  </div>

  <div class="extract-section">
    <h3>Rhythm Quantization</h3>
    <label class="extract-select-row">
      <span>Smallest note value</span>
      <select name="quantize_grid">
        <option value="8">Eighth note</option>
        <option value="16" selected>Sixteenth note (recommended)</option>
        <option value="32">Thirty-second note (dense passages)</option>
      </select>
    </label>
    <label class="extract-toggle-row">
      <input type="checkbox" id="enable-beaming" checked />
      <span>Auto-beam eighth and sixteenth notes</span>
    </label>
  </div>

  <div class="extract-section">
    <h3>Confidence Review</h3>
    <label class="extract-toggle-row">
      <input type="checkbox" id="enable-confidence" checked />
      <span>Run confidence scoring after extraction</span>
    </label>
    <div class="extract-sub-settings" id="confidence-settings">
      <label class="extract-select-row">
        <span>Flag threshold</span>
        <select name="confidence_threshold">
          <option value="0.10">10% flagged → review required</option>
          <option value="0.15" selected>15% flagged (recommended)</option>
          <option value="0.25">25% flagged (lenient)</option>
        </select>
      </label>
    </div>
  </div>

</div>
```

---

**Tab 4 — Export:**
```html
<div class="extract-pane" data-pane="export" hidden>

  <div class="extract-section">
    <h3>Score Export</h3>
    <div class="extract-export-grid">

      <div class="extract-export-card" id="export-midi">
        <div class="extract-export-icon">🎹</div>
        <div class="extract-export-info">
          <strong>MIDI</strong>
          <small>Multi-track .mid file. Open in any DAW or MuseScore.</small>
        </div>
        <button class="extract-download-btn" data-export="midi"
                data-disabled-reason="Run note extraction first">
          Download .mid
        </button>
      </div>

      <div class="extract-export-card" id="export-musicxml">
        <div class="extract-export-icon">🎼</div>
        <div class="extract-export-info">
          <strong>MusicXML</strong>
          <small>Standard notation file. Open in MuseScore, Sibelius, Finale.</small>
        </div>
        <button class="extract-download-btn" data-export="musicxml"
                data-disabled-reason="Run note extraction first">
          Download .xml
        </button>
      </div>

      <div class="extract-export-card" id="export-click">
        <div class="extract-export-icon">🥁</div>
        <div class="extract-export-info">
          <strong>Click Track</strong>
          <small>Mono WAV. Downbeat 1000 Hz, beat 800 Hz.</small>
        </div>
        <button class="extract-download-btn" data-export="click"
                data-disabled-reason="Run beat detection first">
          Download .wav
        </button>
      </div>

    </div>

    <div class="extract-musescore-hint">
      <strong>Opening in MuseScore:</strong> Download the .xml file above, 
      then double-click it in MuseScore 4. No plugin required — MusicXML is 
      MuseScore's native import format.
    </div>
  </div>

  <div class="extract-section">
    <h3>Stem Audio Export</h3>
    <div class="extract-stem-mix" id="stem-mix-controls">
      <!-- one fader row per available stem, generated from manifest -->
    </div>
    <div class="extract-export-row">
      <label class="extract-select-row">
        <span>Format</span>
        <select name="export_format">
          <option value="wav">WAV (lossless)</option>
          <option value="mp3">MP3 (compressed)</option>
          <option value="flac">FLAC (lossless compressed)</option>
        </select>
      </label>
      <button id="export-mix-btn">Export Mix</button>
      <button id="export-stems-btn">Export All Stems</button>
    </div>
    <label class="extract-toggle-row">
      <input type="checkbox" id="export-include-click" />
      <span>Include click track in mix export</span>
    </label>
  </div>

</div>
```

---

**Tab 5 — Advanced:**
```html
<div class="extract-pane" data-pane="advanced" hidden>

  <div class="extract-section">
    <h3>Colab Automation</h3>
    <label class="extract-select-row">
      <span>Papermill notebook path</span>
      <input type="text" name="papermill_notebook"
             placeholder="colab/mwtn_notebook.ipynb"
             value="colab/mwtn_notebook.ipynb" />
    </label>
    <label class="extract-select-row">
      <span>Output notebook path</span>
      <input type="text" name="papermill_output"
             placeholder="colab/output/run_{timestamp}.ipynb" />
    </label>
    <label class="extract-toggle-row">
      <input type="checkbox" id="papermill-auto" />
      <span>Auto-run notebook via Papermill when job is queued</span>
    </label>
    <p class="extract-hint">Requires Papermill installed. See docs/colab-guide.md.</p>
  </div>

  <div class="extract-section">
    <h3>Job Queue</h3>
    <label class="extract-select-row">
      <span>Max retries on failure</span>
      <select name="job_max_retries">
        <option value="1">1</option>
        <option value="2" selected>2 (recommended)</option>
        <option value="3">3</option>
      </select>
    </label>
    <label class="extract-select-row">
      <span>Stale job timeout</span>
      <select name="stale_threshold">
        <option value="300">5 minutes</option>
        <option value="600" selected>10 minutes (recommended)</option>
        <option value="1200">20 minutes</option>
      </select>
    </label>
  </div>

  <div class="extract-section">
    <h3>Storage</h3>
    <div class="extract-storage-info" id="storage-info">
      <!-- populated by JS: song count, total size, _jobs count -->
    </div>
    <button id="clear-confidence-cache">Clear confidence cache</button>
    <button id="clear-corrections" class="extract-btn--danger">
      Clear all corrections for this song
    </button>
  </div>

  <div class="extract-section">
    <h3>Debug</h3>
    <label class="extract-toggle-row">
      <input type="checkbox" id="debug-show-confidence-scores" />
      <span>Show raw confidence scores in Review panel</span>
    </label>
    <label class="extract-toggle-row">
      <input type="checkbox" id="debug-log-audio-engine" />
      <span>Log AudioEngine events to console</span>
    </label>
  </div>

</div>
```

---

**Settings persistence:**
All extract panel settings are saved to `localStorage` under `mwtn_extract_settings` as a flat JSON object. On panel open, settings are read and applied to all form elements. On any change, re-save immediately.

```js
const SETTINGS_KEY = 'mwtn_extract_settings';
const defaults = {
  demucs_model: 'htdemucs_6s',
  proc_path: 'colab',
  enable_whisper: true,
  whisper_model: 'small',
  whisper_language: 'auto',
  enable_alignment: true,
  enable_notes: true,
  note_confidence: '0.6',
  note_min_dur: '0.1',
  enable_chords: true,
  enable_solfa: true,
  solfa_system: 'movable_do',
  solfa_minor: 'la_based',
  solfa_colours: true,       // ← bass solfa colours re-enabled here
  quantize_grid: '16',
  enable_beaming: true,
  enable_confidence: true,
  confidence_threshold: '0.15',
  export_format: 'wav',
  export_include_click: false,
  job_max_retries: '2',
  stale_threshold: '600',
};
```

**"Run Selected" button logic:**
Reads current settings, builds a job payload, and either:
- `proc_path === 'colab'`: calls `createJob(payload)` — opens job queue panel automatically.
- `proc_path === 'local'`: calls `POST /api/import` with the current file — existing local import path.

**Export button states:**
Each download button in Tab 4 checks `store.get().manifest` for the relevant flag:
- MIDI/MusicXML: disabled if `!manifest.notes_available`.
- Click track: disabled if `!manifest.has_beats`.
- Shows `data-disabled-reason` as a tooltip on hover when disabled.

**CSS — key rules:**
```css
.extract-panel-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.8);
  z-index: 1500;
  display: flex; align-items: center; justify-content: center;
}
.extract-panel {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  width: min(700px, 96vw);
  max-height: 88vh;
  display: flex; flex-direction: column;
}
.extract-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  background: var(--bg-elevated);
  flex-shrink: 0;
}
.extract-tab {
  padding: 10px 18px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-family: var(--font-ui);
  font-size: 0.85rem;
}
.extract-tab.active {
  color: var(--text-primary);
  border-bottom-color: var(--accent);
}
.extract-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}
.extract-section {
  margin-bottom: 24px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--border);
}
.extract-section:last-child { border-bottom: none; }
.extract-section h3 {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  margin-bottom: 12px;
}
.extract-export-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.extract-export-card {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px;
  display: flex; flex-direction: column; gap: 8px;
}
.extract-musescore-hint {
  background: rgba(124,58,237,0.08);
  border: 1px solid var(--accent);
  border-radius: var(--radius);
  padding: 12px;
  font-size: 0.82rem;
  color: var(--text-muted);
  margin-top: 12px;
}
.extract-download-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.extract-btn--danger {
  background: rgba(239,68,68,0.15);
  border: 1px solid #ef4444;
  color: #f87171;
}
.extract-badge--recommended {
  background: var(--accent);
  color: white;
  font-size: 0.7rem;
  padding: 1px 6px;
  border-radius: 10px;
  margin-left: 6px;
}
```

**Execution Constraints:**
- Tab switching hides/shows panes with `hidden` attribute — not CSS `display` toggle — so form state is preserved.
- All settings read/write via `localStorage` — no API calls for settings persistence.
- Export buttons in Tab 4 must call the same blob-download functions already in `api.js` — do not duplicate fetch logic.
- "Clear all corrections" requires an inline confirmation step (a "Are you sure?" text row that appears for 3 seconds) — no `confirm()` dialog.
- Panel must be openable from both the existing toolbar trigger and the job queue's "Run" shortcut.

**Output Request:**
Return complete `frontend/js/ui/extractPanel.js` and `frontend/css/extract-panel.css`.

