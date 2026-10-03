/**
 * studio.js — Loads a song into the DAW view.
 *
 * Responsibilities:
 *   - Fetch manifest, beats, key, peaks from the backend
 *   - Build the Web Audio graph (one GainNode per stem)
 *   - Draw waveforms using the peaks data
 *   - Wire M/S buttons in the mixer column
 *   - Populate analysis cards + stem presence row
 *   - Expose play/pause/seek/stop to transport.js
 *   - Expose export helpers to app.js
 *   - Run Web Audio lookahead click-track scheduler
 */

const STEM_COLORS = {
  vocals:         '#e85f6f',
  drums:          '#e89048',
  bass:           '#e8b848',
  guitar:         '#88d878',
  piano:          '#b88fe0',
  other:          '#88a8c8',
  original:       '#a8b0bd',
  lead_vocals:    '#e8748a',
  backing_vocals: '#c98fe0',
};

const STEM_ICONS = {
  vocals: `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><path d="M12 19v3"/></svg>`,
  drums:  `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><ellipse cx="12" cy="9" rx="9" ry="4"/><path d="M3 9v6c0 2.2 4 4 9 4s9-1.8 9-4V9"/><path d="M3 15c0 2.2 4 4 9 4s9-1.8 9-4"/></svg>`,
  bass:   `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path d="M16.5 3h4v5h-3"/><path d="M17.5 5.5 9.8 13.2"/><path d="M10 13c1.6 2.2 1.1 5.1-1.2 6.5-2.1 1.3-5 .5-6-1.6-.9-1.9-.1-4.1 1.8-5 .9-.4 1.8-.4 2.8-.1.1-1.1.6-2.1 1.6-2.6 1.2-.6 2.6-.1 3.2 1.1"/></svg>`,
  guitar: `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path d="M16 4.5 20 2l2 2-2.5 4"/><path d="M18.2 5.8 10.2 13.8"/><circle cx="7" cy="16.4" r="1.4"/><circle cx="7" cy="16.4" r="3.6"/></svg>`,
  piano:  `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M7 5v8M12 5v8M17 5v8"/><path d="M9.5 5v5M14.5 5v5"/></svg>`,
  other:  `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path d="M4 13v-2"/><path d="M8 17V7"/><path d="M12 21V3"/><path d="M16 17V7"/><path d="M20 13v-2"/></svg>`,
  original: `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`,
  lead_vocals:    `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><path d="M12 19v3"/></svg>`,
  backing_vocals: `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><path d="M12 19v3"/></svg>`,
};

// ── Click-track voice constants (must match click_render.py exactly) ──────────
const CLICK_FREQ   = 1000.0;
const GROUP_FREQ   = 1225.0;
const ACCENT_FREQ  = 1500.0;
const CLICK_DECAY  = 0.035;   // seconds
const CLICK_ATTACK = 0.001;   // seconds
const CLICK_PEAK   = 0.7;
const GROUP_PEAK   = 0.85;
const ACCENT_PEAK  = 1.0;

function fmtDur(s) {
  if (!s || !isFinite(s)) return '—';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60).toString().padStart(2, '0');
  return `${m}:${sec}`;
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val ?? '—';
}

function setClass(id, cls, on) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle(cls, on);
}

export class Studio {
  constructor({ State, API }) {
    this.State = State;
    this.API   = API;

    // Audio state
    this._ctx         = null;    // AudioContext
    this._masterGain  = null;    // GainNode
    this._stems       = {};      // { [name]: { buffer, source, gainNode, analyser } }
    this._startOffset = 0;       // AudioContext.currentTime when last play() was called
    this._posOffset   = 0;       // track position at last play()
    this._rafId       = null;

    // Click-track scheduler state
    this._metro = {
      gainNode:        null,    // GainNode → ctx.destination
      nextBeatIdx:     0,
      nextBeatTime:    0,       // AudioContext time of next scheduled click
      lookaheadMs:     100,
      scheduleAheadSec:0.15,
      timerId:         null,
    };

    // Export state
    this._exportFmt   = 'wav';
    this._exportClick = false;

    // DOM
    this._loadingEl   = document.getElementById('waveLoadingOverlay');
    this._phraseEl    = document.getElementById('waveLoadingPhrase');
    this._jobEl       = document.getElementById('job');
    this._errorEl     = document.getElementById('error');
    this._mixerEl     = document.getElementById('mixer');
    this._container   = document.getElementById('multitrack-container');
    this._footerWave  = document.getElementById('footer-waveform');
    this._scrubFill   = document.getElementById('footer-scrub-fill');
    this._nowPlaying  = document.getElementById('nowPlayingPanel');

    this._bindExportUI();
  }

  // ── Public: load a song ───────────────────────────────────────────────────

