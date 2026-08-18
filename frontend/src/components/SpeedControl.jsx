import React, { useEffect, useState } from 'react';

const PRESETS = [0.5, 0.75, 1.0, 1.25, 1.5];
const EPS = 0.025; // tolerance for matching presets

export default function SpeedControl({ currentRate = 1.0, onRateChange }) {
  const [value, setValue] = useState(currentRate);

  useEffect(() => {
    setValue(currentRate);
  }, [currentRate]);

  const clamp = (n) => Math.max(0.25, Math.min(2.0, Number(n) || 1.0));

  const isPresetActive = (r) => Math.abs((currentRate ?? value) - r) < EPS;

  const handlePresetClick = (r) => {
    const clamped = clamp(r);
    // clicking active 1× serves as a reset affordance as well
    onRateChange(clamped);
  };

  const handleSliderChange = (e) => {
    const r = clamp(parseFloat(e.target.value));
    setValue(r);
    onRateChange(r);
  };

  const activePreset = PRESETS.find((p) => isPresetActive(p));
  const showNumeric = !activePreset;
  const displayLabel = (showNumeric ? (currentRate ?? value).toFixed(2) : null) + '×';

  const styles = {
    container: {
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      fontFamily: "'Segoe UI', 'Helvetica Neue', Arial, sans-serif",
      color: '#f0f0f0',
      fontSize: 13,
    },
    presetsRow: { display: 'flex', gap: 8, alignItems: 'center' },
    presetBtn: {
      background: '#242424',
      color: '#f0f0f0',
      border: '1px solid #333',
      padding: '6px 10px',
      borderRadius: 4,
      cursor: 'pointer',
      minWidth: 44,
      textAlign: 'center',
    },
    presetActive: {
      background: '#e8a020',
      color: '#0f0f0f',
      borderColor: '#b87610',
      fontWeight: 600,
      boxShadow: '0 0 0 2px rgba(232,160,32,0.08)'
    },
    sliderRow: { display: 'flex', gap: 10, alignItems: 'center' },
    slider: { flex: 1 },
    numeric: { minWidth: 52, textAlign: 'right', color: '#ddd' },
    resetBtn: {
      background: 'transparent',
      color: '#888',
      border: 'none',
      cursor: 'pointer',
      padding: 6,
      fontSize: 14,
    }
  };

  return (
    <div style={styles.container} aria-label="Speed control">
      <div style={styles.presetsRow}>
        {PRESETS.map((p) => {
          const active = isPresetActive(p);
          return (
            <button
              key={p}
              type="button"
              onClick={() => handlePresetClick(p)}
              style={{ ...styles.presetBtn, ...(active ? styles.presetActive : {}) }}
              aria-pressed={active}
              title={`${p}×`}
            >
              {p === 1.0 ? '1×' : `${p}×`}
            </button>
          );
        })}

        <button
          type="button"
          onClick={() => onRateChange(1.0)}
          aria-label="Reset speed to 1x"
          title="Reset to 1×"
          style={styles.resetBtn}
        >
          1B6
        </button>
      </div>

      <div style={styles.sliderRow}>
        <input
          type="range"
          min="0.25"
          max="2.0"
          step="0.05"
          value={value}
          onChange={handleSliderChange}
          style={styles.slider}
          aria-label="Playback speed"
        />

        <div style={styles.numeric} aria-hidden>
          {showNumeric ? `${(currentRate ?? value).toFixed(2)}×` : ' '}
        </div>
      </div>
    </div>
  );
}
