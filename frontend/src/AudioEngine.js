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
    this.playbackRate = 1.0;
    this.loopStart = null;
    this.loopEnd = null;
    this.duration = 0;
    this._onEndedCallback = null;
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
    this.pause();
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
    source.playbackRate.value = this.playbackRate;
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
    this.isPlaying = true;
    this._applyGains();
  }

  pause() {
    if (!this.isPlaying) return;

    // Capture position BEFORE stopping -- stopping a source doesn't
    // preserve "where it was," we have to compute that from the clock
    // first and stash it as the new startOffset.
    this.startOffset = this.getCurrentTime();

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

  seek(timeSeconds) {
    const clamped = Math.max(0, Math.min(timeSeconds, this.duration));
    const wasPlaying = this.isPlaying;
    if (wasPlaying) this.pause();
    this.startOffset = clamped;
    if (wasPlaying) this.play(clamped);
  }

  getCurrentTime() {
    if (!this.isPlaying) return this.startOffset;
    const wallClockElapsed = this.context.currentTime - this.startTime;
    return this.startOffset + wallClockElapsed * this.playbackRate;
  }

  /**
   * Changing playbackRate on a node that's already scheduled is technically
   * supported live, but our getCurrentTime() math assumes a constant rate
   * since startTime. Rather than adding a rate-change-history log to
   * getCurrentTime, we just restart all sources at the current position
   * with the new rate -- one frame of scheduling overhead, and the sync
   * math stays simple and correct.
   */
  setPlaybackRate(rate) {
    this.playbackRate = rate;
    if (this.isPlaying) {
      const pos = this.getCurrentTime();
      this.pause();
      this.play(pos);
    }
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