  async loadSong(songId) {
    const { State, API } = this;

    this._stopAudio();
    this._stopMetronome();
    this._clearWaveforms();
    this._showLoading('Loading song…');
    this._showError(null);
    document.getElementById('app')?.classList.add('no-track');
    document.getElementById('app')?.classList.remove('has-track');

    State.songId   = songId;
    State.manifest = null;
    State.beats    = null;
    State.keyInfo  = null;
    State.isPlaying = false;
    State.currentTime = 0;
    State.mixer    = {};

    // Reset analysis cards
    this._resetAnalysis();

    try {
      // 1. Manifest
      this._setPhrase('Reading manifest…');
      const manifest = await API.getManifest(songId);
      State.manifest = manifest;

      // Update now-playing header
      this._updateNowPlaying(manifest);

      const stems = manifest.stems || [];

      // 2. Beats + key + stem presence in parallel
      this._setPhrase('Fetching analysis…');
      const [beats, keyInfo, presence] = await Promise.allSettled([
        API.getBeats(songId),
        API.getKey(songId),
        API.getStemPresence(songId),
      ]).then(r => r.map(v => v.status === 'fulfilled' ? v.value : null));

      State.beats   = beats;
      State.keyInfo = keyInfo;

      this._populateAnalysis(manifest, beats, keyInfo, presence);

      // 3. Peaks (waveform display data)
      this._setPhrase('Loading waveforms…');
      const allPeaks = await API.getAllPeaks(songId).catch(() => null);

      // 4. Load audio buffers for each stem
      this._setPhrase('Decoding audio…');
      this._initAudioContext();

      const results = await Promise.allSettled(
        stems.map(name => this._loadStemBuffer(songId, name))
      );

      let loadedCount = 0;
      results.forEach((r, i) => {
        if (r.status === 'fulfilled' && r.value) loadedCount++;
        else console.warn(`[studio] stem ${stems[i]} failed:`, r.reason);
      });

      if (loadedCount === 0) throw new Error('No stems could be decoded');

      // 5. Build mixer
      this._buildMixer(stems, allPeaks);

      // 6. Draw waveforms
      this._drawAllWaveforms(stems, allPeaks);
      this._drawFooterWaveform(stems, allPeaks);

      // 7. Enable transport
      State.duration = this._longestStemDuration();
      this._enableTransport();

      this._hideLoading();
      document.getElementById('app')?.classList.remove('no-track');
      document.getElementById('app')?.classList.add('has-track');

    } catch (err) {
      console.error('[studio] loadSong failed:', err);
      this._hideLoading();
      this._showError(`Failed to load song: ${err.message}`);
    }
  }

  // ── Public: playback controls (called by transport.js) ────────────────────

  play() {
    if (this.State.isPlaying) return;
    if (!this._ctx || Object.keys(this._stems).length === 0) return;
    this.State.isPlaying = true;

    const countInBars = this.State.metronomeCountIn || 0;

    if (countInBars > 0 && this.State.beats?.beats?.length > 1) {
      const leadIn = this._computeCountInDuration(countInBars);
      this._startPlaybackWithDelay(this.State.currentTime, leadIn);
      if (this.State.metronomeEnabled) this._startMetronomeCountIn(countInBars, leadIn);
    } else {
      this._startPlayback(this.State.currentTime);
      if (this.State.metronomeEnabled) this._startMetronome();
    }

    this._startRaf();
  }

  pause() {
    if (!this.State.isPlaying) return;
    this.State.currentTime = this._getPosition();
    this.State.isPlaying = false;
    this._stopSources();
    this._stopRaf();
    this._stopMetronome();
  }

  stop() {
    this.State.currentTime = 0;
    this.State.isPlaying = false;
    this._stopSources();
    this._stopRaf();
    this._stopMetronome();
    this._updatePlayhead(0);
  }

  seek(time) {
    const wasPlaying = this.State.isPlaying;
    if (wasPlaying) {
      this._stopSources();
      this._stopMetronome();
    }
    this.State.currentTime = Math.max(0, Math.min(time, this.State.duration));
    if (wasPlaying) {
      this._startPlayback(this.State.currentTime);
      if (this.State.metronomeEnabled) this._startMetronome();
    }
    this._updatePlayhead(this.State.currentTime);
  }

  getPosition() { return this._getPosition(); }
  getDuration()  { return this.State.duration; }

  /** Called by transport.js when speed changes while playing. */
  restartAtCurrentPosition() {
    const pos = this._getPosition();
    this._stopSources();
    this._stopMetronome();
    this.State.currentTime = pos;
    this._startPlayback(pos);
    if (this.State.metronomeEnabled) this._startMetronome();
  }

  setStemVolume(name, vol) {
    const s = this._stems[name];
    if (s?.gainNode) s.gainNode.gain.value = vol;
    if (!this.State.mixer[name]) this.State.mixer[name] = { volume: 1, muted: false, soloed: false };
    this.State.mixer[name].volume = vol;
  }

  setStemMuted(name, muted) {
    const s = this._stems[name];
    if (!this.State.mixer[name]) this.State.mixer[name] = { volume: 1, muted: false, soloed: false };
    this.State.mixer[name].muted = muted;
    this._applyMuteState();
  }

  setStemSoloed(name, soloed) {
    if (!this.State.mixer[name]) this.State.mixer[name] = { volume: 1, muted: false, soloed: false };
    this.State.mixer[name].soloed = soloed;
    this._applyMuteState();
  }

  /** Called by transport.js when metronome toggle changes while playing. */
  onMetronomeToggle() {
    if (this.State.metronomeEnabled && this.State.isPlaying) {
      this._startMetronome();
    } else {
      this._stopMetronome();
    }
  }

  clearStudio() {
    this._stopAudio();
    this._stopMetronome();
    this._clearWaveforms();
    this._resetAnalysis();
    if (this._mixerEl) this._mixerEl.innerHTML = '';
    document.getElementById('app')?.classList.add('no-track');
    document.getElementById('app')?.classList.remove('has-track');
    this.State.songId = null;
    this.State.manifest = null;
  }

  // ── Export ────────────────────────────────────────────────────────────────

