import { Fragment, useState } from 'react';

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
const QUAL_ABBR = {
  major: '', minor: 'm', diminished: 'dim', augmented: 'aug', dominant7: '7', major7: 'maj7',
  minor7: 'm7', diminished7: 'dim7', 'half-diminished7': 'ø7', sus2: 'sus2', sus4: 'sus4',
};
const QUALITIES = Object.keys(QUAL_ABBR);

function isActive(chord, currentTime) {
  return chord.start_time <= currentTime && (chord.end_time == null || currentTime < chord.end_time);
}

export default function ChordChart({ chords = [], currentTime = 0, duration = 0, onChordOverride }) {
  const [selectedId, setSelectedId] = useState(null);
  const [root, setRoot] = useState('C');
  const [quality, setQuality] = useState('major');
  const safeDuration = Math.max(Number(duration) || 0, 0.001);

  const selectChord = (chord) => {
    setSelectedId(chord.event_id);
    setRoot(chord.root);
    setQuality(chord.quality);
  };
  const applyOverride = () => {
    onChordOverride?.(selectedId, root, quality);
    setSelectedId(null);
  };

  return (
    <div className="chord-chart" aria-label="Chord chart">
      <div className="chord-chart__timeline">
        {chords.map((chord, index) => {
          const width = Math.max(0.5, ((Number(chord.end_time) - Number(chord.start_time)) / safeDuration) * 100);
          const previousEnd = index === 0 ? 0 : Number(chords[index - 1].end_time) || 0;
          const gapWidth = Math.max(0, ((Number(chord.start_time) - previousEnd) / safeDuration) * 100);
          const active = isActive(chord, currentTime);
          const lowConfidence = Number(chord.confidence) < 0.6;
          return (
            <Fragment key={chord.event_id || `${chord.start_time}-${chord.root}`}>
              {gapWidth > 0 && <span className="chord-gap" style={{ width: `${gapWidth}%` }} aria-hidden="true" />}
              <button
                type="button"
                className={`chord-block${active ? ' chord-block--active' : ''}${lowConfidence ? ' chord-block--low-confidence' : ''}`}
                style={{ width: `${width}%`, '--chord-hue': chord.quality === 'minor' ? 280 : chord.quality === 'dominant7' ? 30 : chord.quality === 'diminished' ? 0 : 210 }}
                onClick={() => selectChord(chord)}
                title={`${chord.root} ${chord.quality}`}
              >
                {chord.root}{QUAL_ABBR[chord.quality] ?? chord.quality}
              </button>
            </Fragment>
          );
        })}
      </div>
      {selectedId && (
        <div className="chord-override" role="group" aria-label="Chord override controls">
          <select value={root} onChange={(event) => setRoot(event.target.value)} aria-label="Chord root">
            {NOTE_NAMES.map((note) => <option key={note} value={note}>{note}</option>)}
          </select>
          <select value={quality} onChange={(event) => setQuality(event.target.value)} aria-label="Chord quality">
            {QUALITIES.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <button type="button" onClick={applyOverride}>Apply</button>
        </div>
      )}
    </div>
  );
}
