import { NoteDisplay } from './NoteDisplay.jsx';

const STEM_LABELS = {
  vocals: 'Vocals',
  drums: 'Drums',
  bass: 'Bass',
  guitar: 'Guitar',
  piano: 'Piano',
  other: 'Other',
};

// Drums never gets note detection attempted (see note_extraction.py) --
// don't even render a tuner display slot for it, rather than showing a
// permanent "n/a."
const NOTE_CAPABLE_STEMS = new Set(['vocals', 'bass', 'guitar', 'piano', 'other']);

export function StemChannel({
  name,
  muted,
  soloed,
  volume,
  notes,
  engine,
  isPlaying,
  onToggleMute,
  onToggleSolo,
  onVolumeChange,
}) {
  return (
    <div className={`channel-strip ${soloed ? 'is-soloed' : ''}`}>
      <div className="channel-strip__label">{STEM_LABELS[name] || name}</div>

      {NOTE_CAPABLE_STEMS.has(name) && (
        <NoteDisplay
          engine={engine}
          notes={notes}
          isPlaying={isPlaying}
          instrumentLabel={STEM_LABELS[name] || name}
        />
      )}

      <input
        type="range"
        className="channel-strip__fader"
        min="0"
        max="1"
        step="0.01"
        value={volume}
        orient="vertical"
        onChange={(e) => onVolumeChange(name, parseFloat(e.target.value))}
        aria-label={`${STEM_LABELS[name] || name} volume`}
      />

      <div className="channel-strip__buttons">
        <button
          className={`btn-mute ${muted ? 'is-active' : ''}`}
          onClick={() => onToggleMute(name)}
          aria-pressed={muted}
        >
          M
        </button>
        <button
          className={`btn-solo ${soloed ? 'is-active' : ''}`}
          onClick={() => onToggleSolo(name)}
          aria-pressed={soloed}
        >
          S
        </button>
      </div>
    </div>
  );
}