  exportMix() {
    const { State, API } = this;
    if (!State.songId || !State.manifest) return;
    const stems = State.manifest.stems || [];
    const gains = stems.map(s => State.mixer[s]?.volume ?? 1.0);
    const url = API.mixdownUrl(State.songId, {
      stems, gains, ext: this._exportFmt, click: this._exportClick,
    });
    API.triggerDownload(url, `${State.songId}_mix.${this._exportFmt}`);
  }

  exportStems() {
    const { State, API } = this;
    if (!State.songId) return;
    const url = API.stemsZipUrl(State.songId, this._exportFmt === 'wav' ? 'wav' : 'mp3');
    API.triggerDownload(url, `${State.songId}_stems.zip`);
  }

  // ── Private: audio ────────────────────────────────────────────────────────

  _initAudioContext() {
    if (this._ctx) return;
    this._ctx = new (window.AudioContext || window.webkitAudioContext)();
    this._masterGain = this._ctx.createGain();
    this._masterGain.gain.value = 1.0;
    this._masterGain.connect(this._ctx.destination);

    // Dedicated gain node for the metronome (independent of stem faders)
    this._metro.gainNode = this._ctx.createGain();
    this._metro.gainNode.gain.value = this.State.metronomeVolume;
    this._metro.gainNode.connect(this._ctx.destination);
  }

  async _loadStemBuffer(songId, name) {
    const url  = this.API.stemUrl(songId, name);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`${resp.status} for ${name}`);
    const buf  = await resp.arrayBuffer();
    const decoded = await this._ctx.decodeAudioData(buf);

    if (!this.State.mixer[name]) {
      this.State.mixer[name] = { volume: 1.0, muted: false, soloed: false };
    }
    const gainNode = this._ctx.createGain();
    gainNode.gain.value = 1.0;
    gainNode.connect(this._masterGain);

