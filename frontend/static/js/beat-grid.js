/**
 * beat-grid.js — Beat grid editor.
 *
 * Two modes:
 *   DISPLAY — canvas overlay on the ruler showing beat ticks + bar numbers.
 *   EDIT    — DOM ticks are interactive: drag to move, right-click to delete,
 *             click on empty space to add. Saved to backend via PATCH /beats.
 *
 * Usage (wired in app.js):
 *   const grid = new BeatGrid({ State, API, studio });
 *   grid.init();                    // bind toolbar buttons
 *   grid.loadSong(songId);          // called after studio.loadSong
 *   grid.clear();                   // called before next loadSong
 */
export class BeatGrid {
  constructor({ State, API, studio }) {
    this.State  = State;
    this.API    = API;
    this.studio = studio;

    this._editMode = false;
    this._beats    = [];   // local mutable copy
    this._bars     = [];
    this._saveTimer = null;
    this._dirty     = false;
    this._rulerEl   = document.getElementById('ruler-time');
    this._canvas    = null;   // overlay canvas for display mode
    this._resizeObs = null;
  }

  // ── Public ─────────────────────────────────────────────────────────────────

  init() {
    document.getElementById('beatEditToggleBtn')?.addEventListener('click', () => this.toggleEditMode());
    document.getElementById('beatResetBtn')?.addEventListener('click',      () => this._reset());
    document.getElementById('beatSaveBtn')?.addEventListener('click',       () => this._save(true));
  }

  loadSong(songId) {
    this._songId   = songId;
    this._beats    = [...(this.State.beats?.beats  || [])];
    this._bars     = [...(this.State.beats?.bars   || [])];
    this._dirty    = false;
    this._editMode = false;

    this._buildCanvas();
    this._render();
    this._updateToolbar();
  }

  clear() {
    this._beats = []; this._bars = []; this._dirty = false; this._editMode = false;
    this._canvas?.remove(); this._canvas = null;
    this._resizeObs?.disconnect(); this._resizeObs = null;
    this._clearDomTicks();
    this._updateToolbar();
  }

  toggleEditMode() {
    this._editMode = !this._editMode;
    this.State.beatEditMode = this._editMode;
    document.getElementById('beatEditToggleBtn')?.classList.toggle('active', this._editMode);
    document.getElementById('beatGridToolbar')?.classList.toggle('edit-active', this._editMode);
    if (this._editMode) {
      this._canvas && (this._canvas.style.display = 'none');
      this._renderDomTicks();
    } else {
      this._clearDomTicks();
      this._canvas && (this._canvas.style.display = '');
      this._render();
    }
    this._updateToolbar();
  }

  // Called from studio rAF via _onTick — highlight nearest tick
  tick(pos) {
    if (!this._editMode || !this._beats.length) return;
    const ruler = this._rulerEl; if (!ruler) return;
    const nearest = this._nearestBeatIdx(pos, 0.08);
    ruler.querySelectorAll('.beat-tick.near').forEach(e => e.classList.remove('near'));
    if (nearest >= 0) {
      ruler.querySelector(`.beat-tick[data-idx="${nearest}"]`)?.classList.add('near');
    }
  }

  // ── Private: canvas rendering (display mode) ──────────────────────────────

  _buildCanvas() {
    const ruler = this._rulerEl; if (!ruler) return;
    this._canvas?.remove();
    const c = document.createElement('canvas');
    c.className   = 'beat-grid-canvas';
    c.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:1';
    ruler.style.position = ruler.style.position || 'relative';
    ruler.appendChild(c);
    this._canvas = c;

    this._resizeObs?.disconnect();
    this._resizeObs = new ResizeObserver(() => this._render());
    this._resizeObs.observe(ruler);
  }

