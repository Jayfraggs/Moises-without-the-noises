/**
 * AudioEngine
 *
 * Loads multiple audio stems (vocals/drums/bass/other) as decoded
 * AudioBuffers and plays them back sample-accurately synced off a single
 * AudioContext clock, with per-stem mute/solo, A-B looping, and speed
 * control.
 *
 * KNOWN LIMITATION -- read before assuming speed control is "done":
 * setPlaybackRate() uses AudioBufferSourceNode.playbackRate, which is the
 * native Web Audio way to change speed. It is sample-accurate and keeps
 * all stems perfectly in sync with each other, but it ALSO shifts pitch
 * (slower = lower pitch, faster = higher pitch) -- this is standard
 * playback-rate behavior, not a bug. True pitch-preserving time-stretch
 * requires a phase vocoder or a library like soundtouchjs, which processes
 * each stem through its own ScriptProcessor/AudioWorklet chain. That's a
 * legitimate v2 upgrade, but wiring 4 independent time-stretch processors
 * while keeping them sample-locked to each other is a meaningfully harder
 * problem than what's implemented here, and I didn't want to ship that
 * integration untested. If you need pitch-preserving speed for practice,
 * that's the next thing to build -- this file's structure (one GainNode
 * per stem, all fed from a shared clock) is set up so you can swap
 * AudioBufferSourceNode for a PitchShifter node per stem without
 * restructuring anything else.
 *
 * SYNC MODEL:
 * `startTime` = context.currentTime when the current playback segment began.
 * `startOffset` = the song-position (seconds) that playback segment started
 * at. getCurrentTime() derives position from real elapsed time * rate, so
 * there's no per-frame drift accumulation -- every pause/seek/rate-change
 * resets both anchors together. This is the same pattern used by most
 * Web Audio scheduling code; the alternative (incrementing a counter every
 * frame) drifts over long playback and is why that's avoided here.
 */

export class AudioEngine {
  constructor() {
    this.context = new (window.AudioContext || window.webkitAudioContext)();
    this.stems = {}; // name -> { buffer, gainNode, sourceNode, muted, soloed, volume }
    this.startTime = 0;
    this.startOffset = 0;
    this.isPlaying = false;
    this._playbackRate = 1.0;
    this.loopStart = null;
    this.loopEnd = null;
    this.duration = 0;
    this._onEndedCallback = null;

    this._beatTimestamps = [];
    this._nextBeatIndex = 0;
    this._playStartContextTime = 0;
    this._playStartSongOffset = 0;
    this._metronomeEnabled = false;
    this._metronomeVolume = 0.7;
    this._metronomeIntervalId = null;
    this._metronomeLookaheadSeconds = 0.1;
    this._metronomeGainNode = this.context.createGain();
    this._metronomeGainNode.gain.value = 0;
    this._metronomeGainNode.connect(this.context.destination);
  }

