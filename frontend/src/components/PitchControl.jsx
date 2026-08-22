import React, { useState } from 'react';

// PitchControl.jsx
// Props:
// - currentKey: string | null (e.g. "C major")
// - onSemitoneChange: (n: number) => void
// - onExportAtPitch: (n: number) => void

const PRESET_SEMITONES = [
  -12, -7, -5, -3, -2, -1, 0, 1, 2, 3, 5, 7, 12,
];

const INTERVAL_TITLES = {
  '-12': 'Octave down',
  '-7': 'Perfect 5th down',
  '-5': 'Perfect 4th down',
  '-3': 'Minor 3rd down',
  '-2': 'Major 2nd down',
  '-1': 'Semitone down',
  '0': 'Unison',
  '1': 'Semitone up',
  '2': 'Major 2nd up',
  '3': 'Minor 3rd up',
  '5': 'Perfect 4th up',
  '7': 'Perfect 5th up',
  '12': 'Octave up',
};

function normalizeNoteName(name) {
  if (!name) return null;
  const n = name.trim().replace(/♯/g, '#').replace(/♭/g, 'b');
  return n.charAt(0).toUpperCase() + n.slice(1);
}

function transposeKey(keyString, semitones) {
  if (!keyString) return null;
  const parts = keyString.split(/\s+/);
  if (parts.length === 0) return null;
  const rootRaw = parts[0];
  const mode = parts.length > 1 ? parts.slice(1).join(' ') : 'major';

  const flatsToSharps = { Db: 'C#', Eb: 'D#', Gb: 'F#', Ab: 'G#', Bb: 'A#' };
  const noteToIndex = {
    C: 0, 'C#': 1, D: 2, 'D#': 3, E: 4, F: 5, 'F#': 6, G: 7, 'G#': 8, A: 9, 'A#': 10, B: 11,
  };
  const indexToNote = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];

  let root = normalizeNoteName(rootRaw);
  if (!root) return null;
  if (flatsToSharps[root]) root = flatsToSharps[root];
  // Accept single-letter with trailing b or # as well (e.g., Bb -> Bb)
  if (!(root in noteToIndex)) {
    // Try uppercase first two chars
    const r2 = root.slice(0,2);
    if (r2 in flatsToSharps) root = flatsToSharps[r2];
  }
  if (!(root in noteToIndex)) return null;

  const baseIdx = noteToIndex[root];
  const outIdx = ((baseIdx + semitones) % 12 + 12) % 12;
  const outNote = indexToNote[outIdx];
  return `${outNote} ${mode}`;
}

export default function PitchControl({ currentKey = null, onSemitoneChange = () => {}, onExportAtPitch = () => {} }) {
  const [semitones, setSemitones] = useState(0);

  function handleSet(n) {
    setSemitones(n);
    if (typeof onSemitoneChange === 'function') onSemitoneChange(n);
  }

  const transposed = currentKey ? transposeKey(currentKey, semitones) : null;

  const containerStyle = {
    border: '1px solid #2b2b2b',
    padding: 12,
    borderRadius: 4,
    background: '#121212',
    color: '#f0f0f0',
    fontFamily: "Segoe UI, Helvetica Neue, Arial, sans-serif",
    maxWidth: 420,
  };

  const sliderRow = { display: 'flex', alignItems: 'center', gap: 12 };
  const presetsStyle = { display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 };
  const buttonStyle = { background: '#1f1f1f', color: '#f0f0f0', border: '1px solid #333', padding: '6px 8px', cursor: 'pointer' };
  const activeButtonStyle = { ...buttonStyle, background: '#2e2e2e', border: '1px solid #555' };

  return (
    <div style={containerStyle}>
      <div style={{ fontSize: 14, marginBottom: 8 }}>Pitch Changer</div>

      <div style={sliderRow}>
        <input
          type="range"
          min={-12}
          max={12}
          step={1}
          value={semitones}
          onChange={(e) => handleSet(parseInt(e.target.value, 10))}
          style={{ flex: 1 }}
        />
        <div style={{ width: 56, textAlign: 'center', fontFamily: 'SF Mono, Consolas, monospace' }}>
          {semitones > 0 ? `+${semitones}` : `${semitones}`}
        </div>
      </div>

      <div style={{ marginTop: 10, fontSize: 13 }}>
        <strong>Key:</strong> {currentKey ?? 'Key unknown'}
        <span style={{ marginLeft: 8, opacity: currentKey ? 1 : 0.6 }}>{currentKey && semitones !== 0 ? `→ ${transposed}` : ''}</span>
      </div>

      <div style={presetsStyle}>
        {PRESET_SEMITONES.map((s) => (
          <button
            key={s}
            title={INTERVAL_TITLES[String(s)]}
            onClick={() => handleSet(s)}
            style={s === semitones ? activeButtonStyle : buttonStyle}
          >
            {s > 0 ? `+${s}` : `${s}`}
          </button>
        ))}
      </div>

      <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
        <button
          onClick={() => onExportAtPitch(semitones)}
          disabled={semitones === 0}
          style={{ padding: '8px 12px', background: semitones === 0 ? '#2a2a2a' : '#e8a020', border: 'none', color: '#0f0f0f', cursor: semitones === 0 ? 'not-allowed' : 'pointer' }}
        >
          Export at this pitch
        </button>
        <button
          onClick={() => handleSet(0)}
          style={{ padding: '8px 12px', background: '#1f1f1f', border: '1px solid #333', color: '#f0f0f0' }}
        >
          Reset
        </button>
      </div>
    </div>
  );
}