  _render() {
    const c   = this._canvas; if (!c) return;
    const pr  = window.devicePixelRatio || 1;
    const w   = c.offsetWidth  || c.parentElement?.offsetWidth  || 800;
    const h   = c.offsetHeight || c.parentElement?.offsetHeight || 28;
    c.width   = w * pr; c.height = h * pr;
    const ctx = c.getContext('2d'); ctx.scale(pr, pr);
    ctx.clearRect(0, 0, w, h);

    const beats = this._beats;
    const dur   = this.State.duration;
    if (!beats.length || !dur) return;

    const barStartSet  = new Set(this._bars.map(b => b.start));
    const barNumAt     = {};
    this._bars.forEach((b, i) => { barNumAt[b.start] = b.bar_number ?? (i + 1); });

    // Auto-detect beats-per-bar if bars array is sparse
    const bpb = this.State.metronomeBeatsPerBar > 0 ? this.State.metronomeBeatsPerBar : 4;

    beats.forEach((t, i) => {
      if (t > dur) return;
      const x = (t / dur) * w;
      // Determine if this is a bar downbeat
      const isBar = barStartSet.has(t) || (i % bpb === 0);
      ctx.strokeStyle = isBar ? 'rgba(244,183,64,0.75)' : 'rgba(255,255,255,0.18)';
      ctx.lineWidth   = isBar ? 1.5 : 0.75;
      ctx.beginPath();
      ctx.moveTo(x, isBar ? 0 : h * 0.45);
      ctx.lineTo(x, h);
      ctx.stroke();

      // Bar number label above downbeat
      if (isBar) {
        const num = barNumAt[t] ?? (Math.floor(i / bpb) + 1);
        ctx.fillStyle = 'rgba(244,183,64,0.9)';
        ctx.font      = `bold ${Math.min(10, h * 0.4)}px var(--font-mono, monospace)`;
        ctx.textAlign = 'center';
        ctx.fillText(String(num), x, h * 0.38);
      }
    });
  }

  // ── Private: DOM ticks (edit mode) ───────────────────────────────────────

  _renderDomTicks() {
    const ruler = this._rulerEl; if (!ruler) return;
    this._clearDomTicks();

    const dur = this.State.duration;
    const bpb = this.State.metronomeBeatsPerBar > 0 ? this.State.metronomeBeatsPerBar : 4;
    const barNumAt = {};
    this._bars.forEach((b, i) => { barNumAt[b.start?.toFixed(3)] = b.bar_number ?? (i + 1); });

    this._beats.forEach((t, i) => {
      const tick = this._makeTick(t, i, bpb, barNumAt, dur);
      ruler.appendChild(tick);
    });

    // Click on ruler empty space → add beat
    ruler.addEventListener('click', this._onRulerClick);
    ruler.addEventListener('contextmenu', e => e.preventDefault());
    this._updateBeatInfo();
  }