    this._stems[name] = { buffer: decoded, source: null, gainNode };
    return decoded;
  }

  _startPlayback(fromTime) {
    if (!this._ctx) return;
    if (this._ctx.state === 'suspended') this._ctx.resume();

    this._startOffset  = this._ctx.currentTime;
    this._posOffset    = fromTime;

    Object.entries(this._stems).forEach(([name, stem]) => {
      if (!stem.buffer) return;
      const src = this._ctx.createBufferSource();
      src.buffer = stem.buffer;
      src.playbackRate.value = this.State.playbackRate;
      src.connect(stem.gainNode);
      src.start(0, fromTime);
      stem.source = src;
    });
    this._applyMuteState();
  }

  /**
   * Start playback after a count-in delay.
   * Stems start at audioCtx.currentTime + leadIn seconds.
   */
  _startPlaybackWithDelay(fromTime, leadIn) {
    if (!this._ctx) return;
    if (this._ctx.state === 'suspended') this._ctx.resume();

    const startAt = this._ctx.currentTime + leadIn;
    // Store offsets so _getPosition() works correctly after playback starts
    this._startOffset = startAt;
    this._posOffset   = fromTime;

    Object.entries(this._stems).forEach(([name, stem]) => {
      if (!stem.buffer) return;
      const src = this._ctx.createBufferSource();
      src.buffer = stem.buffer;
      src.playbackRate.value = this.State.playbackRate;
      src.connect(stem.gainNode);
      src.start(startAt, fromTime);
      stem.source = src;
    });
    this._applyMuteState();
  }

  _stopSources() {
    Object.values(this._stems).forEach(stem => {
      try { stem.source?.stop(); } catch {}
      stem.source = null;
    });
  }

  _stopAudio() {
    this._stopSources();
    this._stopRaf();
    this.State.isPlaying = false;
    this.State.currentTime = 0;
  }

  _getPosition() {
    if (!this.State.isPlaying || !this._ctx) return this.State.currentTime;
    // Don't report negative time during count-in lead-in
    const elapsed = (this._ctx.currentTime - this._startOffset) * this.State.playbackRate;
    return Math.max(0, this._posOffset + elapsed);
  }

  _longestStemDuration() {
    return Math.max(0, ...Object.values(this._stems).map(s => s.buffer?.duration || 0));
  }

  _applyMuteState() {
    const hasSolo = Object.values(this.State.mixer).some(m => m.soloed);
    Object.entries(this._stems).forEach(([name, stem]) => {
      const m = this.State.mixer[name] || { volume: 1, muted: false, soloed: false };
      const shouldBeSilent = m.muted || (hasSolo && !m.soloed);
      stem.gainNode.gain.value = shouldBeSilent ? 0 : (m.volume ?? 1.0);
    });
  }

  // ── Private: click-track (Web Audio lookahead scheduler) ─────────────────

  /**
   * Compute a median inter-beat interval from the next N beats starting at pos.
   * Used for count-in timing.
   */
  _medianInterval(beats, fromPos, n) {
    let i = 0;
    while (i < beats.length - 1 && beats[i] < fromPos) i++;
    const slice = beats.slice(i, i + Math.max(2, n + 1));
    if (slice.length < 2) return 60 / (this.State.beats?.bpm || 120);
    const diffs = [];
    for (let k = 0; k < slice.length - 1; k++) diffs.push(slice[k + 1] - slice[k]);
    diffs.sort((a, b) => a - b);
    return diffs[Math.floor(diffs.length / 2)];
  }

  _computeCountInDuration(countInBars) {
    const beats = this.State.beats?.beats;
    if (!beats?.length) return 0;
    const bpb = this.State.metronomeBeatsPerBar > 0 ? this.State.metronomeBeatsPerBar : 4;
    const interval = this._medianInterval(beats, this.State.currentTime, bpb);
    return countInBars * bpb * interval;
  }

  /**
   * Synthesise a single click at the given AudioContext time.
   * level: 0 = normal, 1 = group accent, 2 = downbeat
   */
  _scheduleClick(atTime, level) {
    if (!this._ctx || !this._metro.gainNode) return;

    let freq, peak;
    if (level === 2)      { freq = ACCENT_FREQ; peak = ACCENT_PEAK; }
    else if (level === 1) { freq = GROUP_FREQ;  peak = GROUP_PEAK;  }
    else                  { freq = CLICK_FREQ;  peak = CLICK_PEAK;  }

    const osc  = this._ctx.createOscillator();
    const env  = this._ctx.createGain();
    osc.frequency.value = freq;
    osc.connect(env);
    env.connect(this._metro.gainNode);

    const attackEnd = atTime + CLICK_ATTACK;
    const decayEnd  = atTime + CLICK_DECAY;
    env.gain.setValueAtTime(0.0001, atTime);
    env.gain.exponentialRampToValueAtTime(peak, attackEnd);
    env.gain.exponentialRampToValueAtTime(0.0001, decayEnd);

    osc.start(atTime);
    osc.stop(decayEnd + 0.01);
  }

  /** Return the beat level (0/1/2) for a given beat index. */
  _beatLevel(idx) {
    const bpb = this.State.metronomeBeatsPerBar;
    if (bpb === 0) return 0; // accent off
    const perBar = bpb > 0 ? bpb : 4; // -1 = auto → 4/4
    const pos = idx % perBar;
    if (pos === 0) return 2; // downbeat
    // Simple half-bar group accent for compound metres
    if (perBar >= 6 && pos === Math.floor(perBar / 2)) return 1;
    if (perBar === 4 && pos === 2) return 1;
    return 0;
  }

  /** Start the lookahead scheduler. Picks up from State.currentTime in the beat grid. */
  _startMetronome() {
    this._stopMetronome();
    if (!this.State.beats?.beats?.length) {
      const note = document.getElementById('t-metro-note');
      if (note) note.textContent = 'No beat data — load a song first';
      return;
    }
    const note = document.getElementById('t-metro-note');
    if (note) note.textContent = '';

    if (this._ctx.state === 'suspended') this._ctx.resume();

    // Update metronome gain from current state
    if (this._metro.gainNode) {
      this._metro.gainNode.gain.value = this.State.metronomeVolume;
    }

    const beats   = this.State.beats.beats;
    const multiplier = this.State.metronomeMultiplier || 1.0;

    // Build the click grid by applying the multiplier
    const grid = this._applyMultiplier(beats, multiplier);

    // Find the first beat at or after the current position
    const pos = this.State.currentTime;
    let idx = 0;
    while (idx < grid.length - 1 && grid[idx] < pos) idx++;

    this._metro.nextBeatIdx  = idx;
    // Map grid time → AudioContext time
    // _posOffset and _startOffset are already set by _startPlayback
    this._metro._grid = grid;

    const tick = () => {
      if (!this.State.isPlaying || !this.State.metronomeEnabled) {
        this._stopMetronome();
        return;
      }
      const ahead = this._ctx.currentTime + this._metro.scheduleAheadSec;
      while (
        this._metro.nextBeatIdx < this._metro._grid.length &&
        this._gridTimeToCtx(this._metro._grid[this._metro.nextBeatIdx]) < ahead
      ) {
        const beatTrackIdx = Math.round(this._metro.nextBeatIdx / (multiplier === 2 ? 0.5 : multiplier === 0.5 ? 2 : 1));
        const level = this._beatLevel(multiplier === 2 ? Math.floor(this._metro.nextBeatIdx / 2) : this._metro.nextBeatIdx);
        const atTime = this._gridTimeToCtx(this._metro._grid[this._metro.nextBeatIdx]);
        if (atTime >= this._ctx.currentTime - 0.01) {
          this._scheduleClick(Math.max(atTime, this._ctx.currentTime), level);
        }
        this._metro.nextBeatIdx++;
      }
    };

    tick();
    this._metro.timerId = setInterval(tick, this._metro.lookaheadMs);
  }

  /** Schedule count-in clicks before playback starts. */
  _startMetronomeCountIn(countInBars, leadIn) {
    if (!this._ctx || !this._metro.gainNode) return;
    if (this._ctx.state === 'suspended') this._ctx.resume();

    if (this._metro.gainNode) {
      this._metro.gainNode.gain.value = this.State.metronomeVolume;
    }

    const bpb      = this.State.metronomeBeatsPerBar > 0 ? this.State.metronomeBeatsPerBar : 4;
    const interval = leadIn / (countInBars * bpb);
    const nowCtx   = this._ctx.currentTime;
    const total    = countInBars * bpb;

    for (let i = 0; i < total; i++) {
      const atTime = nowCtx + i * interval;
      const pos    = i % bpb;
      const level  = pos === 0 ? 2 : (pos === Math.floor(bpb / 2) ? 1 : 0);
      this._scheduleClick(atTime, level);
    }

    // After count-in, hand off to the normal scheduler
    setTimeout(() => {
      if (this.State.isPlaying && this.State.metronomeEnabled) {
        this._startMetronome();
      }
    }, leadIn * 1000);
  }

  _stopMetronome() {
    if (this._metro.timerId) {
      clearInterval(this._metro.timerId);
      this._metro.timerId = null;
    }
    this._metro._grid = null;
    this._metro.nextBeatIdx = 0;
  }

  /** Convert a beat-grid timestamp (track seconds) to AudioContext time. */
  _gridTimeToCtx(trackTime) {
    // _startOffset = ctx time when play() was called
    // _posOffset   = track position at that moment
    // playbackRate affects how fast ctx time maps to track time
    return this._startOffset + (trackTime - this._posOffset) / this.State.playbackRate;
  }

  /** Apply metronome multiplier (0.5 = half-time, 2 = double-time). */
  _applyMultiplier(beats, mult) {
    if (mult === 2.0) {
      const out = [];
      for (let i = 0; i < beats.length - 1; i++) {
        out.push(beats[i]);
        out.push((beats[i] + beats[i + 1]) / 2);
      }
      if (beats.length) out.push(beats[beats.length - 1]);
      return out;
    }
    if (mult === 0.5) return beats.filter((_, i) => i % 2 === 0);
    return [...beats];
  }

  // ── Private: rAF loop ─────────────────────────────────────────────────────

  _startRaf() {
    this._stopRaf();
    const tick = () => {
      if (!this.State.isPlaying) return;
      const pos = this._getPosition();

      // Loop
      if (this.State.loopEnabled && pos >= this.State.loopEnd && this.State.loopEnd > 0) {
        this._stopSources();
        this._stopMetronome();
        this._posOffset = this.State.loopStart;
        this._startOffset = this._ctx.currentTime;
        this._startPlayback(this.State.loopStart);
        if (this.State.metronomeEnabled) this._startMetronome();
        return;
      }

      // End of track
      if (pos >= this.State.duration && this.State.duration > 0) {
        this.stop();
        this._updateTransportUI();
        return;
      }

      this.State.currentTime = pos;
      this._updatePlayhead(pos);
      this._updateTransportUI();
      if (typeof this._onTick === 'function') this._onTick(pos);
      this._rafId = requestAnimationFrame(tick);
    };
    this._rafId = requestAnimationFrame(tick);
  }

  _stopRaf() {
    if (this._rafId) { cancelAnimationFrame(this._rafId); this._rafId = null; }
  }

  // ── Private: waveform drawing ─────────────────────────────────────────────

  _buildMixer(stems, allPeaks) {
    if (!this._mixerEl) return;
    this._mixerEl.innerHTML = '';
    this._container && (this._container.innerHTML = '');

    // Inject fader styles once
    if (!document.getElementById('mwtn-fader-style')) {
      const st = document.createElement('style');
      st.id = 'mwtn-fader-style';
      st.textContent = `
        .mixer-row { display:flex; align-items:center; height:var(--lane-h,86px); border-bottom:1px solid var(--border); gap:8px; padding:0 10px; }
        .mixer-stem-icon { width:28px; height:28px; border-radius:6px; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
        .mixer-stem-label { font-size:11px; font-weight:600; width:52px; flex-shrink:0; text-transform:capitalize; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .mixer-ms-group { display:flex; flex-direction:column; gap:3px; flex-shrink:0; }
        .mixer-ms-btn { width:20px; height:18px; border-radius:4px; font-size:9px; font-weight:700; font-family:var(--font-mono); background:var(--panel-2); border:1px solid var(--border); color:var(--muted); display:flex; align-items:center; justify-content:center; cursor:pointer; transition:background 80ms,color 80ms,border-color 80ms; }
        .mixer-ms-btn.muted  { background:rgba(59,130,246,.18); color:#60a5fa; border-color:rgba(59,130,246,.4); }
        .mixer-ms-btn.soloed { background:rgba(244,183,64,.18); color:var(--accent); border-color:rgba(244,183,64,.4); }
        .mixer-fader { -webkit-appearance:none; appearance:none; height:4px; border-radius:2px; flex:1; min-width:40px;
          background:linear-gradient(to right, var(--track-fill) 0%, var(--track-fill) calc(var(--val,67%)), rgba(255,255,255,0.08) calc(var(--val,67%))); cursor:ew-resize; }
        .mixer-fader::-webkit-slider-thumb { -webkit-appearance:none; width:14px; height:14px; border-radius:50%;
          background:var(--track-fill); border:2px solid rgba(0,0,0,0.35); box-shadow:0 0 0 1px rgba(255,255,255,0.18); }
        .mixer-fader::-moz-range-thumb { width:14px; height:14px; border-radius:50%; background:var(--track-fill); border:2px solid rgba(0,0,0,0.35); }
        .mixer-vol-readout { font-size:10px; font-family:var(--font-mono); color:var(--muted); width:30px; text-align:right; flex-shrink:0; }
      `;
      document.head.appendChild(st);
    }

    stems.forEach(name => {
      const color = STEM_COLORS[name] || '#888';
      const icon  = STEM_ICONS[name] || STEM_ICONS.other;
      const label = name.replace('_', ' ');

      // ── Mixer row (left panel) ──────────────────────────────────────────
      const row = document.createElement('div');
      row.className = 'mixer-row';
      row.innerHTML = `
        <div class="mixer-stem-icon" style="background:color-mix(in srgb,${color} 18%,transparent);color:${color}">
          ${icon}
        </div>
        <span class="mixer-stem-label" style="color:${color}">${label}</span>
        <div class="mixer-ms-group">
          <button class="mixer-ms-btn mute-btn" data-stem="${name}" aria-pressed="false" aria-label="Mute ${name}" title="Mute">M</button>
          <button class="mixer-ms-btn solo-btn" data-stem="${name}" aria-pressed="false" aria-label="Solo ${name}" title="Solo">S</button>
        </div>
        <input type="range" class="mixer-fader" min="0" max="1.5" step="0.01" value="1"
          data-stem="${name}" aria-label="${name} volume" style="--track-fill:${color}">
        <span class="mixer-vol-readout">100%</span>
      `;
      this._mixerEl.appendChild(row);

      const fader   = row.querySelector('.mixer-fader');
      const readout = row.querySelector('.mixer-vol-readout');
      fader.addEventListener('input', () => {
        const vol = parseFloat(fader.value);
        readout.textContent = `${Math.round(vol * 100)}%`;
        this.setStemVolume(name, vol);
      });

      const muteBtn = row.querySelector('.mute-btn');
      const soloBtn = row.querySelector('.solo-btn');

      muteBtn.addEventListener('click', () => {
        const m = this.State.mixer[name] || {};
        const nowMuted = !m.muted;
        this.setStemMuted(name, nowMuted);
        muteBtn.classList.toggle('muted', nowMuted);
        muteBtn.setAttribute('aria-pressed', nowMuted ? 'true' : 'false');
      });

      soloBtn.addEventListener('click', () => {
        const m = this.State.mixer[name] || {};
        const nowSoloed = !m.soloed;
        this.setStemSoloed(name, nowSoloed);
        this._mixerEl.querySelectorAll('.solo-btn').forEach(b => {
          const bName = b.dataset.stem;
          const isSoloed = this.State.mixer[bName]?.soloed || false;
          b.classList.toggle('soloed', isSoloed);
          b.setAttribute('aria-pressed', isSoloed ? 'true' : 'false');
        });
      });

      // ── Waveform lane (right panel) ─────────────────────────────────────
      const lane = document.createElement('div');
      lane.className = 'wave-lane';
      lane.dataset.stem = name;
      lane.style.cssText = `height:var(--lane-h,86px);border-bottom:1px solid var(--border);position:relative;overflow:hidden`;
      const canvas = document.createElement('canvas');
      canvas.className = 'wave-lane-canvas';
      canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%';
      lane.appendChild(canvas);
      this._container?.appendChild(lane);

      const peaks = allPeaks?.[name] || this._extractPeaksFromBuffer(name, 1500);
      if (peaks?.length) {
        requestAnimationFrame(() => this._drawLaneWaveform(canvas, peaks, color));
      }
    });
  }

  _extractPeaksFromBuffer(name, numPoints) {
    const stem = this._stems[name];
    if (!stem?.buffer) return null;
    const data  = stem.buffer.getChannelData(0);
    const step  = Math.max(1, Math.floor(data.length / numPoints));
    const peaks = [];
    for (let i = 0; i < numPoints; i++) {
      let min = 0, max = 0;
      for (let j = i * step; j < Math.min((i + 1) * step, data.length); j++) {
        if (data[j] < min) min = data[j];
        if (data[j] > max) max = data[j];
      }
      peaks.push([min, max]);
    }
    return peaks;
  }

  _drawLaneWaveform(canvas, peaks, color) {
    const pr = window.devicePixelRatio || 1;
    const w  = canvas.offsetWidth || canvas.parentElement?.offsetWidth || 800;
    const h  = canvas.offsetHeight || canvas.parentElement?.offsetHeight || 86;
    canvas.width  = w * pr;
    canvas.height = h * pr;
    const ctx = canvas.getContext('2d');
    ctx.scale(pr, pr);
    ctx.clearRect(0, 0, w, h);

    const mid  = h / 2;
    const barW = w / peaks.length;
    const hex  = color.replace('#', '');
    const r = parseInt(hex.slice(0,2),16);
    const g = parseInt(hex.slice(2,4),16);
    const b = parseInt(hex.slice(4,6),16);

    peaks.forEach(([lo, hi], i) => {
      const x    = i * barW;
      const yTop = mid - hi * mid * 0.95;
      const yBot = mid - lo * mid * 0.95;
      ctx.fillStyle = `rgba(${r},${g},${b},0.75)`;
      ctx.fillRect(Math.floor(x), yTop, Math.max(1, Math.ceil(barW) - 1), Math.max(1, yBot - yTop));
    });

    canvas._peaks = peaks;
    canvas._color = color;
  }

  _drawAllWaveforms(stems, allPeaks) {
    stems.forEach(name => {
      const canvas = this._container?.querySelector(`.wave-lane[data-stem="${name}"] canvas`);
      if (!canvas) return;
      const color = STEM_COLORS[name] || '#888';
      const peaks = allPeaks?.[name] || this._extractPeaksFromBuffer(name, 1500);
      if (peaks?.length) {
        requestAnimationFrame(() => this._drawLaneWaveform(canvas, peaks, color));
      }
    });
  }

  _drawFooterWaveform(stems, allPeaks) {
    const canvas = this._footerWave;
    if (!canvas) return;
    const firstStem = stems[0];
    if (!firstStem) return;
    const peaks = allPeaks?.[firstStem] || this._extractPeaksFromBuffer(firstStem, 800);
    if (!peaks?.length) return;
    requestAnimationFrame(() => {
      const pr = window.devicePixelRatio || 1;
      const w  = canvas.offsetWidth || 600;
      const h  = canvas.offsetHeight || 40;
      canvas.width  = w * pr;
      canvas.height = h * pr;
      const ctx = canvas.getContext('2d');
      ctx.scale(pr, pr);
      ctx.clearRect(0, 0, w, h);
      const mid = h / 2;
      const barW = w / peaks.length;
      ctx.fillStyle = 'rgba(244,183,64,0.5)';
      peaks.forEach(([lo, hi], i) => {
        const x = i * barW;
        ctx.fillRect(Math.floor(x), mid - hi * mid * 0.9, Math.max(1, Math.ceil(barW) - 1), Math.max(1, (hi - lo) * mid * 0.9));
      });
      canvas._totalPeaks = peaks.length;
    });
  }

  _clearWaveforms() {
    if (this._container) this._container.innerHTML = '';
    if (this._mixerEl) this._mixerEl.innerHTML = '';
    if (this._footerWave) {
      const ctx = this._footerWave.getContext('2d');
      if (ctx) ctx.clearRect(0, 0, this._footerWave.width, this._footerWave.height);
    }
    document.querySelectorAll('.stem-list span').forEach(row => {
      const muteBtn = row.querySelector('.stem-mute');
      const soloBtn = row.querySelector('.stem-solo');
      if (muteBtn) { muteBtn.removeAttribute('style'); muteBtn.setAttribute('aria-pressed','false'); }
      if (soloBtn) { soloBtn.removeAttribute('style'); soloBtn.setAttribute('aria-pressed','false'); }
    });
    this._stems = {};
  }

  // ── Private: playhead ──────────────────────────────────────────────────────

  _updatePlayhead(pos) {
    const dur  = this.State.duration;
    const frac = dur > 0 ? Math.min(1, pos / dur) : 0;

    if (this._scrubFill) {
      this._scrubFill.style.width = `${frac * 100}%`;
    }

    const marker = document.querySelector('.playhead-marker');
    const ruler  = document.getElementById('ruler-time');
    if (marker && ruler) {
      marker.style.left = `${frac * 100}%`;
    }
  }

  _updateTransportUI() {
    const pos = this.State.currentTime;
    const dur = this.State.duration;
    const fmt = (s) => {
      const m  = Math.floor(s / 60);
      const ss = Math.floor(s % 60).toString().padStart(2, '0');
      return `${m}:${ss}`;
    };
    const elElapsed = document.getElementById('footer-time-elapsed');
    const elTotal   = document.getElementById('footer-time-total');
    if (elElapsed) elElapsed.textContent = fmt(pos);
    if (elTotal)   elTotal.textContent   = fmt(dur);
    this._updatePlayhead(pos);
    this._updatePlayBtn();
  }

  _updatePlayBtn() {
    const btn = document.getElementById('t-play');
    if (!btn) return;
    btn.classList.toggle('playing', this.State.isPlaying);
    btn.setAttribute('aria-label', this.State.isPlaying ? 'Pause' : 'Play');
  }

  // ── Private: analysis ─────────────────────────────────────────────────────

  _populateAnalysis(manifest, beats, keyInfo, presence) {
    // KEY
    const keyStr = manifest.key || keyInfo?.key;
    if (keyStr) {
      const parts = keyStr.split(' ');
      const keyPart   = parts.slice(0, -1).join(' ') || keyStr;
      const scalePart = parts.slice(-1)[0] || '';
      setText('summary-key', keyPart);
      setText('summary-scale', scalePart);
    }

    // SCALE full name
    const scale = manifest.scale || keyInfo?.scale;
    if (scale) setText('summary-scale-name', scale === 'Natural Minor' ? 'Aeolian / Natural Minor' : scale);

    // BPM
    const bpm = manifest.bpm || beats?.bpm;
    if (bpm) setText('summary-bpm', Math.round(bpm));

    // LUFS + peak — show "n/a" (not "—") after a song loads if data is absent
    const lufs   = keyInfo?.lufs    ?? manifest.lufs;
    const peakDb = keyInfo?.peak_db ?? manifest.peak_db;
    if (lufs    != null) {
      setText('summary-lufs', `${parseFloat(lufs).toFixed(1)}`);
      document.querySelector('[data-meta="lufs"]')?.classList.remove('meta-card--unavailable');
    } else {
      setText('summary-lufs', 'n/a');
      document.querySelector('[data-meta="lufs"]')?.classList.add('meta-card--unavailable');
    }
    if (peakDb != null) setText('summary-peak', `Peak ${parseFloat(peakDb).toFixed(1)} dB`);

    // DURATION
    const durSecs = beats?.duration ?? manifest.duration_secs ?? this._longestStemDuration();
    if (durSecs > 0) {
      setText('summary-duration', fmtDur(durSecs));
      if (durSecs > this.State.duration) this.State.duration = durSecs;
    }

    // DYNAMIC RANGE
    const dr = keyInfo?.dynamic_range ?? manifest.dynamic_range;
    if (dr != null) {
      setText('summary-dr', `${parseFloat(dr).toFixed(1)}`);
      const drLbl = dr > 14 ? 'Wide' : dr > 8 ? 'Medium' : 'Narrow';
      setText('summary-dr-label', drLbl);
      document.querySelector('[data-meta="dr"]')?.classList.remove('meta-card--unavailable');
    } else {
      setText('summary-dr', 'n/a');
      setText('summary-dr-label', '');
      document.querySelector('[data-meta="dr"]')?.classList.add('meta-card--unavailable');
    }

    // TEMPO STABILITY
    const stability = beats?.tempo_stability ?? manifest.tempo_stability;
    if (stability != null) {
      setText('summary-stability', `${stability}%`);
      const sLbl = stability >= 90 ? 'Very Stable' : stability >= 70 ? 'Stable' : 'Variable';
      setText('summary-stability-label', sLbl);
      setClass('summary-stability', 'accent', stability >= 90);
      document.querySelector('[data-meta="stability"]')?.classList.remove('meta-card--unavailable');
    } else {
      setText('summary-stability', 'n/a');
      setText('summary-stability-label', '');
      document.querySelector('[data-meta="stability"]')?.classList.add('meta-card--unavailable');
    }

    // STEM PRESENCE — merge manifest data with freshly fetched presence
    const presenceData = presence ?? manifest.stem_presence ?? {};
    document.querySelectorAll('.stem-card[data-stem]').forEach(card => {
      const name  = card.dataset.stem;
      const pctEl = card.querySelector('.stem-card-pct');
      if (!pctEl) return;
      if (presenceData[name] != null) {
        pctEl.textContent = `${presenceData[name]}%`;
        card.classList.remove('inactive');
      } else {
        pctEl.textContent = '—';
        card.classList.add('inactive');
      }
    });
    Object.entries(presenceData).forEach(([name, val]) => {
      const el = document.getElementById(`pct-${name}`);
      if (el) el.textContent = `${val}%`;
    });
    setText('pct-stems', manifest.stems?.length ?? '—');

    // NOW-PLAYING header
    const nowDur = durSecs > 0 ? fmtDur(durSecs) : '—';
    setText('t-meta-duration', nowDur);
    const stemCount = (manifest.stems || []).length;
    const stemsChip = document.getElementById('t-stems-chip');
    if (stemsChip) stemsChip.textContent = `${stemCount} stem${stemCount !== 1 ? 's' : ''}`;

    // Footer total time
    if (durSecs > 0) {
      const m = Math.floor(durSecs / 60);
      const s = Math.floor(durSecs % 60).toString().padStart(2, '0');
      setText('footer-time-total', `${m}:${s}`);
    }
  }

  _resetAnalysis() {
    ['summary-key','summary-bpm','summary-lufs','summary-peak','summary-duration',
     'summary-scale','summary-scale-name','summary-dr','summary-dr-label',
     'summary-stability','summary-stability-label'].forEach(id => setText(id, '—'));
    document.querySelectorAll('.stem-card-pct').forEach(el => { el.textContent = '—'; });
    document.querySelectorAll('[id^="pct-"]').forEach(el => { el.textContent = '—'; });
    document.querySelectorAll('.stem-card').forEach(c => c.classList.add('inactive'));
    // Clear n/a state on reset
    document.querySelectorAll('.meta-card--unavailable').forEach(c => c.classList.remove('meta-card--unavailable'));
  }

  _updateNowPlaying(manifest) {
    setText('title', manifest.title || manifest.song_id);
    const srcEl = document.getElementById('track-source');
    if (srcEl) srcEl.textContent = manifest.separation_model || 'colab';
  }

  // ── Private: transport enable ─────────────────────────────────────────────

  _enableTransport() {
    ['t-play','t-stop','t-loop','t-metro',
     't-pitch-up','t-pitch-down','t-pitch-reset'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.disabled = false;
    });
    document.querySelector('#t-metro-panel')?.classList.remove('unavailable');
    // Set total time
    const dur = this.State.duration;
    const m = Math.floor(dur / 60);
    const s = Math.floor(dur % 60).toString().padStart(2, '0');
    setText('footer-time-total', `${m}:${s}`);
  }

  // ── Private: UI ───────────────────────────────────────────────────────────

  _showLoading(msg) {
    if (this._loadingEl)  this._loadingEl.classList.remove('hidden');
    if (this._phraseEl)   this._phraseEl.textContent = msg || 'Loading…';
    if (this._jobEl)      this._jobEl.classList.remove('hidden');
    const titleEl = document.getElementById('job-title');
    const stageEl = document.getElementById('job-stage');
    if (titleEl) titleEl.textContent = 'Loading song…';
    if (stageEl) stageEl.textContent = msg || '';
  }

  _setPhrase(msg) {
    if (this._phraseEl) this._phraseEl.textContent = msg;
    const stageEl = document.getElementById('job-stage');
    if (stageEl) stageEl.textContent = msg;
  }

  _hideLoading() {
    if (this._loadingEl) this._loadingEl.classList.add('hidden');
    if (this._jobEl)     this._jobEl.classList.add('hidden');
  }

  _showError(msg) {
    if (!this._errorEl) return;
    if (msg) {
      this._errorEl.textContent = msg;
      this._errorEl.classList.remove('hidden');
    } else {
      this._errorEl.textContent = '';
      this._errorEl.classList.add('hidden');
    }
  }

  _bindExportUI() {
    document.querySelectorAll('.export-fmt').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.export-fmt').forEach(b => {
          b.classList.remove('active');
          b.setAttribute('aria-checked', 'false');
        });
        btn.classList.add('active');
        btn.setAttribute('aria-checked', 'true');
        this._exportFmt = btn.id.replace('t-fmt-', '');
      });
    });

    document.getElementById('t-export-click')?.addEventListener('change', (e) => {
      this._exportClick = e.target.checked;
    });

    const scrub = document.getElementById('footer-scrub');
    scrub?.addEventListener('click', (e) => {
      const rect = scrub.getBoundingClientRect();
      const frac = (e.clientX - rect.left) / rect.width;
      this.seek(frac * this.State.duration);
    });
  }
}
