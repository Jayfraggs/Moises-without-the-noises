import { useEffect, useRef, useState } from 'react';

function formatTime(seconds) {
  if (!isFinite(seconds)) return '0:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

const SPEED_STEPS = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0];

export function TransportControls({
  engine,
  isPlaying,
  onPlayPause,
  duration,
  metronomeEnabled,
  metronomeVolume,
  metronomeAvailable,
  onToggleMetronome,
  onMetronomeVolumeChange,
}) {
  const [position, setPosition] = useState(0);
  const [speed, setSpeed] = useState(1.0);
  const [loopStart, setLoopStart] = useState(null);
  const [loopEnd, setLoopEnd] = useState(null);
  const rafRef = useRef(null);

  useEffect(() => {
    const tick = () => {
      setPosition(engine.getCurrentTime());
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [engine]);

  const handleSeek = (e) => {
    const t = parseFloat(e.target.value);
    engine.seek(t);
    setPosition(t);
  };

  const handleSpeedChange = (e) => {
    const rate = parseFloat(e.target.value);
    setSpeed(rate);
    engine.setPlaybackRate(rate);
  };

  const markLoopStart = () => {
    const t = engine.getCurrentTime();
    setLoopStart(t);
    if (loopEnd !== null && t < loopEnd) {
      engine.setLoop(t, loopEnd);
    }
  };

  const markLoopEnd = () => {
    const t = engine.getCurrentTime();
    setLoopEnd(t);
    if (loopStart !== null && loopStart < t) {
      engine.setLoop(loopStart, t);
    }
  };

  const clearLoop = () => {
    setLoopStart(null);
    setLoopEnd(null);
    engine.clearLoop();
  };

  return (
    <div className="transport">
      <div className="transport__main-row">
        <button className="btn-transport-play" onClick={onPlayPause}>
          {isPlaying ? '\u23F8' : '\u25B6'}
        </button>

        <span className="transport__time">{formatTime(position)}</span>

        <input
          type="range"
          className="transport__seek"
          min="0"
          max={duration || 0}
          step="0.01"
          value={Math.min(position, duration || 0)}
          onChange={handleSeek}
        />

        <span className="transport__time">{formatTime(duration)}</span>
      </div>

      <div className="transport__sub-row">
        <div className="transport__speed-control">
          <label htmlFor="speed-select">Speed</label>
          <select id="speed-select" value={speed} onChange={handleSpeedChange}>
            {SPEED_STEPS.map((s) => (
              <option key={s} value={s}>
                {Math.round(s * 100)}%
              </option>
            ))}
          </select>
          {speed !== 1.0 && (
            <span className="transport__speed-note">pitch shifts at this speed</span>
          )}
        </div>

        <div className="transport__loop-control">
          <button onClick={markLoopStart}>Set A</button>
          <button onClick={markLoopEnd}>Set B</button>
          <button onClick={clearLoop} disabled={loopStart === null && loopEnd === null}>
            Clear loop
          </button>
          {loopStart !== null && loopEnd !== null && (
            <span className="transport__loop-range">
              {formatTime(loopStart)} \u2192 {formatTime(loopEnd)}
            </span>
          )}
        </div>

        <div className="transport__metronome-control">
          <button
            type="button"
            className={`btn-toggle ${metronomeEnabled ? 'is-active' : ''}`}
            onClick={onToggleMetronome}
            disabled={!metronomeAvailable}
            title={metronomeAvailable ? 'Metronome' : 'Beat data unavailable'}
            aria-pressed={metronomeEnabled}
          >
            Metronome
          </button>

          {metronomeEnabled && metronomeAvailable && (
            <label className="transport__metronome-volume">
              <span>Volume</span>
              <input
                type="range"
                min="0"
                max="1"
                step="0.01"
                value={metronomeVolume}
                onChange={(e) => onMetronomeVolumeChange(parseFloat(e.target.value))}
                aria-label="Metronome volume"
              />
            </label>
          )}
        </div>
      </div>
    </div>
  );
}