  _makeTick(t, i, bpb, barNumAt, dur) {
    const frac   = t / dur;
    const isBar  = (i % bpb === 0) || barNumAt[t?.toFixed(3)] !== undefined;
    const tick   = document.createElement('div');
    tick.className   = `beat-tick beat-tick-dom${isBar ? ' beat-tick-bar' : ''}`;
    tick.style.left  = `${frac * 100}%`;
    tick.dataset.idx = i;
    tick.dataset.t   = t;

    if (isBar) {
      const num = document.createElement('span');
      num.className   = 'beat-bar-num-label';
      num.textContent = barNumAt[t?.toFixed(3)] ?? (Math.floor(i / bpb) + 1);
      tick.appendChild(num);
    }

    // Drag to move
    tick.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return;
      e.stopPropagation();
      this._startTickDrag(e, i, tick);
    });

    // Right-click to delete
    tick.addEventListener('contextmenu', (e) => {
      e.preventDefault(); e.stopPropagation();
      this._deleteBeat(i);
    });

    return tick;
  }

  _onRulerClick = (e) => {
    if (!this._editMode) return;
    // Only add if click was directly on the ruler, not a tick
    if (e.target !== this._rulerEl && !e.target.classList.contains('beat-grid-canvas')) return;
    const ruler = this._rulerEl;
    const rect  = ruler.getBoundingClientRect();
    const frac  = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const t     = frac * this.State.duration;
    this._addBeat(t);
  };

  _startTickDrag(e, idx, el) {
    const ruler = this._rulerEl;
    const rect  = ruler.getBoundingClientRect();
    let lastT   = this._beats[idx];
    el.classList.add('dragging');

    const onMove = (ev) => {
      const frac = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width));
      const t    = frac * this.State.duration;
      this._beats[idx] = t;
      el.style.left     = `${frac * 100}%`;
      el.dataset.t      = t;
      lastT = t;
    };
    const onUp = () => {
      el.classList.remove('dragging');
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup',   onUp);
      this._beats.sort((a, b) => a - b);
      this._dirty = true;
      this._debouncedSave();
      this._renderDomTicks();
      this._updateBeatInfo();
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup',   onUp);
  }

  _addBeat(t) {
    // Insert sorted
    const idx = this._beats.findIndex(b => b > t);
    if (idx === -1) this._beats.push(t);
    else            this._beats.splice(idx, 0, t);
    this._dirty = true;
    this._debouncedSave();
    this._renderDomTicks();
    this._updateBeatInfo();
  }

  _deleteBeat(idx) {
    this._beats.splice(idx, 1);
    this._dirty = true;
    this._debouncedSave();
    this._renderDomTicks();
    this._updateBeatInfo();
  }

  _clearDomTicks() {
    this._rulerEl?.querySelectorAll('.beat-tick-dom').forEach(e => e.remove());
    this._rulerEl?.removeEventListener('click', this._onRulerClick);
  }

  _nearestBeatIdx(pos, windowSec) {
    let best = -1, bestDist = windowSec;
    this._beats.forEach((t, i) => { const d = Math.abs(t - pos); if (d < bestDist) { bestDist = d; best = i; } });
    return best;
  }

  // ── Private: save / reset ────────────────────────────────────────────────

  _debouncedSave() {
    clearTimeout(this._saveTimer);
    this._saveTimer = setTimeout(() => this._save(), 800);
  }

  async _save(userTriggered = false) {
    if (!this._songId || !this._dirty) return;
    try {
      await this.API.patchBeats(this._songId, this._beats, this._bars);
      this._dirty = false;
      this.State.beats = { ...this.State.beats, beats: [...this._beats], bars: [...this._bars] };
      this._showSaveBadge(userTriggered ? 'Saved' : '✓');
      // Update studio ruler
      this.studio._drawRulerBeats();
    } catch (err) {
      this._showSaveBadge('Save failed');
      console.error('[beat-grid] save failed:', err);
    }
  }

  async _reset() {
    if (!this._songId) return;
    if (!confirm('Reset beat grid to auto-detected values?')) return;
    try {
      await this.API.resetBeats(this._songId);
      const fresh = await this.API.getBeats(this._songId);
      this.State.beats = fresh;
      this._beats = [...(fresh?.beats || [])];
      this._bars  = [...(fresh?.bars  || [])];
      this._dirty = false;
      this._renderDomTicks();
      this._render();
      this.studio._drawRulerBeats();
      this._updateBeatInfo();
      this._showSaveBadge('Reset');
    } catch (err) {
      console.error('[beat-grid] reset failed:', err);
    }
  }

  _showSaveBadge(msg) {
    const el = document.getElementById('beatSaveBadge'); if (!el) return;
    el.textContent = msg; el.classList.add('visible');
    setTimeout(() => el.classList.remove('visible'), 1800);
  }

  _updateBeatInfo() {
    const el = document.getElementById('beatGridInfo');
    if (el) el.textContent = `${this._beats.length} beats`;
  }

  _updateToolbar() {
    const toolbar = document.getElementById('beatGridToolbar');
    if (toolbar) toolbar.classList.toggle('hidden', !this._beats.length);
    const saveBtn = document.getElementById('beatSaveBtn');
    if (saveBtn) saveBtn.disabled = !this._dirty;
  }
}
