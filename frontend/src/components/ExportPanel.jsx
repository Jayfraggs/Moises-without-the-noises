import { useEffect, useState } from 'react';
import { exportMix, triggerBrowserDownload } from '../api.js';

const STEM_LABELS = {
  vocals: 'Vocals',
  drums: 'Drums',
  bass: 'Bass',
  guitar: 'Guitar',
  piano: 'Piano',
  other: 'Other',
};

export default function ExportPanel({ songId, stems = [], currentGains = {}, onClose }) {
  const [gains, setGains] = useState({});
  const [prevGains, setPrevGains] = useState({});
  const [includeClick, setIncludeClick] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const map = {};
    stems.forEach((s) => {
      map[s] = typeof currentGains?.[s] === 'number' ? currentGains[s] : 1.0;
    });
    setGains(map);
    setPrevGains(map);
  }, [stems, currentGains]);

  function setGain(stem, value) {
    setGains((g) => ({ ...g, [stem]: value }));
  }

  function toggleMute(stem) {
    setGains((g) => {
      const cur = g[stem] ?? 1.0;
      if (cur > 0) {
        setPrevGains((p) => ({ ...p, [stem]: cur }));
        return { ...g, [stem]: 0 };
      }
      const restored = prevGains[stem] ?? 1.0;
      return { ...g, [stem]: restored };
    });
  }

  async function handleExport() {
    setExporting(true);
    setError(null);
    try {
      const blob = await exportMix(songId, gains, includeClick);
      const filename = `${songId}_mix.wav`;
      triggerBrowserDownload(blob, filename);
      // close panel after successful download
      onClose?.();
    } catch (err) {
      setError(err.message || 'Export failed');
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="export-panel">
      <div className="export-panel__header">
        <h3>Export Mix</h3>
        <button className="btn" onClick={() => onClose?.()}>✕</button>
      </div>

      <div className="export-panel__body">
        {stems.length === 0 && <div className="muted">No stems available</div>}

        {stems.map((s) => (
          <div key={s} className="export-panel__row">
            <div className="export-panel__label">{STEM_LABELS[s] || s}</div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={gains[s] ?? 1.0}
              onChange={(e) => setGain(s, parseFloat(e.target.value))}
              className="channel-strip__fader"
              aria-label={`${STEM_LABELS[s] || s} export gain`}
            />
            <button
              className={`btn-mute ${gains[s] === 0 ? 'is-active' : ''}`}
              onClick={() => toggleMute(s)}
              aria-pressed={gains[s] === 0}
            >
              M
            </button>
          </div>
        ))}

        <div className="export-panel__options">
          <label>
            <input
              type="checkbox"
              checked={includeClick}
              onChange={(e) => setIncludeClick(e.target.checked)}
            />{' '}
            Include metronome click track
          </label>
        </div>

        {error && <div className="error-text">{error}</div>}

        <div className="export-panel__actions">
          <button className="btn btn-secondary" onClick={() => onClose?.()} disabled={exporting}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={handleExport} disabled={exporting}>
            {exporting ? 'Exporting…' : 'Export Mix'}
          </button>
        </div>
      </div>
    </div>
  );
}
