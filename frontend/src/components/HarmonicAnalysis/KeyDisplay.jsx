import { useEffect, useMemo, useState } from 'react';

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
const MODES = ['major', 'minor', 'dorian', 'mixolydian', 'phrygian'];

function activeEntry(keyMap, currentTime) {
  return [...keyMap].reverse().find((entry) => (
    entry.start_s <= currentTime && (entry.end_s == null || currentTime < entry.end_s)
  )) || keyMap[0] || null;
}

function formatSeconds(value) {
  return value == null ? 'end' : `${Number(value).toFixed(0)}s`;
}

export default function KeyDisplay({ keyMap = [], currentTime = 0, songId, onKeyOverride }) {
  const entry = useMemo(() => activeEntry(keyMap, currentTime), [keyMap, currentTime]);
  const [editing, setEditing] = useState(false);
  const [tonic, setTonic] = useState(entry?.tonic || 'C');
  const [mode, setMode] = useState(entry?.mode || 'major');

  useEffect(() => {
    if (entry) {
      setTonic(entry.tonic);
      setMode(entry.mode);
    }
  }, [entry?.tonic, entry?.mode]);

  if (!entry) return <section className="key-display"><span className="harmonic-muted">No key analysis</span></section>;

  const confidence = Math.round(Math.max(0, Math.min(1, Number(entry.confidence || 0))) * 100);
  const applyOverride = () => {
    onKeyOverride?.(tonic, mode, currentTime, null);
    setEditing(false);
  };

  return (
    <section className="key-display" aria-label="Detected key">
      <div className="key-display__row">
        <div>
          <span className="key-display__label">Key</span>
          <strong className="key-display__name">{entry.tonic} {entry.mode}</strong>
          {entry.manually_overridden && <span className="key-lock" title="Manually overridden">Locked</span>}
          <span className="key-display__confidence">• {confidence}%</span>
        </div>
        <button type="button" className="harmonic-toggle" onClick={() => setEditing((open) => !open)}>
          {editing ? 'Cancel' : 'Override'}
        </button>
      </div>
      {editing && (
        <div className="key-override" role="group" aria-label="Key override controls">
          <select value={tonic} onChange={(event) => setTonic(event.target.value)} aria-label="Override tonic">
            {NOTE_NAMES.map((note) => <option key={note} value={note}>{note}</option>)}
          </select>
          <select value={mode} onChange={(event) => setMode(event.target.value)} aria-label="Override mode">
            {MODES.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <button type="button" onClick={applyOverride}>Apply</button>
        </div>
      )}
      {keyMap.length > 1 && (
        <div className="key-modulations" aria-label="Key changes">
          {keyMap.map((item) => (
            <span className="key-modulation" key={`${item.start_s}-${item.tonic}-${item.mode}`}>
              {formatSeconds(item.start_s)}–{formatSeconds(item.end_s)}: {item.tonic} {item.mode}
            </span>
          ))}
        </div>
      )}
      <span className="sr-only">Song: {songId}</span>
    </section>
  );
}
