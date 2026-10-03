/**
 * solfa.js — Tonic-Solfège Panel for the bass stem.
 *
 * Lifecycle:
 *   1. When a song loads, call SolfaPanel.loadSong(songId).
 *      - Tries GET /api/songs/{id}/solfa.
 *      - If 404, shows an "Extract" button. Clicking it POSTs to trigger
 *        extraction (runs pyin on the backend, ~30-60 s on CPU).
 *      - Once data arrives, renders the syllable grid.
 *   2. Studio calls SolfaPanel.tick(currentTime) on every animation frame.
 *      The panel highlights the syllable whose window covers currentTime.
 *   3. SolfaPanel.clear() resets state when a new song is loaded.
 *
 * Data shape expected from the backend:
 *   {
 *     key: "G# Major",
 *     scale: "Major",
 *     root: "G#",
 *     events: [
 *       { time: 0.512, duration: 0.48, pitch: "G#2", midi: 44, solfa: "Do", octave: 2 },
 *       …
 *     ]
 *   }
 */

const SOLFA_COLORS = {
  Do:   '#e85f6f',
  Re:   '#e89048',
  Mi:   '#e8c848',
  Fa:   '#88d878',
  Sol:  '#4aafe8',
  La:   '#b88fe0',
  Ti:   '#e878c8',
  // Minor-mode equivalents (same colours, different names)
  'Do#':'#e87080',
  'Re#':'#e8a060',
  'Mi#':'#e8d060',
  'Fa#':'#a8e090',
  'Sol#':'#60c0e8',
  'La#':'#c8a0f0',
  'Ti#':'#f090d8',
};

function el(id)   { return document.getElementById(id); }
function setText(id, v) { const e = el(id); if (e) e.textContent = v ?? ''; }

export class SolfaPanel {
  constructor({ API }) {
    this.API      = API;
    this._songId  = null;
    this._events  = [];       // sorted array of { time, duration, …solfa }
    this._current = -1;       // index of currently highlighted event
    this._loaded  = false;
    this._extracting = false;

    this._panel    = el('solfaPanel');
    this._grid     = el('solfaGrid');
    this._keyLabel = el('solfaKeyLabel');
    this._emptyEl  = el('solfaEmpty');
    this._extractBtn = el('solfaExtractBtn');
    this._spinner  = el('solfaSpinner');
    this._nowEl    = el('solfaNow');

    this._extractBtn?.addEventListener('click', () => this._triggerExtraction());
  }

  // ── Public API ─────────────────────────────────────────────────────────────

  async loadSong(songId) {
    this._songId  = songId;
    this._events  = [];
    this._current = -1;
    this._loaded  = false;
    this._extracting = false;
    this._showState('loading');

    try {
      const data = await this.API.getSolfa(songId);
      this._ingest(data);
    } catch (err) {
      if (err?.status === 404 || err?.message?.includes('404')) {
        this._showState('empty');
      } else {
        this._showState('error', err.message);
      }
    }
  }

  /** Called by Studio's rAF loop on every frame. */
  tick(currentTime) {
    if (!this._loaded || !this._events.length) return;
    const idx = this._findEvent(currentTime);
    if (idx === this._current) return;
    this._current = idx;
    this._highlightEvent(idx, currentTime);
  }

  clear() {
    this._songId  = null;
    this._events  = [];
    this._current = -1;
    this._loaded  = false;
    if (this._grid)     this._grid.innerHTML = '';
    if (this._nowEl)    { this._nowEl.textContent = ''; this._nowEl.style.display = 'none'; }
    if (this._keyLabel) this._keyLabel.textContent = '';
    this._showState('idle');
  }

  // ── Private ────────────────────────────────────────────────────────────────

  _ingest(data) {
    this._events = (data.events || []).slice().sort((a, b) => a.time - b.time);
    this._loaded  = true;
    if (this._keyLabel) {
      this._keyLabel.textContent = data.key || '';
    }
    this._renderGrid();
    this._showState('ready');
  }

