/**
 * transport.js — Play/pause/stop/seek/loop/speed/pitch controls.
 */
export class Transport {
  constructor({ State, studio }) {
    this.State  = State;
    this.studio = studio;
  }

  init() {
    const { State } = this;

    // Speed, pitch, metronome controls are always enabled (don't need a track)
    ['t-pitch-up','t-pitch-down','t-pitch-reset',
     't-speed-075','t-speed-1',
     't-metro-vol-btn','t-metro-countin','t-metro-bar',
     't-metro-half','t-metro-one','t-metro-double'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.disabled = false;
    });

    // Speed + pitch visual reset
    const pitchVal = document.getElementById('t-pitch-value');
    if (pitchVal) pitchVal.textContent = '0';

    // Play / pause
    document.getElementById('t-play')?.addEventListener('click', () => {
      if (State.isPlaying) this.studio.pause();
      else                 this.studio.play();
    });

    // Stop
    document.getElementById('t-stop')?.addEventListener('click', () => {
      this.studio.stop();
    });

    // Loop
    const loopBtn   = document.getElementById('t-loop');
    const loopStart = document.getElementById('t-loop-start');
    const loopEnd   = document.getElementById('t-loop-end');

    loopBtn?.addEventListener('click', () => {
      State.loopEnabled = !State.loopEnabled;
      loopBtn.classList.toggle('active', State.loopEnabled);
      loopBtn.setAttribute('aria-pressed', State.loopEnabled ? 'true' : 'false');
      if (State.loopEnabled && State.loopEnd === 0 && State.duration > 0) {
        State.loopStart = State.duration * 0.25;
        State.loopEnd   = State.duration * 0.5;
        if (loopStart) loopStart.value = this._fmtMs(State.loopStart);
        if (loopEnd)   loopEnd.value   = this._fmtMs(State.loopEnd);
      }
    });

    loopStart?.addEventListener('change', () => {
      const v = parseFloat(loopStart.value);
      if (isFinite(v)) State.loopStart = v;
    });
    loopEnd?.addEventListener('change', () => {
      const v = parseFloat(loopEnd.value);
      if (isFinite(v)) State.loopEnd = v;
    });

    // Speed buttons
    document.querySelectorAll('.speed-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const speed = parseFloat(btn.dataset.speed);
        document.querySelectorAll('.speed-btn').forEach(b => {
          b.classList.remove('active');
          b.setAttribute('aria-checked', 'false');
        });
        btn.classList.add('active');
        btn.setAttribute('aria-checked', 'true');
        State.playbackRate = speed;
        // Mid-play restart: capture position first, then restart
        if (State.isPlaying) {
          this.studio.restartAtCurrentPosition();
        }
      });
    });

    // Pitch (semitone offset — written to State for future SoundTouch integration)
    let semitones = 0;
    const pitchValEl = document.getElementById('t-pitch-value');
    document.getElementById('t-pitch-up')?.addEventListener('click', () => {
      semitones = Math.min(12, semitones + 1);
      if (pitchValEl) pitchValEl.textContent = semitones > 0 ? `+${semitones}` : String(semitones);
      State.pitchSemitones = semitones;
    });
    document.getElementById('t-pitch-down')?.addEventListener('click', () => {
      semitones = Math.max(-12, semitones - 1);
      if (pitchValEl) pitchValEl.textContent = semitones > 0 ? `+${semitones}` : String(semitones);
      State.pitchSemitones = semitones;
    });
    document.getElementById('t-pitch-reset')?.addEventListener('click', () => {
      semitones = 0;
      if (pitchValEl) pitchValEl.textContent = '0';
      State.pitchSemitones = 0;
    });

    // Metronome on/off
    const metroBtn = document.getElementById('t-metro');
    metroBtn?.addEventListener('click', () => {
      State.metronomeEnabled = !State.metronomeEnabled;
      metroBtn.setAttribute('aria-pressed', State.metronomeEnabled ? 'true' : 'false');
      metroBtn.classList.toggle('active', State.metronomeEnabled);
      // Tell studio to start or stop the scheduler
      this.studio.onMetronomeToggle();
    });

    // Metro volume
    const metroVol = document.getElementById('t-metro-vol');
    const metroLbl = document.getElementById('t-metro-vol-label');
    metroVol?.addEventListener('input', () => {
      State.metronomeVolume = parseFloat(metroVol.value);
      if (metroLbl) metroLbl.textContent = `${Math.round(State.metronomeVolume * 100)}%`;
      // Live update the gain node if it exists
      if (this.studio._metro?.gainNode) {
        this.studio._metro.gainNode.gain.value = State.metronomeVolume;
      }
    });

    // Metro time-signature selector
    const metroBar = document.getElementById('t-metro-bar');
    metroBar?.addEventListener('change', () => {
      State.metronomeBeatsPerBar = parseInt(metroBar.value, 10);
    });

    // Count-in selector
    const metroCountIn = document.getElementById('t-metro-countin');
    metroCountIn?.addEventListener('change', () => {
      State.metronomeCountIn = parseInt(metroCountIn.value, 10);
    });

    // Metro multiplier
    ['t-metro-half','t-metro-one','t-metro-double'].forEach(id => {
      document.getElementById(id)?.addEventListener('click', () => {
        document.querySelectorAll('.metro-mult-btn').forEach(b => {
          b.classList.remove('active');
          b.setAttribute('aria-checked', 'false');
        });
        const btn = document.getElementById(id);
        btn?.classList.add('active');
        btn?.setAttribute('aria-checked', 'true');
        State.metronomeMultiplier = id.includes('half') ? 0.5 : id.includes('double') ? 2.0 : 1.0;
        // Restart scheduler if currently running to apply new multiplier
        if (State.isPlaying && State.metronomeEnabled) {
          this.studio.onMetronomeToggle();
          this.studio.onMetronomeToggle();
        }
      });
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      const tag = document.activeElement?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (e.key === ' ' || e.code === 'Space') {
        e.preventDefault();
        if (State.isPlaying) this.studio.pause();
        else this.studio.play();
      }
      if (e.key === 'l' || e.key === 'L') {
        loopBtn?.click();
      }
      if (e.key === 'k' || e.key === 'K') {
        metroBtn?.click();
      }
    });
  }

  _fmtMs(s) {
    const total = Math.round(s * 1000);
    const sec   = Math.floor(total / 1000);
    const ms    = total % 1000;
    return `${sec.toString().padStart(2,'0')}.${ms.toString().padStart(3,'0')}`;
  }
}
