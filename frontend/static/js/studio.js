/**
 * studio.js — Audio engine, waveform rendering, playback control.
 *
 * Key additions over v8 base:
 *  - Progressive stem loading: play starts as soon as first stem decodes.
 *    Subsequent stems join the playback graph as they arrive.
 *  - Scrub bar: full mousedown/mousemove/mouseup + touch drag.
 *  - Per-stem AnalyserNode exposed as stem.analyser for VU meters.
 *  - Ruler beat markers drawn via canvas (display) + DOM ticks (edit mode).
 *  - _onTick(pos) hook called from rAF for SolfaPanel, BeatGrid, etc.
 */

const STEM_COLORS = {
  vocals:'#e85f6f', drums:'#e89048', bass:'#e8b848',
  guitar:'#88d878', piano:'#b88fe0', other:'#88a8c8',
  original:'#a8b0bd', lead_vocals:'#e8748a', backing_vocals:'#c98fe0',
};
const STEM_ICONS = {
  vocals:`<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><path d="M12 19v3"/></svg>`,
  drums:`<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9"><ellipse cx="12" cy="9" rx="9" ry="4"/><path d="M3 9v6c0 2.2 4 4 9 4s9-1.8 9-4V9"/></svg>`,
  bass:`<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M16.5 3h4v5h-3"/><path d="M17.5 5.5 9.8 13.2"/><path d="M10 13c1.6 2.2 1.1 5.1-1.2 6.5-2.1 1.3-5 .5-6-1.6-.9-1.9-.1-4.1 1.8-5 1.2-.6 2.6-.1 3.2 1.1"/></svg>`,
  guitar:`<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M16 4.5 20 2l2 2-2.5 4"/><path d="M18.2 5.8 10.2 13.8"/><circle cx="7" cy="16.4" r="3.6"/></svg>`,
  piano:`<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M7 5v8M12 5v8M17 5v8M9.5 5v5M14.5 5v5"/></svg>`,
  other:`<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M4 13v-2M8 17V7M12 21V3M16 17V7M20 13v-2"/></svg>`,
  original:`<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`,
};
STEM_ICONS.lead_vocals    = STEM_ICONS.vocals;
STEM_ICONS.backing_vocals = STEM_ICONS.vocals;

// Click-track voice constants (must match click_render.py)
const CLICK_FREQ=1000,GROUP_FREQ=1225,ACCENT_FREQ=1500;
const CLICK_DECAY=0.035,CLICK_ATTACK=0.001;
const CLICK_PEAK=0.7,GROUP_PEAK=0.85,ACCENT_PEAK=1.0;

function fmtDur(s){ if(!s||!isFinite(s))return'—'; const m=Math.floor(s/60); return `${m}:${Math.floor(s%60).toString().padStart(2,'0')}`; }
function setText(id,v){ const e=document.getElementById(id); if(e) e.textContent=v??'—'; }
function setClass(id,cls,on){ const e=document.getElementById(id); if(e) e.classList.toggle(cls,on); }

export class Studio {
  constructor({ State, API }) {
    this.State = State;
    this.API   = API;

    this._ctx        = null;
    this._masterGain = null;
    this._stems      = {};   // { [name]: { buffer, source, gainNode, analyser } }
    this._startOffset= 0;
    this._posOffset  = 0;
    this._rafId      = null;

    this._metro = {
      gainNode:null, nextBeatIdx:0, nextBeatTime:0,
      lookaheadMs:100, scheduleAheadSec:0.15, timerId:null, _grid:null,
    };

    this._exportFmt   = 'wav';
    this._exportClick = false;

    // Hooks set by app.js after construction
    this._onTick       = null;   // (pos: number) => void
    this._onStemReady  = null;   // (name: string, total: number, loaded: number) => void

    this._loadingEl  = document.getElementById('waveLoadingOverlay');
    this._phraseEl   = document.getElementById('waveLoadingPhrase');
    this._jobEl      = document.getElementById('job');
    this._errorEl    = document.getElementById('error');
    this._mixerEl    = document.getElementById('mixer');
    this._container  = document.getElementById('multitrack-container');
    this._footerWave = document.getElementById('footer-waveform');
    this._scrubFill  = document.getElementById('footer-scrub-fill');

    this._initScrub();
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

    State.songId      = songId;
    State.manifest    = null;
    State.beats       = null;
    State.keyInfo     = null;
    State.sections    = [];
    State.isPlaying   = false;
    State.currentTime = 0;
    State.mixer       = {};
    State.stemLoadProgress = {};

    this._resetAnalysis();

    try {
      this._setPhrase('Reading manifest…');
      const manifest = await API.getManifest(songId);
      State.manifest = manifest;
      this._updateNowPlaying(manifest);

      const stems = manifest.stems || [];

      this._setPhrase('Fetching analysis…');
      const [beats, keyInfo, presence, sections] = await Promise.allSettled([
        API.getBeats(songId),
        API.getKey(songId),
        API.getStemPresence(songId),
        API.getSections(songId),
      ]).then(r => r.map(v => v.status === 'fulfilled' ? v.value : null));

      State.beats    = beats;
      State.keyInfo  = keyInfo;
      State.sections = sections || [];

      this._populateAnalysis(manifest, beats, keyInfo, presence);

      this._setPhrase('Loading waveforms…');
      const allPeaks = await API.getAllPeaks(songId).catch(() => null);

      this._setPhrase('Decoding audio…');
      this._initAudioContext();

      // Build mixer layout immediately so the UI is populated
      this._buildMixer(stems, allPeaks);
      this._drawAllWaveforms(stems, allPeaks);
      this._drawFooterWaveform(stems, allPeaks);

      // Progressive loading — enable transport after first stem decodes
      let loadedCount   = 0;
      let firstEnabled  = false;

      const onStemDone = (name, ok) => {
        if (ok) loadedCount++;
        const total = stems.length;
        if (typeof this._onStemReady === 'function') this._onStemReady(name, total, loadedCount);
        // Enable transport the moment first stem is available
        if (loadedCount > 0 && !firstEnabled) {
          firstEnabled = true;
          State.duration = this._longestStemDuration();
          this._enableTransport();
          this._hideLoading();
          document.getElementById('app')?.classList.remove('no-track');
          document.getElementById('app')?.classList.add('has-track');
        }
      };

      await Promise.allSettled(
        stems.map(name =>
          this._loadStemBuffer(songId, name)
            .then(() => onStemDone(name, true))
            .catch(err => { console.warn(`[studio] stem ${name} failed:`, err); onStemDone(name, false); })
        )
      );

      // Final duration update once all stems are in
      State.duration = this._longestStemDuration();
      this._updateTransportUI();

      if (loadedCount === 0) {
        this._hideLoading();
        throw new Error('No stems could be decoded');
      }

      // Draw ruler beats now that beats are loaded
      this._drawRulerBeats();

    } catch (err) {
      console.error('[studio] loadSong failed:', err);
      this._hideLoading();
      this._showError(`Failed to load song: ${err.message}`);
    }
  }

