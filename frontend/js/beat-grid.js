/**
 * beat-grid.js — Beat grid editor.
 *
 * Two modes share ONE canvas:
 *
 *   DISPLAY — canvas overlay on the ruler. Draws beat ticks + bar numbers.
 *             Pointer events are disabled (pass-through).
 *
 *   EDIT    — same canvas becomes interactive:
 *               • Left-click on empty space → add beat at that position.
 *               • Left-drag an existing beat tick → move it.
 *               • Right-click a beat tick → delete it.
 *             Changes are debounce-saved to PATCH /beats.
 *
 * The previous implementation created one DOM element per beat, which
 * becomes sluggish on dense grids (200+ beats). This version draws
 * everything on canvas and uses pointer coordinates to hit-test beats,
 * keeping interaction at O(n) but with zero DOM overhead.
 *
 * Usage (wired in app.js — unchanged public API):
 *   const grid = new BeatGrid({ State, API, studio });
 *   grid.init();          // bind toolbar buttons
 *   grid.loadSong(id);    // called after studio.loadSong
 *   grid.clear();         // called before next loadSong
 */
export class BeatGrid {
  constructor({ State, API, studio }) {
    this.State  = State;
    this.API    = API;
    this.studio = studio;

    this._editMode  = false;
    this._beats     = [];   // local mutable copy (seconds)
    this._bars      = [];
    this._saveTimer = null;
    this._dirty     = false;
    this._songId    = null;

    // Canvas
    this._rulerEl   = document.getElementById('ruler-time');
    this._canvas    = null;
    this._ctx       = null;
    this._resizeObs = null;

    // Drag state
    this._drag = null;   // { idx, startX, origT } | null

    // Hit-test geometry (updated on each render)
    this._tickRects = [];   // [{ x, idx }] for hit-testing (each ~8px wide)
    this._TICK_HIT  = 8;    // px half-width for hit-test
  }

  // ── Public ─────────────────────────────────────────────────────────────────

  init() {
    document.getElementById('beatEditToggleBtn')?.addEventListener('click', () => this.toggleEditMode());
    document.getElementById('beatResetBtn')?.addEventListener('click',      () => this._reset());
    document.getElementById('beatSaveBtn')?.addEventListener('click',       () => this._save(true));
  }

  loadSong(songId) {
    this._songId   = songId;
    this._beats    = [...(this.State.beats?.beats || [])];
    this._bars     = [...(this.State.beats?.bars  || [])];
    this._dirty    = false;
    this._editMode = false;

    this._buildCanvas();
    this._render();
    this._updateToolbar();
  }

  clear() {
    this._beats    = [];
    this._bars     = [];
    this._dirty    = false;
    this._editMode = false;
    this._drag     = null;
    this._songId   = null;

    this._resizeObs?.disconnect();
    this._resizeObs = null;

    if (this._canvas) {
      this._canvas.removeEventListener('pointerdown',  this._onPointerDown);
      this._canvas.removeEventListener('pointermove',  this._onPointerMove);
      this._canvas.removeEventListener('pointerup',    this._onPointerUp);
      this._canvas.removeEventListener('pointercancel',this._onPointerUp);
      this._canvas.removeEventListener('contextmenu',  this._onContextMenu);
      this._canvas.remove();
      this._canvas = null;
      this._ctx    = null;
    }

    this._updateToolbar();
  }

  toggleEditMode() {
    this._editMode = !this._editMode;
    this.State.beatEditMode = this._editMode;

    document.getElementById('beatEditToggleBtn')?.classList.toggle('active', this._editMode);
    document.getElementById('beatGridToolbar')?.classList.toggle('edit-active', this._editMode);

    // Switch pointer-events on the canvas
    if (this._canvas) {
      this._canvas.style.pointerEvents = this._editMode ? 'auto' : 'none';
      this._canvas.style.cursor = this._editMode ? 'crosshair' : 'default';
    }

    this._render();
    this._updateToolbar();
  }

  /** Called from studio rAF — highlight nearest beat in edit mode. */
  tick(pos) {
    if (!this._editMode || !this._beats.length) return;
    // Just re-render; the playhead highlight is drawn in _render.
    this._nearestPlayheadPos = pos;
    this._render();
  }

  // ── Private: canvas setup ─────────────────────────────────────────────────

