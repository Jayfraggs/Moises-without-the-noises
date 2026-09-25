import React, { useEffect, useState } from 'react';

const PRESETS = [0.5, 0.75, 1.0, 1.25, 1.5];
const EPS = 0.025;

export default function SpeedControl({ currentRate = 1.0, onRateChange }) {
  const [value, setValue] = useState(currentRate);

  useEffect(() => {
    setValue(currentRate);
  }, [currentRate]);

  const clamp = (n) => Math.max(0.25, Math.min(2.0, Number(n) || 1.0));
  const isPresetActive = (r) => Math.abs((currentRate ?? value) - r) < EPS;

  const handlePresetClick = (r) => onRateChange(clamp(r));

  const handleSliderChange = (e) => {
    const r = clamp(parseFloat(e.target.value));
    setValue(r);
    onRateChange(r);
  };

  const activePreset = PRESETS.find((p) => isPresetActive(p));
  const displayRate = (currentRate ?? value);

  return (
    <div className="speed-control" aria-label="Speed control">
      <div className="speed-control__label">Speed</div>
      <div className="speed-control__row">
        <div className="speed-control__presets">
          {PRESETS.map((p) => {
            const active = isPresetActive(p);
            return (
              <button
                key={p}
                type="button"
                className={`speed-control__preset ${active ? 'is-active' : ''}`}
                onClick={() => handlePresetClick(p)}
                aria-pressed={active}
                title={`${p}×`}
              >
                {p === 1.0 ? '1×' : `${p}×`}
              </button>
            );
          })}
        </div>

        <button
          type="button"
          className="speed-control__reset"
          onClick={() => onRateChange(1.0)}
          aria-label="Reset speed to 1×"
          title="Reset to 1×"
          disabled={isPresetActive(1.0)}
        >
          ↺
        </button>
      </div>

      <div className="speed-control__slider-row">
        <input
          type="range"
          className="speed-control__slider"
          min="0.25"
          max="2.0"
          step="0.05"
          value={value}
          onChange={handleSliderChange}
          aria-label="Playback speed"
        />
        {!activePreset && (
          <span className="speed-control__value" aria-hidden>
            {displayRate.toFixed(2)}×
          </span>
        )}
      </div>

      {displayRate !== 1.0 && (
        <p className="speed-control__pitch-note">Pitch shifts at speeds other than 1×</p>
      )}
    </div>
  );
}