  async loadStem(name, url) {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to fetch stem '${name}': ${response.status}`);
    }
    const arrayBuffer = await response.arrayBuffer();
    const audioBuffer = await this.context.decodeAudioData(arrayBuffer);

    const gainNode = this.context.createGain();
    gainNode.connect(this.context.destination);

    this.stems[name] = {
      buffer: audioBuffer,
      gainNode,
      sourceNode: null,
      muted: false,
      soloed: false,
      volume: 1.0,
    };

    this.duration = Math.max(this.duration, audioBuffer.duration);
  }

  getStemNames() {
    return Object.keys(this.stems);
  }

  loadBeats(beatsData) {
    this._beatTimestamps = Array.isArray(beatsData?.beats) ? beatsData.beats.slice() : [];
    this._nextBeatIndex = this._getNextBeatIndex(this.startOffset);
    if (this.isPlaying && this._metronomeEnabled) {
      this._startMetronomeScheduler();
    }
  }

  setMetronomeEnabled(enabled) {
    this._metronomeEnabled = !!enabled;
    if (!this._metronomeEnabled) {
      this._clearMetronomeScheduler();
      this._metronomeGainNode.gain.setTargetAtTime(0, this.context.currentTime, 0.01);
      return;
    }

    if (this.isPlaying) {
      this._startMetronomeScheduler();
    }
  }

  setMetronomeVolume(volume) {
    this._metronomeVolume = Math.max(0, Math.min(1, Number(volume) || 0));
    const target = this._metronomeEnabled ? this._metronomeVolume : 0;
    this._metronomeGainNode.gain.setTargetAtTime(target, this.context.currentTime, 0.01);
  }

  _getNextBeatIndex(offset) {
    let i = 0;
    while (i < this._beatTimestamps.length && this._beatTimestamps[i] < offset) {
      i += 1;
    }
    return i;
  }

  _clearMetronomeScheduler() {
    if (this._metronomeIntervalId !== null) {
      clearInterval(this._metronomeIntervalId);
      this._metronomeIntervalId = null;
    }
  }

  _scheduleMetronomeClick(when) {
    const oscillator = this.context.createOscillator();
    const gainNode = this.context.createGain();

    oscillator.type = 'sine';
    oscillator.frequency.setValueAtTime(1000, when);

    gainNode.gain.setValueAtTime(0, when);
    gainNode.gain.linearRampToValueAtTime(this._metronomeVolume, when + 0.002);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, when + 0.01);

    oscillator.connect(gainNode);
    gainNode.connect(this._metronomeGainNode);

    oscillator.start(when);
    oscillator.stop(when + 0.01);
  }

  _startMetronomeScheduler() {
    this._clearMetronomeScheduler();

    if (!this.isPlaying || !this._metronomeEnabled || this._beatTimestamps.length === 0) {
      return;
    }

    this._metronomeIntervalId = setInterval(() => {
      if (!this.isPlaying || !this._metronomeEnabled) {
        return;
      }

      const currentContextTime = this.context.currentTime;
      const lookaheadEndTime = currentContextTime + this._metronomeLookaheadSeconds;

      while (this._nextBeatIndex < this._beatTimestamps.length) {
        const beatOffset = this._beatTimestamps[this._nextBeatIndex];
        const scheduledContextTime = this._playStartContextTime + (beatOffset - this._playStartSongOffset);

        if (scheduledContextTime < currentContextTime - 0.02) {
          this._nextBeatIndex += 1;
          continue;
        }

        if (scheduledContextTime <= lookaheadEndTime) {
          this._scheduleMetronomeClick(scheduledContextTime);
          this._nextBeatIndex += 1;
          continue;
        }

        break;
      }
    }, 25);
  }

  /**
   * Tears down all currently loaded stems -- stops any playing sources,
   * disconnects their GainNodes from the graph, and clears state. Call
   * this before loading a different song into the same engine instance.
   * Without it, switching songs would silently overwrite same-named stem
   * entries (both songs have a "vocals" key) while leaving the previous
   * song's GainNode still connected to context.destination -- not audible
   * as a bug immediately, since it'd have no source feeding it, but it's
   * a real leak if you switch songs repeatedly in one session.
   */
  unloadAll() {
    this.stop();
    for (const stem of Object.values(this.stems)) {
      stem.gainNode.disconnect();
    }
    this.stems = {};
    this.duration = 0;
    this.startOffset = 0;
    this.loopStart = null;
    this.loopEnd = null;
  }

  _createAndStartSource(name, when, offset) {
    const stem = this.stems[name];
    const source = this.context.createBufferSource();
    source.buffer = stem.buffer;
    source.playbackRate.value = this._playbackRate;
    source.connect(stem.gainNode);

    if (this.loopStart !== null && this.loopEnd !== null) {
      source.loop = true;
      source.loopStart = this.loopStart;
      source.loopEnd = this.loopEnd;
    }

    source.start(when, offset);
    stem.sourceNode = source;
    return source;
  }

  play(offsetOverride = null) {
    if (this.isPlaying) return;
    if (Object.keys(this.stems).length === 0) return;

    const offset = offsetOverride !== null ? offsetOverride : this.startOffset;
    const when = this.context.currentTime;

    for (const name of Object.keys(this.stems)) {
      this._createAndStartSource(name, when, offset);
    }

    this.startTime = when;
    this.startOffset = offset;
    this._playStartContextTime = when;
    this._playStartSongOffset = offset;
    this._nextBeatIndex = this._getNextBeatIndex(offset);
    this.isPlaying = true;
    this._applyGains();
    this._startMetronomeScheduler();
  }

  pause() {
    if (!this.isPlaying) return;

    // Capture position BEFORE stopping -- stopping a source doesn't
    // preserve "where it was," we have to compute that from the clock
    // first and stash it as the new startOffset.
    this.startOffset = this.getCurrentTime();
    this._clearMetronomeScheduler();

    for (const stem of Object.values(this.stems)) {
      if (stem.sourceNode) {
        try {
          stem.sourceNode.stop();
        } catch {
          // Already stopped (e.g. hit natural end) -- fine to ignore.
        }
        stem.sourceNode = null;
      }
    }

    this.isPlaying = false;
  }

  stop() {
    this.pause();
  }

  seek(timeSeconds) {
    const clamped = Math.max(0, Math.min(timeSeconds, this.duration));
    const wasPlaying = this.isPlaying;
    if (wasPlaying) this.pause();
    this.startOffset = clamped;
    this._playStartContextTime = this.context.currentTime;
    this._playStartSongOffset = clamped;
    this._nextBeatIndex = this._getNextBeatIndex(clamped);
    if (wasPlaying) this.play(clamped);
  }

  getCurrentTime() {
    if (!this.isPlaying) return this.startOffset;
    const wallClockElapsed = this.context.currentTime - this.startTime;
    return this.startOffset + wallClockElapsed * this._playbackRate;
  }

  /**
   * Changing playbackRate on a node that's already scheduled is technically
   * supported live, but our getCurrentTime() math assumes a constant rate
   * since startTime. Rather than adding a rate-change-history log to
   * getCurrentTime, we just restart all sources at the current position
   * with the new rate -- one frame of scheduling overhead, and the sync
   * math stays simple and correct.
   */
  // NOTE: pitch shifts with speed — no pitch compensation implemented here.
  setPlaybackRate(rate) {
    const min = 0.25;
    const max = 2.0;
    const numeric = Number(rate);
    if (Number.isNaN(numeric)) {
      console.warn('setPlaybackRate: rate is not a number:', rate);
      return;
    }

    const clamped = Math.max(min, Math.min(max, numeric));
    if (clamped !== numeric) {
      console.warn(`setPlaybackRate: rate out of range [${min},${max}], clamped to ${clamped}`);
    }

    // Preserve current playhead position computed with OLD rate
    const wasPlaying = this.isPlaying;
    const currentPos = wasPlaying ? this.getCurrentTime() : this.startOffset;

    const oldRate = this._playbackRate;
    this._playbackRate = clamped;

    // If playing, atomically stop all sources and restart at same song offset
    if (wasPlaying) {
      // pause() will stop all sources and stash startOffset based on oldRate
      this.pause();
      // start again from the exact song position we computed above
      this.play(currentPos);
    }
  }

  getPlaybackRate() {
    return this._playbackRate;
  }

  setLoop(startSeconds, endSeconds) {
    this.loopStart = startSeconds;
    this.loopEnd = endSeconds;
    if (this.isPlaying) {
      const pos = this.getCurrentTime();
      this.pause();
      this.play(pos);
    }
  }

  clearLoop() {
    this.loopStart = null;
    this.loopEnd = null;
    if (this.isPlaying) {
      const pos = this.getCurrentTime();
      this.pause();
      this.play(pos);
    }
  }

  setMute(name, muted) {
    if (!this.stems[name]) return;
    this.stems[name].muted = muted;
    this._applyGains();
  }

  setSolo(name, soloed) {
    if (!this.stems[name]) return;
    this.stems[name].soloed = soloed;
    this._applyGains();
  }

  setVolume(name, volume) {
    if (!this.stems[name]) return;
    this.stems[name].volume = Math.max(0, Math.min(1, volume));
    this._applyGains();
  }

  _applyGains() {
    const anySoloed = Object.values(this.stems).some((s) => s.soloed);
    const now = this.context.currentTime;

    for (const stem of Object.values(this.stems)) {
      let gain = stem.volume;
      if (stem.muted) gain = 0;
      if (anySoloed && !stem.soloed) gain = 0;

      // setTargetAtTime with a short time constant avoids an audible click
      // from an instant gain jump -- a raw `gainNode.gain.value = gain`
      // assignment is what produces the classic "pop" when toggling mute
      // mid-playback.
      stem.gainNode.gain.setTargetAtTime(gain, now, 0.01);
    }
  }

  destroy() {
    this.pause();
    this.context.close();
  }
}
