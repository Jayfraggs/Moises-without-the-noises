/**
 * vu-meters.js — Real-time VU meter system.
 *
 * Two views driven by the same AnalyserNode data:
 *   MINI  — 4px-wide vertical bar inside each mixer row (always visible).
 *   FULL  — tall canvas columns in the collapsible #vuMeterPanel.
 *
 * Peak-hold: each stem tracks its highest recent value. The peak segment
 * lingers for PEAK_HOLD_MS, then falls at PEAK_FALL_DB_PER_SEC dB/s.
 *
 * Usage (wired in app.js after studio construction):
 *   const vu = new VuMeters({ studio });
 *   vu.start();   // begins rAF loop
 *   vu.stop();    // pauses (called on song clear)
 *   vu.rebuild(); // call after new stems are loaded
 */

const PEAK_HOLD_MS      = 1500;
const PEAK_FALL_DB_S    = 24;      // dB per second fall rate
const FLOOR_DB          = -60;
const CLIP_DB           = -0.5;    // anything above this goes red

// Segment colours for the full-panel bars
function segColor(dbFrac) {
  if (dbFrac > 0.90) return '#ff2d2d';   // clip zone
  if (dbFrac > 0.75) return '#f4b740';   // warning zone
  return '#22c55e';                       // normal
}

function rmsDb(analyser) {
  const buf = new Uint8Array(analyser.fftSize);
  analyser.getByteTimeDomainData(buf);
  let sum = 0;
  for (let i = 0; i < buf.length; i++) {
    const s = (buf[i] - 128) / 128;
    sum += s * s;
  }
  const rms = Math.sqrt(sum / buf.length);
  return rms < 1e-7 ? FLOOR_DB : Math.max(FLOOR_DB, 20 * Math.log10(rms));
}

export class VuMeters {
  constructor({ studio }) {
    this.studio  = studio;
    this._rafId  = null;
    this._peaks  = {};   // { [stemName]: { db, heldUntil, fallDb } }
    this._minis  = {};   // { [stemName]: CanvasRenderingContext2D }
    this._fulls  = {};   // { [stemName]: CanvasRenderingContext2D }
    this._lastTs = 0;
    this._panelEl = document.getElementById('vuMeterPanel');
    this._bodyEl  = document.getElementById('vuMeterBody');
  }

  // ── Public ─────────────────────────────────────────────────────────────────

  start() {
    this._stop();
    this._loop();
  }

  stop() { this._stop(); }

  /** Called after new stems load — rebuilds canvases for current stem set. */
  rebuild() {
    this._peaks = {};
    this._minis = {};
    this._fulls = {};
    if (this._bodyEl) this._bodyEl.innerHTML = '';

    const stems = Object.keys(this.studio._stems);
    if (!stems.length) return;

    stems.forEach(name => {
      this._peaks[name] = { db: FLOOR_DB, heldUntil: 0, fallDb: FLOOR_DB };

      // Mini canvas — already in the mixer row from studio._buildMixer
      const mini = document.getElementById(`vu-mini-${name}`);
      if (mini) this._minis[name] = mini.getContext('2d');

      // Full-panel column
      if (this._bodyEl) {
        const col   = document.createElement('div');
        col.className = 'vu-col';
        const label  = document.createElement('span');
        label.className = 'vu-col-label';
        label.textContent = name.replace('_', ' ');
        const canvas = document.createElement('canvas');
        canvas.className = 'vu-full-canvas';
        canvas.id        = `vu-full-${name}`;
        canvas.width     = 20;
        canvas.height    = 160;
        col.appendChild(canvas);
        col.appendChild(label);
        this._bodyEl.appendChild(col);
        this._fulls[name] = canvas.getContext('2d');
      }
    });
  }

  // ── Private: rAF loop ─────────────────────────────────────────────────────

  _loop() {
    const tick = (ts) => {
      this._rafId = requestAnimationFrame(tick);
      const dt = Math.min(0.1, (ts - (this._lastTs || ts)) / 1000);
      this._lastTs = ts;

      const stems = this.studio._stems;
      Object.entries(stems).forEach(([name, stem]) => {
        if (!stem?.analyser) return;

        const db    = rmsDb(stem.analyser);
        const state = this._peaks[name] || (this._peaks[name] = { db: FLOOR_DB, heldUntil: 0, fallDb: FLOOR_DB });

        // Peak-hold
        if (db >= state.fallDb) {
          state.fallDb  = db;
          state.heldUntil = ts + PEAK_HOLD_MS;
        } else if (ts > state.heldUntil) {
          state.fallDb = Math.max(FLOOR_DB, state.fallDb - PEAK_FALL_DB_S * dt);
        }

        const liveF = Math.max(0, (db      - FLOOR_DB) / -FLOOR_DB);
        const peakF = Math.max(0, (state.fallDb - FLOOR_DB) / -FLOOR_DB);

        this._drawMini(name,  liveF, peakF);
        this._drawFull(name,  liveF, peakF);
      });
    };
    this._rafId = requestAnimationFrame(tick);
  }

  _stop() {
    if (this._rafId) { cancelAnimationFrame(this._rafId); this._rafId = null; }
  }

  // ── Drawing: mini (4 × lane-height px vertical bar) ──────────────────────

  _drawMini(name, liveF, peakF) {
    const ctx = this._minis[name]; if (!ctx) return;
    const c   = ctx.canvas;
    const w   = c.width, h = c.height;
    ctx.clearRect(0, 0, w, h);

    // Background
    ctx.fillStyle = 'rgba(255,255,255,0.04)';
    ctx.fillRect(0, 0, w, h);

    // Live bar (bottom → up)
    const barH = Math.round(liveF * h);
    const grad = ctx.createLinearGradient(0, h, 0, 0);
    grad.addColorStop(0,    '#22c55e');
    grad.addColorStop(0.75, '#22c55e');
    grad.addColorStop(0.88, '#f4b740');
    grad.addColorStop(1.0,  '#ff2d2d');
    ctx.fillStyle = grad;
    ctx.fillRect(0, h - barH, w, barH);

    // Peak hold line
    const peakY = Math.round((1 - peakF) * h);
    ctx.fillStyle = peakF > 0.88 ? '#ff2d2d' : '#fff';
    ctx.fillRect(0, peakY, w, 2);
  }

  // ── Drawing: full (20 × 160 px segmented bar) ────────────────────────────

  _drawFull(name, liveF, peakF) {
    const ctx = this._fulls[name]; if (!ctx) return;
    const c   = ctx.canvas;
    const w   = c.width, h = c.height;
    const SEG = 3, GAP = 1, N = Math.floor(h / (SEG + GAP));
    ctx.clearRect(0, 0, w, h);

    for (let i = 0; i < N; i++) {
      const frac = (N - 1 - i) / (N - 1);   // 0 = bottom, 1 = top
      const y    = i * (SEG + GAP);
      const lit  = frac <= liveF;
      if (lit) {
        ctx.fillStyle = segColor(frac);
      } else {
        ctx.fillStyle = 'rgba(255,255,255,0.05)';
      }
      ctx.fillRect(0, y, w, SEG);
    }

    // Peak hold segment
    const peakSeg = Math.round((1 - peakF) * (N - 1));
    const py = peakSeg * (SEG + GAP);
    ctx.fillStyle = peakF > 0.88 ? '#ff2d2d' : 'rgba(255,255,255,0.8)';
    ctx.fillRect(0, py, w, SEG);
  }
}
