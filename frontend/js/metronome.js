/** Sample-accurate browser metronome driven by beat timestamps. */
const LOOKAHEAD_SECONDS = 0.1;
const SCHEDULE_INTERVAL_MS = 25;
const CLICK_DURATION_SECONDS = 0.02;

export class Metronome {
  constructor(audioContext) {
    this.audioContext = audioContext;
    this.beats = [];
    this.nextBeatIndex = 0;
    this.offsetSeconds = 0;
    this.pendingStartOffset = null;
    this.volume = 1;
    this.enabled = true;
    this.running = false;
    this.timerId = null;
    this.scheduledNodes = new Set();
    this.beatCallbacks = new Set();
  }

  load(beatsData) {
    const beats = beatsData && Array.isArray(beatsData.beats) ? beatsData.beats : [];
    this.beats = beats.filter((beat) => Number.isFinite(Number(beat?.time_s)));
    this.beats.sort((left, right) => Number(left.time_s) - Number(right.time_s));
    this.nextBeatIndex = 0;
    if (this.pendingStartOffset !== null) {
      const offset = this.pendingStartOffset;
      this.pendingStartOffset = null;
      this.start(offset);
      return;
    }
    if (this.running) this._schedule();
  }

  start(offsetSeconds = 0) {
    if (!this.audioContext || !this.enabled) return;
    if (!this.beats.length) {
      this.pendingStartOffset = Math.max(0, Number(offsetSeconds) || 0);
      return;
    }
    this.stop();
    this.offsetSeconds = Math.max(0, Number(offsetSeconds) || 0);
    this.nextBeatIndex = this.beats.findIndex((beat) => Number(beat.time_s) >= this.offsetSeconds);
    if (this.nextBeatIndex < 0) this.nextBeatIndex = this.beats.length;
    this.running = true;
    this._schedule();
  }

  stop() {
    this.running = false;
    if (this.timerId !== null) {
      clearTimeout(this.timerId);
      this.timerId = null;
    }
    this.scheduledNodes.forEach(({ oscillator, gain }) => {
      try { oscillator.stop(); } catch (_) { /* already stopped */ }
      oscillator.disconnect();
      gain.disconnect();
    });
    this.scheduledNodes.clear();
  }

  setVolume(volume) {
    if (Number.isFinite(volume)) this.volume = Math.min(1, Math.max(0, volume));
  }

  setEnabled(enabled) {
    this.enabled = Boolean(enabled);
    if (!this.enabled) this.stop();
  }

  onBeat(callback) {
    if (typeof callback !== 'function') return () => {};
    this.beatCallbacks.add(callback);
    return () => this.beatCallbacks.delete(callback);
  }

  _schedule() {
    if (!this.running || !this.audioContext) return;
    const now = this.audioContext.currentTime;
    const horizon = now + LOOKAHEAD_SECONDS;
    while (this.nextBeatIndex < this.beats.length) {
      const beat = this.beats[this.nextBeatIndex];
      const beatTime = Number(beat.time_s);
      const audioTime = now + (beatTime - this.offsetSeconds);
      if (audioTime > horizon) break;
      if (audioTime >= now) {
        this._scheduleClick(audioTime, beat.beat_number === 1);
        this.beatCallbacks.forEach((callback) => callback({ ...beat }));
      }
      this.nextBeatIndex += 1;
    }
    if (this.nextBeatIndex < this.beats.length) {
      this.timerId = setTimeout(() => this._schedule(), SCHEDULE_INTERVAL_MS);
    } else {
      this.running = false;
      this.timerId = null;
    }
  }

  _scheduleClick(timeSeconds, isDownbeat) {
    const oscillator = this.audioContext.createOscillator();
    const gain = this.audioContext.createGain();
    oscillator.type = 'sine';
    oscillator.frequency.setValueAtTime(isDownbeat ? 1000 : 800, timeSeconds);
    gain.gain.setValueAtTime(this.volume, timeSeconds);
    gain.gain.linearRampToValueAtTime(0, timeSeconds + CLICK_DURATION_SECONDS);
    oscillator.connect(gain);
    gain.connect(this.audioContext.destination);
    const node = { oscillator, gain };
    this.scheduledNodes.add(node);
    oscillator.onended = () => {
      this.scheduledNodes.delete(node);
      oscillator.disconnect();
      gain.disconnect();
    };
    oscillator.start(timeSeconds);
    oscillator.stop(timeSeconds + CLICK_DURATION_SECONDS);
  }
}