  _buildCanvas() {
    const ruler = this._rulerEl;
    if (!ruler) return;

    if (this._canvas) {
      this._canvas.removeEventListener('pointerdown',   this._onPointerDown);
      this._canvas.removeEventListener('pointermove',   this._onPointerMove);
      this._canvas.removeEventListener('pointerup',     this._onPointerUp);
      this._canvas.removeEventListener('pointercancel', this._onPointerUp);
      this._canvas.removeEventListener('contextmenu',   this._onContextMenu);
      this._canvas.remove();
    }

    const c = document.createElement('canvas');
    c.className = 'beat-grid-canvas';
    c.style.cssText = [
      'position:absolute', 'top:0', 'left:0',
      'width:100%', 'height:100%',
      'pointer-events:none',   // starts in display mode
      'z-index:2',
      'touch-action:none',
    ].join(';');
    ruler.style.position = ruler.style.position || 'relative';
    ruler.appendChild(c);

    this._canvas = c;
    this._ctx    = c.getContext('2d');

    // Pointer events (only active in edit mode)
    c.addEventListener('pointerdown',   this._onPointerDown);
    c.addEventListener('pointermove',   this._onPointerMove);
    c.addEventListener('pointerup',     this._onPointerUp);
    c.addEventListener('pointercancel', this._onPointerUp);
    c.addEventListener('contextmenu',   this._onContextMenu);

    this._resizeObs?.disconnect();
    this._resizeObs = new ResizeObserver(() => this._render());
    this._resizeObs.observe(ruler);
  }

  // ── Private: canvas rendering ─────────────────────────────────────────────

