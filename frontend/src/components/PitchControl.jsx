import React, { useState } from 'react';

const PRESET_SEMITONES = [-12, -7, -5, -3, -2, -1, 0, 1, 2, 3, 5, 7, 12];

const INTERVAL_TITLES = {
  '-12': 'Octave down', '-7': 'Perfect 5th down', '-5': 'Perfect 4th down',
  '-3': 'Minor 3rd down', '-2': 'Major 2nd down', '-1': 'Semitone down',
  '0': 'Unison', '1': 'Semitone up', '2': 'Major 2nd up',
  '3': 'Minor 3rd up', '5': 'Perfect 4th up', '7': 'Perfect 5th up', '12': 'Octave up',
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
  const noteToIndex = { C: 0, 'C#': 1, D: 2, 'D#': 3, E: 4, F: 5, 'F#': 6, G: 7, 'G#': 8, A: 9, 'A#': 10, B: 11 };
  const indexToNote = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
  let root = normalizeNoteName(rootRaw);
  if (!root) return null;
  if (flatsToSharps[root]) root = flatsToSharps[root];
  if (!(root in noteToIndex)) {
    const r2 = root.slice(0, 2);
    if (r2 in flatsToSharps) root = flatsToSharps[r2];
  }
  if (!(root in noteToIndex)) return null;
  const baseIdx = noteToIndex[root];
  const outIdx = ((baseIdx + semitones) % 12 + 12) % 12;
  return `${indexToNote[outIdx]} ${mode}`;
}

export default function PitchControl({ currentKey = null, onSemitoneChange = () => {}, onExportAtPitch = () => {} }) {
  const [semitones, setSemitones] = useState(0);

  function handleSet(n) {
    setSemitones(n);
    if (typeof onSemitoneChange === 'function') onSemitoneChange(n);
  }

  const transposed = currentKey ? transposeKey(currentKey, semitones) : null;

  return (
    <div className="pitch-control">
      <div className="pitch-control__label">Pitch</div>

      <div className="pitch-control__slider-row">
        <input
          type="range"
          className="pitch-control__slider"
          min={-12}
          max={12}
          step={1}
          value={semitones}
          onChange={(e) => handleSet(parseInt(e.target.value, 10))}
          aria-label="Pitch semitones"
        />
        <span className="pitch-control__value">
          {semitones > 0 ? `+${semitones}` : `${semitones}`}st
        </span>
      </div>

      {currentKey && (
        <div className="pitch-control__key-row">
          <span className="pitch-control__key">{currentKey}</span>
          {semitones !== 0 && transposed && (
            <span className="pitch-control__key-arrow">→ {transposed}</span>
          )}
        </div>
      )}

      <div className="pitch-control__presets">
        {PRESET_SEMITONES.map((s) => (
          <button
            key={s}
            className={`pitch-control__preset ${s === semitones ? 'is-active' : ''}`}
            title={INTERVAL_TITLES[String(s)]}
            onClick={() => handleSet(s)}
          >
            {s > 0 ? `+${s}` : `${s}`}
          </button>
        ))}
      </div>

      <div className="pitch-control__actions">
        <button
          className="btn btn-secondary"
          onClick={() => handleSet(0)}
          disabled={semitones === 0}
        >
          Reset
        </button>
        <button
          className="btn btn-primary"
          onClick={() => onExportAtPitch(semitones)}
          disabled={semitones === 0}
        >
          Export at pitch
        </button>
      </div>
    </div>
  );
}
