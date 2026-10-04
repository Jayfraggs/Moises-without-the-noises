/**
 * transport.js — Play/pause/stop/loop/speed/pitch/metronome controls.
 * Scrub bar drag is handled inside studio.js (_initScrub).
 */
export class Transport {
  constructor({ State, studio }) {
    this.State  = State;
    this.studio = studio;
  }

  init() {
    const { State } = this;

    // Pitch display reset
    const pitchValEl = document.getElementById('t-pitch-value');
    if (pitchValEl) pitchValEl.textContent = '0';

    // ── Playback ──────────────────────────────────────────────────────────────
    document.getElementById('t-play')?.addEventListener('click', () => {
      if (State.isPlaying) this.studio.pause();
      else                 this.studio.play();
    });

    document.getElementById('t-stop')?.addEventListener('click', () => this.studio.stop());

    // ── Loop ──────────────────────────────────────────────────────────────────
    const loopBtn   = document.getElementById('t-loop');
    const loopStart = document.getElementById('t-loop-start');
    const loopEnd   = document.getElementById('t-loop-end');

    loopBtn?.addEventListener('click', () => {
      State.loopEnabled = !State.loopEnabled;
      loopBtn.classList.toggle('active', State.loopEnabled);
      loopBtn.setAttribute('aria-pressed', State.loopEnabled);
      if (State.loopEnabled && State.loopEnd === 0 && State.duration > 0) {
        State.loopStart = State.duration * 0.25;
        State.loopEnd   = State.duration * 0.5;
        if (loopStart) loopStart.value = _fmtMs(State.loopStart);
        if (loopEnd)   loopEnd.value   = _fmtMs(State.loopEnd);
      }
    });

    loopStart?.addEventListener('change', () => {
      const v = parseFloat(loopStart.value); if (isFinite(v)) State.loopStart = v;
    });
    loopEnd?.addEventListener('change', () => {
      const v = parseFloat(loopEnd.value); if (isFinite(v)) State.loopEnd = v;
    });

    // ── Speed ─────────────────────────────────────────────────────────────────
    document.querySelectorAll('.speed-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const speed = parseFloat(btn.dataset.speed);
        document.querySelectorAll('.speed-btn').forEach(b => {
          b.classList.remove('active'); b.setAttribute('aria-checked', 'false');
        });
        btn.classList.add('active'); btn.setAttribute('aria-checked', 'true');
        State.playbackRate = speed;
        if (State.isPlaying) this.studio.restartAtCurrentPosition();
      });
    });

    // ── Pitch ─────────────────────────────────────────────────────────────────
    let semitones = 0;

    document.getElementById('t-pitch-up')?.addEventListener('click', () => {
      semitones = Math.min(12, semitones + 1);
      if (pitchValEl) pitchValEl.textContent = semitones > 0 ? `+${semitones}` : `${semitones}`;
      State.pitchSemitones = semitones;
    });
    document.getElementById('t-pitch-down')?.addEventListener('click', () => {
      semitones = Math.max(-12, semitones - 1);
      if (pitchValEl) pitchValEl.textContent = semitones > 0 ? `+${semitones}` : `${semitones}`;
      State.pitchSemitones = semitones;
    });
    document.getElementById('t-pitch-reset')?.addEventListener('click', () => {
      semitones = 0;
      if (pitchValEl) pitchValEl.textContent = '0';
      State.pitchSemitones = 0;
    });

    // ── Metronome ─────────────────────────────────────────────────────────────
    const metroBtn = document.getElementById('t-metro');
    metroBtn?.addEventListener('click', () => {
      State.metronomeEnabled = !State.metronomeEnabled;
      metroBtn.setAttribute('aria-pressed', State.metronomeEnabled);
      metroBtn.classList.toggle('active', State.metronomeEnabled);
      this.studio.onMetronomeToggle();
    });

    const metroVol = document.getElementById('t-metro-vol');
    const metroLbl = document.getElementById('t-metro-vol-label');
    metroVol?.addEventListener('input', () => {
      State.metronomeVolume = parseFloat(metroVol.value);
      if (metroLbl) metroLbl.textContent = `${Math.round(State.metronomeVolume * 100)}%`;
      if (this.studio._metro?.gainNode) this.studio._metro.gainNode.gain.value = State.metronomeVolume;
    });

    document.getElementById('t-metro-bar')?.addEventListener('change', (e) => {
      State.metronomeBeatsPerBar = parseInt(e.target.value, 10);
    });
    document.getElementById('t-metro-countin')?.addEventListener('change', (e) => {
      State.metronomeCountIn = parseInt(e.target.value, 10);
    });

    ['t-metro-half','t-metro-one','t-metro-double'].forEach(id => {
      document.getElementById(id)?.addEventListener('click', () => {
        document.querySelectorAll('.metro-mult-btn').forEach(b => {
          b.classList.remove('active'); b.setAttribute('aria-checked', 'false');
        });
        const btn = document.getElementById(id);
        btn?.classList.add('active'); btn?.setAttribute('aria-checked', 'true');
        State.metronomeMultiplier = id.includes('half') ? 0.5 : id.includes('double') ? 2.0 : 1.0;
        if (State.isPlaying && State.metronomeEnabled) {
          this.studio.onMetronomeToggle(); // restart scheduler with new grid
        }
      });
    });

    // ── Keyboard shortcuts ────────────────────────────────────────────────────
    document.addEventListener('keydown', (e) => {
      const tag = document.activeElement?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (e.code === 'Space') {
        e.preventDefault();
        if (State.isPlaying) this.studio.pause(); else this.studio.play();
      }
      if (e.key === 'l' || e.key === 'L') loopBtn?.click();
      if (e.key === 'k' || e.key === 'K') metroBtn?.click();
      if (e.key === 'ArrowLeft'  && e.shiftKey) this.studio.seek(Math.max(0, State.currentTime - 5));
      if (e.key === 'ArrowRight' && e.shiftKey) this.studio.seek(Math.min(State.duration, State.currentTime + 5));
    });
  }
}

function _fmtMs(s) {
  const tot = Math.round(s * 1000);
  return `${Math.floor(tot/1000).toString().padStart(2,'0')}.${(tot%1000).toString().padStart(3,'0')}`;
}