  _renderGrid() {
    if (!this._grid) return;
    this._grid.innerHTML = '';

    this._events.forEach((ev, i) => {
      const cell = document.createElement('div');
      cell.className  = 'solfa-cell';
      cell.dataset.idx = i;
      cell.title = `${ev.pitch}  ${ev.solfa}  (${ev.time.toFixed(2)}s)`;

      const color = SOLFA_COLORS[ev.solfa] || '#aaa';

      // Octave badge (top-right)
      const badge = document.createElement('span');
      badge.className = 'solfa-octave';
      badge.textContent = ev.octave;

      // Main syllable
      const syl = document.createElement('span');
      syl.className = 'solfa-syl';
      syl.textContent = ev.solfa;
      syl.style.color = color;

      // Pitch name (small, below)
      const pitch = document.createElement('span');
      pitch.className = 'solfa-pitch';
      pitch.textContent = ev.pitch;

      // Width proportional to duration (clamped 28-120 px)
      const w = Math.max(28, Math.min(120, Math.round(ev.duration * 80)));
      cell.style.width = `${w}px`;
      cell.style.setProperty('--solfa-color', color);

      cell.appendChild(badge);
      cell.appendChild(syl);
      cell.appendChild(pitch);

      // Click to seek
      cell.addEventListener('click', () => {
        const seekEvt = new CustomEvent('solfa:seek', { detail: { time: ev.time } });
        document.dispatchEvent(seekEvt);
      });

      this._grid.appendChild(cell);
    });
  }

  /**
   * Binary search: return the index of the event active at `t`,
   * or -1 if between events or before the first.
   */
  _findEvent(t) {
    const evs = this._events;
    if (!evs.length) return -1;
    let lo = 0, hi = evs.length - 1, best = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      const ev  = evs[mid];
      if (t >= ev.time && t < ev.time + ev.duration) return mid;
      if (ev.time <= t) { best = mid; lo = mid + 1; }
      else              hi = mid - 1;
    }
    // Check the best candidate in case we overshot
    if (best >= 0) {
      const ev = evs[best];
      if (t >= ev.time && t < ev.time + ev.duration) return best;
    }
    return -1;
  }

  _highlightEvent(idx, currentTime) {
    // Remove previous highlight
    this._grid?.querySelectorAll('.solfa-cell.active').forEach(c => {
      c.classList.remove('active');
    });

    if (idx < 0) {
      if (this._nowEl) this._nowEl.style.display = 'none';
      return;
    }

    const cell = this._grid?.querySelector(`.solfa-cell[data-idx="${idx}"]`);
    if (cell) {
      cell.classList.add('active');
      // Scroll the active cell into view smoothly inside the panel
      cell.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }

    const ev = this._events[idx];
    if (this._nowEl && ev) {
      this._nowEl.style.display = '';
      this._nowEl.textContent   = `${ev.solfa}  ·  ${ev.pitch}`;
      this._nowEl.style.color   = SOLFA_COLORS[ev.solfa] || '#aaa';
    }
  }

  async _triggerExtraction() {
    if (this._extracting || !this._songId) return;
    this._extracting = true;
    this._showState('extracting');
    try {
      const data = await this.API.computeSolfa(this._songId);
      this._ingest(data);
    } catch (err) {
      this._showState('error', `Extraction failed: ${err.message}`);
      this._extracting = false;
    }
  }

  _showState(state, msg) {
    const states = {
      idle:       { empty: false, extract: false, spinner: false, error: false },
      loading:    { empty: false, extract: false, spinner: true,  error: false },
      empty:      { empty: true,  extract: true,  spinner: false, error: false },
      extracting: { empty: true,  extract: false, spinner: true,  error: false },
      ready:      { empty: false, extract: false, spinner: false, error: false },
      error:      { empty: true,  extract: true,  spinner: false, error: true  },
    }[state] || {};

    const show  = (id, on) => { const e = el(id); if (e) e.style.display = on ? '' : 'none'; };
    show('solfaEmpty',      states.empty);
    show('solfaExtractBtn', states.extract);
    show('solfaSpinner',    states.spinner);

    const errEl = el('solfaError');
    if (errEl) {
      errEl.style.display = states.error ? '' : 'none';
      if (states.error && msg) errEl.textContent = msg;
    }

    // Loading phrase
    if (state === 'loading')    setText('solfaPhrase', 'Loading solfège…');
    if (state === 'extracting') setText('solfaPhrase', 'Extracting bass notes — this may take a minute…');
    if (state === 'empty')      setText('solfaPhrase', 'No solfège data yet for this song.');
    if (state === 'idle')       setText('solfaPhrase', '');
    if (state === 'ready')      setText('solfaPhrase', '');
  }
}