  _render() {
    const c = this._canvas;
    if (!c) return;

    const pr  = window.devicePixelRatio || 1;
    const w   = c.offsetWidth  || c.parentElement?.offsetWidth  || 800;
    const h   = c.offsetHeight || c.parentElement?.offsetHeight || 28;
    c.width   = w * pr;
    c.height  = h * pr;

    const ctx = this._ctx;
    ctx.setTransform(pr, 0, 0, pr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const beats = this._beats;
    const dur   = this.State.duration;
    if (!beats.length || !dur) return;

    const bpb = (this.State.metronomeBeatsPerBar > 0) ? this.State.metronomeBeatsPerBar : 4;
    const barNumAt = {};
    const barStartSet = new Set();
    this._bars.forEach((b, i) => {
      barStartSet.add(b.start);
      barNumAt[b.start] = b.bar_number ?? (i + 1);
    });

    // Determine which beat is being dragged (draw it differently)
    const dragIdx = this._drag?.idx ?? -1;

    // Reset hit rects
    this._tickRects = [];

    beats.forEach((t, i) => {
      if (t > dur) return;
      const x      = (t / dur) * w;
      const isBar  = barStartSet.has(t) || (i % bpb === 0);
      const isDrag = (i === dragIdx);

      // Colour: dragged=accent, bar=gold, beat=dim white
      if (isDrag) {
        ctx.strokeStyle = 'rgba(80,200,255,0.95)';
        ctx.lineWidth   = 2;
      } else if (isBar) {
        ctx.strokeStyle = 'rgba(244,183,64,0.80)';
        ctx.lineWidth   = 1.5;
      } else {
        ctx.strokeStyle = this._editMode ? 'rgba(255,255,255,0.30)' : 'rgba(255,255,255,0.18)';
        ctx.lineWidth   = 0.75;
      }

      const topY = isBar ? 0 : h * 0.45;
      ctx.beginPath();
      ctx.moveTo(x, topY);
      ctx.lineTo(x, h);
      ctx.stroke();

      // Bar number label
      if (isBar) {
        const num = barNumAt[t] ?? (Math.floor(i / bpb) + 1);
        ctx.fillStyle = isDrag ? 'rgba(80,200,255,0.95)' : 'rgba(244,183,64,0.90)';
        ctx.font      = `bold ${Math.min(10, h * 0.4)}px var(--font-mono, monospace)`;
        ctx.textAlign = 'center';
        ctx.fillText(String(num), x, h * 0.38);
      }

      // Edit mode: draw a small grab handle circle at midpoint
      if (this._editMode) {
        const cy = h * 0.75;
        ctx.beginPath();
        ctx.arc(x, cy, isDrag ? 5 : 3.5, 0, Math.PI * 2);
        ctx.fillStyle = isDrag ? 'rgba(80,200,255,0.95)' : (isBar ? 'rgba(244,183,64,0.80)' : 'rgba(255,255,255,0.45)');
        ctx.fill();
      }

      // Record hit rect for pointer interaction
      this._tickRects.push({ x, idx: i });
    });

    // Edit-mode cursor guide line (nearest beat highlight)
    if (this._editMode && this._cursorX !== undefined) {
      const hovered = this._hitTest(this._cursorX);
      if (hovered >= 0) {
        const hx = (beats[hovered] / dur) * w;
        ctx.strokeStyle = 'rgba(80,200,255,0.5)';
        ctx.lineWidth   = 1;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(hx, 0);
        ctx.lineTo(hx, h);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }
  }

  // ── Private: pointer interaction ──────────────────────────────────────────

  /** Returns index of the beat nearest to clientX, or -1 if none within _TICK_HIT px. */
  _hitTest(clientX) {
    const c = this._canvas;
    if (!c) return -1;
    const rect = c.getBoundingClientRect();
    const x = clientX - rect.left;
    let best = -1, bestDist = this._TICK_HIT;
    for (const { x: tx, idx } of this._tickRects) {
      const d = Math.abs(tx - x);
      if (d < bestDist) { bestDist = d; best = idx; }
    }
    return best;
  }

  _canvasX(clientX) {
    const c = this._canvas;
    if (!c) return 0;
    return clientX - c.getBoundingClientRect().left;
  }

  _xToTime(clientX) {
    const c = this._canvas;
    if (!c) return 0;
    const rect = c.getBoundingClientRect();
    const frac = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    return frac * (this.State.duration || 0);
  }

  _onPointerDown = (e) => {
    if (!this._editMode) return;
    const hit = this._hitTest(e.clientX);

    if (e.button === 0 && hit >= 0) {
      // Start dragging an existing beat
      this._drag = { idx: hit, startX: e.clientX, origT: this._beats[hit] };
      this._canvas.setPointerCapture(e.pointerId);
      this._canvas.style.cursor = 'ew-resize';
      e.preventDefault();
    } else if (e.button === 0 && hit < 0) {
      // Add a new beat at click position
      const t = this._xToTime(e.clientX);
      this._addBeat(t);
    }
    // right-click is handled by contextmenu event
  };

  _onPointerMove = (e) => {
    if (!this._editMode) return;
    this._cursorX = e.clientX;

    if (this._drag) {
      const t = this._xToTime(e.clientX);
      this._beats[this._drag.idx] = Math.max(0, Math.min(this.State.duration || 0, t));
    }

    this._render();
  };

  _onPointerUp = (e) => {
    if (!this._editMode) return;
    if (this._drag) {
      // Re-sort beats (dragging can reorder them)
      this._beats.sort((a, b) => a - b);
      this._drag = null;
      this._dirty = true;
      this._canvas.style.cursor = 'crosshair';
      this._debouncedSave();
      this._render();
      this._updateBeatInfo();
    }
  };

  _onContextMenu = (e) => {
    if (!this._editMode) return;
    e.preventDefault();
    const hit = this._hitTest(e.clientX);
    if (hit >= 0) this._deleteBeat(hit);
  };

  // ── Private: beat mutations ───────────────────────────────────────────────

  _addBeat(t) {
    const idx = this._beats.findIndex(b => b > t);
    if (idx === -1) this._beats.push(t);
    else            this._beats.splice(idx, 0, t);
    this._dirty = true;
    this._debouncedSave();
    this._render();
    this._updateBeatInfo();
  }

  _deleteBeat(idx) {
    this._beats.splice(idx, 1);
    this._dirty = true;
    this._debouncedSave();
    this._render();
    this._updateBeatInfo();
  }

  // ── Private: save / reset ─────────────────────────────────────────────────

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
      this.studio._drawRulerBeats?.();
    } catch (err) {
      this._showSaveBadge('Save failed');
      console.error('[beat-grid] save failed:', err);
    }
    this._updateToolbar();
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
      this._drag  = null;
      this._render();
      this.studio._drawRulerBeats?.();
      this._updateBeatInfo();
      this._showSaveBadge('Reset');
    } catch (err) {
      console.error('[beat-grid] reset failed:', err);
    }
    this._updateToolbar();
  }

  // ── Private: UI helpers ───────────────────────────────────────────────────

  _showSaveBadge(msg) {
    const el = document.getElementById('beatSaveBadge');
    if (!el) return;
    el.textContent = msg;
    el.classList.add('visible');
    setTimeout(() => el.classList.remove('visible'), 1800);
  }

  _updateBeatInfo() {
    const el = document.getElementById('beatGridInfo');
    if (el) el.textContent = `${this._beats.length} beats`;
  }

  _updateToolbar() {
    const toolbar  = document.getElementById('beatGridToolbar');
    const saveBtn  = document.getElementById('beatSaveBtn');
    if (toolbar) toolbar.classList.toggle('hidden', !this._beats.length);
    if (saveBtn) saveBtn.disabled = !this._dirty;
  }
}