  // ── Public: playback ──────────────────────────────────────────────────────

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
    this.State.isPlaying   = false;
    this._stopSources();
    this._stopRaf();
    this._stopMetronome();
  }

  stop() {
    this.State.currentTime = 0;
    this.State.isPlaying   = false;
    this._stopSources();
    this._stopRaf();
    this._stopMetronome();
    this._updatePlayhead(0);
    this._updateTransportUI();
  }

  seek(time) {
    const wasPlaying = this.State.isPlaying;
    if (wasPlaying) { this._stopSources(); this._stopMetronome(); }
    this.State.currentTime = Math.max(0, Math.min(time, this.State.duration));
    if (wasPlaying) {
      this._startPlayback(this.State.currentTime);
      if (this.State.metronomeEnabled) this._startMetronome();
    }
    this._updatePlayhead(this.State.currentTime);
    this._updateTransportUI();
  }

  getPosition()  { return this._getPosition(); }
  getDuration()  { return this.State.duration; }

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
    if (!this.State.mixer[name]) this.State.mixer[name] = { volume:1, muted:false, soloed:false };
    this.State.mixer[name].volume = vol;
  }

  setStemMuted(name, muted) {
    if (!this.State.mixer[name]) this.State.mixer[name] = { volume:1, muted:false, soloed:false };
    this.State.mixer[name].muted = muted;
    this._applyMuteState();
  }

  setStemSoloed(name, soloed) {
    if (!this.State.mixer[name]) this.State.mixer[name] = { volume:1, muted:false, soloed:false };
    this.State.mixer[name].soloed = soloed;
    this._applyMuteState();
  }

  onMetronomeToggle() {
    if (this.State.metronomeEnabled && this.State.isPlaying) this._startMetronome();
    else this._stopMetronome();
  }

  clearStudio() {
    this._stopAudio();
    this._stopMetronome();
    this._clearWaveforms();
    this._resetAnalysis();
    if (this._mixerEl) this._mixerEl.innerHTML = '';
    document.getElementById('app')?.classList.add('no-track');
    document.getElementById('app')?.classList.remove('has-track');
    State.songId = null; State.manifest = null;
  }

  // ── Export helpers (called by app.js) ─────────────────────────────────────

  exportMix() {
    const { State, API } = this;
    if (!State.songId || !State.manifest) return;
    const stems = State.manifest.stems || [];
    const gains = stems.map(s => State.mixer[s]?.volume ?? 1.0);
    const loopOpts = (State.exportLoopOnly && State.loopEnabled && State.loopEnd > State.loopStart)
      ? { start: State.loopStart, end: State.loopEnd } : {};
    const url = API.mixdownUrl(State.songId, {
      stems, gains, ext: this._exportFmt, click: this._exportClick, ...loopOpts,
    });
    API.triggerDownload(url, `${State.songId}_mix.${this._exportFmt}`);
  }

  exportStems() {
    const { State, API } = this;
    if (!State.songId) return;
    API.triggerDownload(
      API.stemsZipUrl(State.songId, this._exportFmt === 'wav' ? 'wav' : 'mp3'),
      `${State.songId}_stems.zip`
    );
  }

  exportSingleStem(name) {
    const { State, API } = this;
    if (!State.songId) return;
    const gain = State.mixer[name]?.volume ?? 1.0;
    const loopOpts = (State.exportLoopOnly && State.loopEnabled && State.loopEnd > State.loopStart)
      ? { start: State.loopStart, end: State.loopEnd } : {};
    const url = API.singleStemUrl(State.songId, name, { gain, ext: this._exportFmt, ...loopOpts });
    API.triggerDownload(url, `${State.songId}_${name}.${this._exportFmt}`);
  }

  // ── Private: audio context ────────────────────────────────────────────────

  _initAudioContext() {
    if (this._ctx) return;
    this._ctx = new (window.AudioContext || window.webkitAudioContext)();
    this._masterGain = this._ctx.createGain();
    this._masterGain.gain.value = 1.0;
    this._masterGain.connect(this._ctx.destination);
    this._metro.gainNode = this._ctx.createGain();
    this._metro.gainNode.gain.value = this.State.metronomeVolume;
    this._metro.gainNode.connect(this._ctx.destination);
  }

  // Progressive fetch: ReadableStream → progress callbacks → decodeAudioData.
  // If playback is already running when this stem arrives, it joins immediately.
  async _loadStemBuffer(songId, name) {
    const url  = this.API.stemUrl(songId, name);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`${resp.status} for ${name}`);

    const contentLength = +resp.headers.get('Content-Length') || 0;
    const reader  = resp.body.getReader();
    const chunks  = [];
    let received  = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      received += value.length;
      if (contentLength > 0) {
        this.State.stemLoadProgress[name] = received / contentLength;
        // Notify loading bar
        const barEl = document.getElementById(`stem-load-bar-${name}`);
        if (barEl) barEl.style.width = `${(received / contentLength) * 100}%`;
      }
    }

    const total = new Uint8Array(received);
    let off = 0;
    for (const c of chunks) { total.set(c, off); off += c.length; }

    const decoded = await this._ctx.decodeAudioData(total.buffer.slice(0));

    // Build audio graph nodes
    if (!this.State.mixer[name]) this.State.mixer[name] = { volume:1.0, muted:false, soloed:false };
    const gainNode = this._ctx.createGain();
    gainNode.gain.value = this.State.mixer[name].volume;

    // AnalyserNode for VU meters — inserted between gain and master
    const analyser = this._ctx.createAnalyser();
    analyser.fftSize              = 256;
    analyser.smoothingTimeConstant = 0.8;
    gainNode.connect(analyser);
    analyser.connect(this._masterGain);

    this._stems[name] = { buffer: decoded, source: null, gainNode, analyser };

    // If already playing, start this late-arriving stem at the current position
    if (this.State.isPlaying) {
      const currentPos = this._getPosition();
      if (currentPos < decoded.duration) {
        const src = this._ctx.createBufferSource();
        src.buffer            = decoded;
        src.playbackRate.value = this.State.playbackRate;
        src.connect(gainNode);
        src.start(0, currentPos);
        this._stems[name].source = src;
        this._applyMuteState();
      }
    }

    // Hide loading bar
    const barEl = document.getElementById(`stem-load-bar-${name}`);
    if (barEl) { barEl.style.width = '100%'; setTimeout(() => barEl.parentElement?.remove(), 600); }

    return decoded;
  }

  _startPlayback(fromTime) {
    if (!this._ctx) return;
    if (this._ctx.state === 'suspended') this._ctx.resume();
    this._startOffset = this._ctx.currentTime;
    this._posOffset   = fromTime;
    Object.entries(this._stems).forEach(([, stem]) => {
      if (!stem.buffer) return;
      const src = this._ctx.createBufferSource();
      src.buffer             = stem.buffer;
      src.playbackRate.value = this.State.playbackRate;
      src.connect(stem.gainNode);
      src.start(0, fromTime);
      stem.source = src;
    });
    this._applyMuteState();
  }

  _startPlaybackWithDelay(fromTime, leadIn) {
    if (!this._ctx) return;
    if (this._ctx.state === 'suspended') this._ctx.resume();
    const startAt     = this._ctx.currentTime + leadIn;
    this._startOffset = startAt;
    this._posOffset   = fromTime;
    Object.entries(this._stems).forEach(([, stem]) => {
      if (!stem.buffer) return;
      const src = this._ctx.createBufferSource();
      src.buffer             = stem.buffer;
      src.playbackRate.value = this.State.playbackRate;
      src.connect(stem.gainNode);
      src.start(startAt, fromTime);
      stem.source = src;
    });
    this._applyMuteState();
  }

  _stopSources() {
    Object.values(this._stems).forEach(s => { try { s.source?.stop(); } catch {} s.source = null; });
  }

  _stopAudio() {
    this._stopSources(); this._stopRaf();
    this.State.isPlaying = false; this.State.currentTime = 0;
  }

  _getPosition() {
    if (!this.State.isPlaying || !this._ctx) return this.State.currentTime;
    const elapsed = (this._ctx.currentTime - this._startOffset) * this.State.playbackRate;
    return Math.max(0, this._posOffset + elapsed);
  }

  _longestStemDuration() {
    return Math.max(0, ...Object.values(this._stems).map(s => s.buffer?.duration || 0));
  }

  _applyMuteState() {
    const hasSolo = Object.values(this.State.mixer).some(m => m.soloed);
    Object.entries(this._stems).forEach(([name, stem]) => {
      const m = this.State.mixer[name] || { volume:1, muted:false, soloed:false };
      stem.gainNode.gain.value = (m.muted || (hasSolo && !m.soloed)) ? 0 : (m.volume ?? 1.0);
    });
  }

  // ── Private: scrub bar ────────────────────────────────────────────────────

  _initScrub() {
    const scrub = document.getElementById('footer-scrub');
    const fill  = document.getElementById('footer-scrub-fill');
    const tip   = document.getElementById('scrub-tooltip');
    if (!scrub) return;

    let dragging   = false;
    let wasPlaying = false;

    const clamp = v => Math.max(0, Math.min(1, v));

    const getClientX = (e) => {
      if (typeof e.clientX === 'number') return e.clientX;
      if (e.touches && e.touches[0]) return e.touches[0].clientX;
      if (e.changedTouches && e.changedTouches[0]) return e.changedTouches[0].clientX;
      if (typeof e.pageX === 'number') return e.pageX;
      return 0;
    };

    const getFrac = (e) => {
      const rect = scrub.getBoundingClientRect();
      const x    = getClientX(e);
      const width = rect.width || 1;
      return clamp((x - rect.left) / width);
    };

    const applyFrac = (frac, commit = false) => {
      const time = frac * this.State.duration;
      if (fill) fill.style.width = `${frac * 100}%`;
      // Move playhead marker
      const marker = document.querySelector('.playhead-marker');
      if (marker) marker.style.left = `${frac * 100}%`;
      // Tooltip
      if (tip) {
        tip.textContent = fmtDur(time);
        tip.style.left  = `${frac * 100}%`;
        tip.style.display = '';
      }
      if (commit) this.seek(time);
    };

    const beginScrub = (e) => {
      if (this.State.duration <= 0) return;
      dragging   = true;
      wasPlaying = this.State.isPlaying;
      if (wasPlaying) this.pause();
      applyFrac(getFrac(e));
      e.preventDefault();
    };

    const commitScrub = (e) => {
      if (!dragging) return;
      dragging = false;
      applyFrac(getFrac(e), true);
      if (tip) tip.style.display = 'none';
      if (wasPlaying) this.play();
    };

    scrub.addEventListener('pointerdown', beginScrub);
    document.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      applyFrac(getFrac(e));
    });
    document.addEventListener('pointerup', commitScrub);
    document.addEventListener('pointercancel', () => {
      if (!dragging) return;
      dragging = false;
      if (tip) tip.style.display = 'none';
      if (wasPlaying) this.play();
    });

    // Hover tooltip (not dragging)
    scrub.addEventListener('pointermove', (e) => {
      if (dragging || this.State.duration <= 0) return;
      const frac = getFrac(e);
      if (tip) {
        tip.textContent  = fmtDur(frac * this.State.duration);
        tip.style.left   = `${frac * 100}%`;
        tip.style.display = '';
      }
    });
    scrub.addEventListener('pointerleave', () => {
      if (!dragging && tip) tip.style.display = 'none';
    });


    // Keyboard on the scrub (ARIA role=slider)
    scrub.addEventListener('keydown', (e) => {
      if (this.State.duration <= 0) return;
      const step = this.State.duration * 0.02;
      if (e.key === 'ArrowRight' || e.key === 'ArrowUp')   this.seek(this.State.currentTime + step);
      if (e.key === 'ArrowLeft'  || e.key === 'ArrowDown')  this.seek(this.State.currentTime - step);
      if (e.key === 'Home') this.seek(0);
      if (e.key === 'End')  this.seek(this.State.duration);
    });
  }

  // ── Private: click-track scheduler ───────────────────────────────────────

  _medianInterval(beats, fromPos, n) {
    let i = 0;
    while (i < beats.length - 1 && beats[i] < fromPos) i++;
    const slice = beats.slice(i, i + Math.max(2, n + 1));
    if (slice.length < 2) return 60 / (this.State.beats?.bpm || 120);
    const diffs = [];
    for (let k = 0; k < slice.length - 1; k++) diffs.push(slice[k+1] - slice[k]);
    diffs.sort((a,b) => a-b);
    return diffs[Math.floor(diffs.length/2)];
  }

  _computeCountInDuration(countInBars) {
    const beats = this.State.beats?.beats;
    if (!beats?.length) return 0;
    const bpb = this.State.metronomeBeatsPerBar > 0 ? this.State.metronomeBeatsPerBar : 4;
    return countInBars * bpb * this._medianInterval(beats, this.State.currentTime, bpb);
  }

  _scheduleClick(atTime, level) {
    if (!this._ctx || !this._metro.gainNode) return;
    const [freq, peak] = level===2 ? [ACCENT_FREQ,ACCENT_PEAK] : level===1 ? [GROUP_FREQ,GROUP_PEAK] : [CLICK_FREQ,CLICK_PEAK];
    const osc = this._ctx.createOscillator();
    const env = this._ctx.createGain();
    osc.frequency.value = freq;
    osc.connect(env); env.connect(this._metro.gainNode);
    const ae = atTime + CLICK_ATTACK, de = atTime + CLICK_DECAY;
    env.gain.setValueAtTime(0.0001, atTime);
    env.gain.exponentialRampToValueAtTime(peak, ae);
    env.gain.exponentialRampToValueAtTime(0.0001, de);
    osc.start(atTime); osc.stop(de + 0.01);
  }

  _beatLevel(idx) {
    const bpb = this.State.metronomeBeatsPerBar;
    if (bpb === 0) return 0;
    const perBar = bpb > 0 ? bpb : 4;
    const pos    = idx % perBar;
    if (pos === 0) return 2;
    if ((perBar >= 6 && pos === Math.floor(perBar/2)) || (perBar === 4 && pos === 2)) return 1;
    return 0;
  }

  _applyMultiplier(beats, mult) {
    if (mult === 2.0) {
      const out = [];
      for (let i = 0; i < beats.length - 1; i++) { out.push(beats[i]); out.push((beats[i]+beats[i+1])/2); }
      if (beats.length) out.push(beats[beats.length-1]);
      return out;
    }
    if (mult === 0.5) return beats.filter((_,i) => i%2===0);
    return [...beats];
  }

  _gridTimeToCtx(t) { return this._startOffset + (t - this._posOffset) / this.State.playbackRate; }

  _startMetronome() {
    this._stopMetronome();
    if (!this.State.beats?.beats?.length) { setText('t-metro-note','No beat data'); return; }
    setText('t-metro-note','');
    if (this._ctx.state === 'suspended') this._ctx.resume();
    if (this._metro.gainNode) this._metro.gainNode.gain.value = this.State.metronomeVolume;
    const grid = this._applyMultiplier(this.State.beats.beats, this.State.metronomeMultiplier || 1.0);
    const pos  = this.State.currentTime;
    let idx = 0;
    while (idx < grid.length - 1 && grid[idx] < pos) idx++;
    this._metro.nextBeatIdx = idx;
    this._metro._grid = grid;
    const tick = () => {
      if (!this.State.isPlaying || !this.State.metronomeEnabled) { this._stopMetronome(); return; }
      const ahead = this._ctx.currentTime + this._metro.scheduleAheadSec;
      while (this._metro.nextBeatIdx < this._metro._grid.length &&
             this._gridTimeToCtx(this._metro._grid[this._metro.nextBeatIdx]) < ahead) {
        const atTime = Math.max(this._gridTimeToCtx(this._metro._grid[this._metro.nextBeatIdx]), this._ctx.currentTime);
        this._scheduleClick(atTime, this._beatLevel(this._metro.nextBeatIdx));
        this._metro.nextBeatIdx++;
      }
    };
    tick();
    this._metro.timerId = setInterval(tick, this._metro.lookaheadMs);
  }

  _startMetronomeCountIn(countInBars, leadIn) {
    if (!this._ctx || !this._metro.gainNode) return;
    if (this._ctx.state === 'suspended') this._ctx.resume();
    if (this._metro.gainNode) this._metro.gainNode.gain.value = this.State.metronomeVolume;
    const bpb      = this.State.metronomeBeatsPerBar > 0 ? this.State.metronomeBeatsPerBar : 4;
    const interval = leadIn / (countInBars * bpb);
    const nowCtx   = this._ctx.currentTime;
    for (let i = 0; i < countInBars * bpb; i++) {
      const pos = i % bpb;
      this._scheduleClick(nowCtx + i * interval, pos===0 ? 2 : (pos===Math.floor(bpb/2) ? 1 : 0));
    }
    setTimeout(() => { if (this.State.isPlaying && this.State.metronomeEnabled) this._startMetronome(); }, leadIn*1000);
  }

  _stopMetronome() {
    if (this._metro.timerId) { clearInterval(this._metro.timerId); this._metro.timerId = null; }
    this._metro._grid = null; this._metro.nextBeatIdx = 0;
  }

  // ── Private: rAF ──────────────────────────────────────────────────────────

  _startRaf() {
    this._stopRaf();
    const tick = () => {
      if (!this.State.isPlaying) return;
      const pos = this._getPosition();
      if (this.State.loopEnabled && pos >= this.State.loopEnd && this.State.loopEnd > 0) {
        this._stopSources(); this._stopMetronome();
        this._posOffset = this.State.loopStart; this._startOffset = this._ctx.currentTime;
        this._startPlayback(this.State.loopStart);
        if (this.State.metronomeEnabled) this._startMetronome();
        return;
      }
      if (pos >= this.State.duration && this.State.duration > 0) { this.stop(); this._updateTransportUI(); return; }
      this.State.currentTime = pos;
      this._updatePlayhead(pos);
      this._updateTransportUI();
      if (typeof this._onTick === 'function') this._onTick(pos);
      this._rafId = requestAnimationFrame(tick);
    };
    this._rafId = requestAnimationFrame(tick);
  }

  _stopRaf() { if (this._rafId) { cancelAnimationFrame(this._rafId); this._rafId = null; } }

  // ── Private: waveform ─────────────────────────────────────────────────────

  _buildMixer(stems, allPeaks) {
    if (!this._mixerEl) return;
    this._mixerEl.innerHTML   = '';
    if (this._container) this._container.innerHTML = '';

    if (!document.getElementById('mwtn-mixer-style')) {
      const st = document.createElement('style'); st.id = 'mwtn-mixer-style';
      st.textContent = `
        .mixer-row{display:flex;align-items:center;height:var(--lane-h,86px);border-bottom:1px solid var(--border);gap:8px;padding:0 10px;position:relative}
        .mixer-stem-icon{width:28px;height:28px;border-radius:6px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
        .mixer-stem-label{font-size:11px;font-weight:600;width:52px;flex-shrink:0;text-transform:capitalize;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .mixer-ms-group{display:flex;flex-direction:column;gap:3px;flex-shrink:0}
        .mixer-ms-btn{width:20px;height:18px;border-radius:4px;font-size:9px;font-weight:700;font-family:var(--font-mono);background:var(--panel-2);border:1px solid var(--border);color:var(--muted);display:flex;align-items:center;justify-content:center;cursor:pointer;transition:background 80ms,color 80ms}
        .mixer-ms-btn.muted{background:rgba(59,130,246,.18);color:#60a5fa;border-color:rgba(59,130,246,.4)}
        .mixer-ms-btn.soloed{background:rgba(244,183,64,.18);color:var(--accent);border-color:rgba(244,183,64,.4)}
        .mixer-fader{-webkit-appearance:none;appearance:none;height:4px;border-radius:2px;flex:1;min-width:40px;background:linear-gradient(to right,var(--track-fill) 0%,var(--track-fill) calc(var(--val,67%)),rgba(255,255,255,0.08) calc(var(--val,67%)));cursor:ew-resize}
        .mixer-fader::-webkit-slider-thumb{-webkit-appearance:none;width:14px;height:14px;border-radius:50%;background:var(--track-fill);border:2px solid rgba(0,0,0,0.35);box-shadow:0 0 0 1px rgba(255,255,255,0.18)}
        .mixer-fader::-moz-range-thumb{width:14px;height:14px;border-radius:50%;background:var(--track-fill);border:2px solid rgba(0,0,0,0.35)}
        .mixer-vol-readout{font-size:10px;font-family:var(--font-mono);color:var(--muted);width:30px;text-align:right;flex-shrink:0}
        .stem-load-bar-wrap{position:absolute;bottom:0;left:0;right:0;height:2px;background:rgba(255,255,255,0.06)}
        .stem-load-bar{height:100%;width:0%;background:var(--accent);transition:width 0.1s;border-radius:1px}
      `;
      document.head.appendChild(st);
    }

    stems.forEach(name => {
      const color = STEM_COLORS[name] || '#888';
      const icon  = STEM_ICONS[name]  || STEM_ICONS.other;
      const label = name.replace('_',' ');

      // Mixer row
      const row = document.createElement('div');
      row.className = 'mixer-row'; row.dataset.stem = name;
      row.innerHTML = `
        <div class="mixer-stem-icon" style="background:color-mix(in srgb,${color} 18%,transparent);color:${color}">${icon}</div>
        <span class="mixer-stem-label" style="color:${color}">${label}</span>
        <div class="mixer-ms-group">
          <button class="mixer-ms-btn mute-btn" data-stem="${name}" aria-pressed="false" title="Mute">M</button>
          <button class="mixer-ms-btn solo-btn" data-stem="${name}" aria-pressed="false" title="Solo">S</button>
        </div>
        <input type="range" class="mixer-fader" min="0" max="1.5" step="0.01" value="1" data-stem="${name}" style="--track-fill:${color}">
        <span class="mixer-vol-readout">100%</span>
        <div class="vu-mini-wrap"><canvas class="vu-mini" id="vu-mini-${name}" width="4" height="72" aria-hidden="true"></canvas></div>
        <div class="stem-load-bar-wrap"><div class="stem-load-bar" id="stem-load-bar-${name}"></div></div>
      `;
      this._mixerEl.appendChild(row);

      const fader   = row.querySelector('.mixer-fader');
      const readout = row.querySelector('.mixer-vol-readout');
      fader.addEventListener('input', () => {
        const vol = parseFloat(fader.value);
        readout.textContent = `${Math.round(vol*100)}%`;
        this.setStemVolume(name, vol);
      });

      row.querySelector('.mute-btn').addEventListener('click', (e) => {
        const btn = e.currentTarget;
        const now = !(this.State.mixer[name]?.muted);
        this.setStemMuted(name, now);
        btn.classList.toggle('muted', now); btn.setAttribute('aria-pressed', now);
      });

      row.querySelector('.solo-btn').addEventListener('click', (e) => {
        const btn = e.currentTarget;
        const now = !(this.State.mixer[name]?.soloed);
        this.setStemSoloed(name, now);
        this._mixerEl.querySelectorAll('.solo-btn').forEach(b => {
          const n = b.dataset.stem; const s = this.State.mixer[n]?.soloed||false;
          b.classList.toggle('soloed', s); b.setAttribute('aria-pressed', s);
        });
      });

      // Waveform lane
      const lane   = document.createElement('div');
      lane.className = 'wave-lane'; lane.dataset.stem = name;
      lane.style.cssText = `height:var(--lane-h,86px);border-bottom:1px solid var(--border);position:relative;overflow:hidden`;
      const canvas = document.createElement('canvas');
      canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%';
      lane.appendChild(canvas);
      this._container?.appendChild(lane);

      const peaks = allPeaks?.[name];
      if (peaks?.length) requestAnimationFrame(() => this._drawLaneWaveform(canvas, peaks, color));
    });
  }

  _extractPeaksFromBuffer(name, n=1500) {
    const stem = this._stems[name]; if (!stem?.buffer) return null;
    const data=stem.buffer.getChannelData(0), step=Math.max(1,Math.floor(data.length/n)), out=[];
    for(let i=0;i<n;i++){let lo=0,hi=0;for(let j=i*step;j<Math.min((i+1)*step,data.length);j++){if(data[j]<lo)lo=data[j];if(data[j]>hi)hi=data[j];}out.push([lo,hi]);}
    return out;
  }

  _drawLaneWaveform(canvas, peaks, color) {
    const pr=window.devicePixelRatio||1, w=canvas.offsetWidth||800, h=canvas.offsetHeight||86;
    canvas.width=w*pr; canvas.height=h*pr;
    const ctx=canvas.getContext('2d'); ctx.scale(pr,pr); ctx.clearRect(0,0,w,h);
    const mid=h/2, barW=w/peaks.length;
    const [r,g,b]=[parseInt(color.slice(1,3),16),parseInt(color.slice(3,5),16),parseInt(color.slice(5,7),16)];
    peaks.forEach(([lo,hi],i)=>{
      ctx.fillStyle=`rgba(${r},${g},${b},0.75)`;
      ctx.fillRect(Math.floor(i*barW),mid-hi*mid*.95,Math.max(1,Math.ceil(barW)-1),Math.max(1,(hi-lo)*mid*.95));
    });
  }

  _drawAllWaveforms(stems, allPeaks) {
    stems.forEach(name=>{
      const canvas=this._container?.querySelector(`.wave-lane[data-stem="${name}"] canvas`);
      if(!canvas) return;
      const peaks=allPeaks?.[name]||this._extractPeaksFromBuffer(name,1500);
      if(peaks?.length) requestAnimationFrame(()=>this._drawLaneWaveform(canvas,peaks,STEM_COLORS[name]||'#888'));
    });
  }

  _drawFooterWaveform(stems, allPeaks) {
    const canvas=this._footerWave; if(!canvas) return;
    const name=stems[0]; if(!name) return;
    const peaks=allPeaks?.[name]||this._extractPeaksFromBuffer(name,800); if(!peaks?.length) return;
    requestAnimationFrame(()=>{
      const pr=window.devicePixelRatio||1,w=canvas.offsetWidth||600,h=canvas.offsetHeight||40;
      canvas.width=w*pr; canvas.height=h*pr;
      const ctx=canvas.getContext('2d'); ctx.scale(pr,pr); ctx.clearRect(0,0,w,h);
      const mid=h/2,barW=w/peaks.length; ctx.fillStyle='rgba(244,183,64,0.45)';
      peaks.forEach(([lo,hi],i)=>ctx.fillRect(Math.floor(i*barW),mid-hi*mid*.9,Math.max(1,Math.ceil(barW)-1),Math.max(1,(hi-lo)*mid*.9)));
    });
  }

  _clearWaveforms() {
    if(this._container) this._container.innerHTML='';
    if(this._mixerEl)   this._mixerEl.innerHTML='';
    if(this._footerWave){const c=this._footerWave.getContext('2d');c?.clearRect(0,0,this._footerWave.width,this._footerWave.height);}
    this._stems={};
    // Clear ruler ticks
    document.querySelectorAll('.beat-tick').forEach(e=>e.remove());
  }

  // ── Private: ruler beat marks ─────────────────────────────────────────────

  _drawRulerBeats() {
    const ruler = document.getElementById('ruler-time');
    if (!ruler || !this.State.beats?.beats?.length || !this.State.duration) return;
    // Remove stale ticks
    ruler.querySelectorAll('.beat-tick,.beat-bar-num-label').forEach(e => e.remove());

    const beats  = this.State.beats.beats;
    const bars   = this.State.beats.bars || [];
    const dur    = this.State.duration;

    // Map bar start times → bar number
    const barNumAt = {};
    bars.forEach((b, idx) => { barNumAt[b.start?.toFixed?.(3) ?? b.start] = b.bar_number ?? (idx + 1); });

    beats.forEach((t, i) => {
      const frac   = t / dur;
      const key    = t.toFixed(3);
      const isBar  = barNumAt[key] !== undefined || i === 0;
      const tick   = document.createElement('div');
      tick.className = `beat-tick${isBar ? ' beat-tick-bar' : ''}`;
      tick.style.left = `${frac * 100}%`;
      tick.dataset.beatIdx  = i;
      tick.dataset.beatTime = t;
      if (isBar) {
        const num = document.createElement('span');
        num.className   = 'beat-bar-num-label';
        num.textContent = barNumAt[key] ?? (Math.floor(i / (this.State.metronomeBeatsPerBar > 0 ? this.State.metronomeBeatsPerBar : 4)) + 1);
        tick.appendChild(num);
      }
      ruler.appendChild(tick);
    });
  }

  // ── Private: playhead ──────────────────────────────────────────────────────

  _updatePlayhead(pos) {
    const dur  = this.State.duration;
    const frac = dur > 0 ? Math.min(1, pos / dur) : 0;
    if (this._scrubFill) this._scrubFill.style.width = `${frac * 100}%`;
    const marker = document.querySelector('.playhead-marker');
    if (marker) marker.style.left = `${frac * 100}%`;
    const scrub = document.getElementById('footer-scrub');
    if (scrub) scrub.setAttribute('aria-valuenow', Math.round(pos));
  }

  _updateTransportUI() {
    const pos=this.State.currentTime, dur=this.State.duration;
    const fmt=s=>{ const m=Math.floor(s/60); return `${m}:${Math.floor(s%60).toString().padStart(2,'0')}`; };
    setText('footer-time-elapsed', fmt(pos));
    setText('footer-time-total',   fmt(dur));
    this._updatePlayhead(pos);
    const btn = document.getElementById('t-play');
    if (btn) { btn.classList.toggle('playing', this.State.isPlaying); btn.setAttribute('aria-label', this.State.isPlaying ? 'Pause' : 'Play'); }
  }

  // ── Private: analysis ─────────────────────────────────────────────────────

  _populateAnalysis(manifest, beats, keyInfo, presence) {
    const keyStr = manifest.key || keyInfo?.key;
    if (keyStr) { const p=keyStr.split(' '); setText('summary-key',p.slice(0,-1).join(' ')||keyStr); setText('summary-scale',p.slice(-1)[0]||''); }
    const scale = manifest.scale || keyInfo?.scale;
    if (scale) setText('summary-scale-name', scale==='Natural Minor'?'Aeolian / Natural Minor':scale);
    const bpm = manifest.bpm || beats?.bpm;
    if (bpm) setText('summary-bpm', Math.round(bpm));
    const dur = beats?.duration ?? manifest.duration_secs ?? this._longestStemDuration();
    if (dur > 0) { setText('summary-duration', fmtDur(dur)); if (dur > this.State.duration) this.State.duration = dur; }

    const setMeta = (id, val, metaAttr) => {
      if (val != null) { setText(id, val); document.querySelector(`[data-meta="${metaAttr}"]`)?.classList.remove('meta-card--unavailable'); }
      else             { setText(id,'n/a'); document.querySelector(`[data-meta="${metaAttr}"]`)?.classList.add('meta-card--unavailable'); }
    };
    setMeta('summary-lufs', keyInfo?.lufs != null ? `${parseFloat(keyInfo.lufs).toFixed(1)}` : manifest.lufs != null ? `${parseFloat(manifest.lufs).toFixed(1)}` : null, 'lufs');
    const dr = keyInfo?.dynamic_range ?? manifest.dynamic_range;
    if (dr != null) { setText('summary-dr', parseFloat(dr).toFixed(1)); setText('summary-dr-label', dr>14?'Wide':dr>8?'Medium':'Narrow'); document.querySelector('[data-meta="dr"]')?.classList.remove('meta-card--unavailable'); }
    else { setText('summary-dr','n/a'); setText('summary-dr-label',''); document.querySelector('[data-meta="dr"]')?.classList.add('meta-card--unavailable'); }
    const stab = beats?.tempo_stability ?? manifest.tempo_stability;
    if (stab != null) { setText('summary-stability',`${stab}%`); setText('summary-stability-label',stab>=90?'Very Stable':stab>=70?'Stable':'Variable'); document.querySelector('[data-meta="stability"]')?.classList.remove('meta-card--unavailable'); }
    else { setText('summary-stability','n/a'); setText('summary-stability-label',''); document.querySelector('[data-meta="stability"]')?.classList.add('meta-card--unavailable'); }

    const presenceData = presence ?? manifest.stem_presence ?? {};
    document.querySelectorAll('[id^="pct-"]').forEach(el => { const n=el.id.replace('pct-',''); if(presenceData[n]!=null) el.textContent=`${presenceData[n]}%`; });
    setText('pct-stems', manifest.stems?.length ?? '—');

    setText('t-meta-duration', dur > 0 ? fmtDur(dur) : '—');
    const sc = (manifest.stems || []).length;
    const chip = document.getElementById('t-stems-chip'); if(chip) chip.textContent=`${sc} stem${sc!==1?'s':''}`;
    if (dur > 0) setText('footer-time-total', fmtDur(dur));
  }

  _resetAnalysis() {
    ['summary-key','summary-bpm','summary-lufs','summary-peak','summary-duration',
     'summary-scale','summary-scale-name','summary-dr','summary-dr-label',
     'summary-stability','summary-stability-label'].forEach(id=>setText(id,'—'));
    document.querySelectorAll('[id^="pct-"]').forEach(el=>{ el.textContent='—'; });
    document.querySelectorAll('.meta-card--unavailable').forEach(c=>c.classList.remove('meta-card--unavailable'));
  }

  _updateNowPlaying(manifest) {
    setText('title', manifest.title || manifest.song_id);
    const src = document.getElementById('track-source'); if(src) src.textContent = manifest.separation_model || 'colab';
  }

  _enableTransport() {
    ['t-play','t-stop','t-loop','t-metro','t-pitch-up','t-pitch-down','t-pitch-reset'].forEach(id=>{
      const el=document.getElementById(id); if(el) el.disabled=false;
    });
    document.querySelector('#t-metro-panel')?.classList.remove('unavailable');
    const dur=this.State.duration, m=Math.floor(dur/60), s=Math.floor(dur%60).toString().padStart(2,'0');
    setText('footer-time-total', `${m}:${s}`);
    const scrub = document.getElementById('footer-scrub');
    if (scrub) { scrub.setAttribute('aria-valuemin','0'); scrub.setAttribute('aria-valuemax', Math.round(dur)); }
  }

  // ── Private: UI helpers ───────────────────────────────────────────────────

  _showLoading(msg){ if(this._loadingEl) this._loadingEl.classList.remove('hidden'); this._setPhrase(msg||'Loading…'); if(this._jobEl) this._jobEl.classList.remove('hidden'); setText('job-stage',msg||''); }
  _setPhrase(msg)  { if(this._phraseEl) this._phraseEl.textContent=msg; setText('job-stage',msg); }
  _hideLoading()   { this._loadingEl?.classList.add('hidden'); this._jobEl?.classList.add('hidden'); }
  _showError(msg)  { if(!this._errorEl) return; if(msg){ this._errorEl.textContent=msg; this._errorEl.classList.remove('hidden'); } else { this._errorEl.textContent=''; this._errorEl.classList.add('hidden'); } }

  _bindExportUI() {
    document.querySelectorAll('.export-fmt').forEach(btn=>{
      btn.addEventListener('click',()=>{
        document.querySelectorAll('.export-fmt').forEach(b=>{b.classList.remove('active');b.setAttribute('aria-checked','false');});
        btn.classList.add('active'); btn.setAttribute('aria-checked','true');
        this._exportFmt = btn.id.replace('t-fmt-','');
      });
    });
    document.getElementById('t-export-click')?.addEventListener('change',e=>{ this._exportClick=e.target.checked; });
    document.getElementById('t-export-loop-only')?.addEventListener('change',e=>{ this.State.exportLoopOnly=e.target.checked; });
  }
}
